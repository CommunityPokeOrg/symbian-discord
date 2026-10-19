"""Live backend: connects to Discord's gateway and REST API as a bot.

The phone never talks to Discord directly — Symbian-era TLS stacks cannot
negotiate with discord.com today. This module owns the bot token, keeps a
resumable gateway websocket open, and mirrors guild/channel/message data
into the shared State the HTTP API serves.
"""

import asyncio
import logging

import aiohttp

from state import norm_channel, norm_guild, norm_message, norm_user

log = logging.getLogger("relay.live")

API = "https://discord.com/api/v10"
USER_AGENT = "symbian-discord-relay (https://github.com/CommunityPokeOrg/symbian-discord, 0.1)"

# GUILDS | GUILD_MESSAGES | MESSAGE_CONTENT
INTENTS = (1 << 0) | (1 << 9) | (1 << 15)

# Gateway opcodes
OP_DISPATCH = 0
OP_HEARTBEAT = 1
OP_IDENTIFY = 2
OP_RESUME = 6
OP_RECONNECT = 7
OP_INVALID_SESSION = 9
OP_HELLO = 10
OP_HEARTBEAT_ACK = 11


class LiveBackend(object):
    def __init__(self, token, state):
        self.token = token
        self.state = state
        self._http = None
        self._runner = None
        self._stopping = False
        self.session_id = None
        self.resume_url = None
        self.last_seq = None

    async def start(self):
        self._http = aiohttp.ClientSession(headers={
            "Authorization": "Bot " + self.token,
            "User-Agent": USER_AGENT,
        })
        self._runner = asyncio.ensure_future(self._gateway_loop())

    async def close(self):
        self._stopping = True
        if self._runner:
            self._runner.cancel()
        if self._http:
            await self._http.close()

    # ----------------------------------------------------------- phone API

    async def info(self):
        return self.state.user or {}

    async def guilds(self):
        return sorted(self.state.guilds.values(), key=lambda g: g["name"].lower())

    async def channels(self, gid):
        return self.state.guild_channels(gid)

    async def history(self, cid, limit=20, before=None):
        params = {"limit": max(1, min(int(limit), 50))}
        if before:
            params["before"] = before
        async with self._http.get(
                "%s/channels/%s/messages" % (API, cid),
                params=params) as r:
            if r.status != 200:
                # fall back to whatever the gateway cache holds
                return self.state.channel_messages(cid)[-params["limit"]:]
            raw = await r.json()
        msgs = [norm_message(m) for m in raw]
        msgs.reverse()  # Discord returns newest-first
        return msgs

    async def send(self, cid, content):
        async with self._http.post(
                "%s/channels/%s/messages" % (API, cid),
                json={"content": content}) as r:
            data = await r.json(content_type=None)
            if r.status not in (200, 201):
                raise RuntimeError(
                    "discord send failed %s: %s" % (r.status, data))
            return norm_message(data)

    # ----------------------------------------------------------- gateway

    async def _gateway_loop(self):
        backoff = 2
        while not self._stopping:
            try:
                await self._connect_once()
                backoff = 2
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("gateway connection lost")
            if self._stopping:
                break
            await self.state.emit("disconnected", {})
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

    async def _connect_once(self):
        url = self.resume_url or (await self._gateway_url())
        ws_url = "%s?v=10&encoding=json" % url.rstrip("/")
        log.info("connecting to %s", ws_url)
        async with self._http.ws_connect(
                ws_url, heartbeat=None, max_msg_size=8 * 1024 * 1024) as ws:
            hb_task = None
            try:
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        hb_task = await self._dispatch(
                            ws, msg.json(), hb_task)
                    elif msg.type in (aiohttp.WSMsgType.CLOSED,
                                      aiohttp.WSMsgType.CLOSE,
                                      aiohttp.WSMsgType.ERROR):
                        break
            finally:
                if hb_task:
                    hb_task.cancel()

    async def _dispatch(self, ws, payload, hb_task):
        op = payload.get("op")
        d = payload.get("d") or {}
        seq = payload.get("s")
        if seq is not None:
            self.last_seq = seq

        if op == OP_HELLO:
            interval = d.get("heartbeat_interval", 41250) / 1000.0
            if hb_task:
                hb_task.cancel()
            hb_task = asyncio.ensure_future(
                self._heartbeat(ws, interval))
            if self.session_id:
                await self._send(ws, OP_RESUME, {
                    "token": self.token,
                    "session_id": self.session_id,
                    "seq": self.last_seq or 0,
                })
                log.info("sent RESUME")
            else:
                await self._identify(ws)
            return hb_task

        if op == OP_DISPATCH:
            await self._handle_event(payload.get("t"), d)
        elif op == OP_RECONNECT:
            log.info("gateway asked to reconnect")
            await ws.close()
        elif op == OP_INVALID_SESSION:
            resumable = bool(d)
            log.warning("invalid session (resumable=%s)", resumable)
            if not resumable:
                self.session_id = None
                self.resume_url = None
            await ws.close()
        elif op == OP_HEARTBEAT:
            await self._send(ws, OP_HEARTBEAT, self.last_seq)
        return hb_task

    async def _handle_event(self, t, d):
        if t == "READY":
            self.state.user = norm_user(d.get("user"))
            self.session_id = d.get("session_id")
            self.resume_url = d.get("resume_gateway_url") or self.resume_url
            self.state.ready.set()
            await self.state.emit("ready", {"user": self.state.user})
            log.info("READY as %s", self.state.user.get("username"))
        elif t == "RESUMED":
            self.state.ready.set()
            await self.state.emit("ready", {"user": self.state.user or {}})
        elif t == "GUILD_CREATE":
            g = norm_guild(d)
            self.state.guilds[g["id"]] = g
            for c in d.get("channels") or []:
                nc = norm_channel(c, guild_id=g["id"])
                # only serve text-capable channels to the phone
                if nc["type"] in (0, 5, 15):  # text, announcement, forum
                    self.state.channels[nc["id"]] = nc
            await self.state.emit("guild", g)
        elif t == "GUILD_DELETE":
            if d.get("unavailable"):
                return
            gid = d.get("id", "")
            self.state.guilds.pop(gid, None)
            for cid in [c for c, v in self.state.channels.items()
                        if v["guild_id"] == gid]:
                del self.state.channels[cid]
        elif t == "CHANNEL_CREATE":
            nc = norm_channel(d)
            if nc["type"] in (0, 5):
                self.state.channels[nc["id"]] = nc
                await self.state.emit("channel", nc)
        elif t == "CHANNEL_DELETE":
            nc = norm_channel(d)
            self.state.channels.pop(nc["id"], None)
            await self.state.emit("channel_delete", {"id": nc["id"]})
        elif t == "MESSAGE_CREATE":
            m = norm_message(d)
            self.state.add_message(m)
            await self.state.emit("message", m)
        elif t == "MESSAGE_DELETE":
            await self.state.emit("message_delete",
                                  {"id": d.get("id", ""),
                                   "channel_id": d.get("channel_id", "")})

    async def _identify(self, ws):
        await self._send(ws, OP_IDENTIFY, {
            "token": self.token,
            "intents": INTENTS,
            "properties": {
                "os": "symbian",
                "browser": "symbian-discord-relay",
                "device": "symbian-discord-relay",
            },
        })
        log.info("sent IDENTIFY")

    async def _heartbeat(self, ws, interval):
        # jittered first beat per gateway docs
        await asyncio.sleep(interval * 0.25)
        while True:
            try:
                await self._send(ws, OP_HEARTBEAT, self.last_seq)
            except Exception:
                return
            await asyncio.sleep(interval)

    async def _send(self, ws, op, d):
        await ws.send_json({"op": op, "d": d})

    async def _gateway_url(self):
        async with self._http.get("%s/gateway/bot" % API) as r:
            data = await r.json()
            if r.status != 200:
                raise RuntimeError(
                    "gateway/bot failed %s: %s" % (r.status, data))
            return data["url"]

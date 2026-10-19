"""Mock backend: a canned Discord world for developing the phone client
without a real bot token. Started with RELAY_MOCK=1 or --mock.

The mock serves one guild ("Mock Realm") with three text channels and a
seeded message history. Sending a message stores it as the bot user and
schedules an auto-reply from "t9_bot" so polling clients see real events.
POST /api/mock/inject injects arbitrary events for testing.
"""

import asyncio
import itertools
import time

from state import norm_message

GUILD_ID = "700000000000000001"
BOT_USER = {
    "id": "700000000000000010",
    "username": "symbot",
    "bot": True,
}
MOCK_CHANNELS = [
    {"id": "700000000000000101", "guild_id": GUILD_ID,
     "name": "general", "type": 0, "position": 0},
    {"id": "700000000000000102", "guild_id": GUILD_ID,
     "name": "bots", "type": 0, "position": 1},
    {"id": "700000000000000103", "guild_id": GUILD_ID,
     "name": "nokia", "type": 0, "position": 2},
]
SEED = [
    ("t9_bot", "welcome to mock realm. your phone is talking to discord."),
    ("t9_bot", "send a message and i will echo it back."),
    ("retro_fan", "my n95 is still going strong"),
]


class MockBackend(object):
    def __init__(self, state):
        self.state = state
        self._snow = itertools.count(700000000000000200)
        self._tasks = []

    async def start(self):
        self.state.user = dict(BOT_USER)
        self.state.guilds[GUILD_ID] = {
            "id": GUILD_ID, "name": "Mock Realm", "unavailable": False}
        for c in MOCK_CHANNELS:
            self.state.channels[c["id"]] = dict(c)
        for i, (author, content) in enumerate(SEED):
            self.state.add_message(self._mk_msg(
                MOCK_CHANNELS[0]["id"], author, content,
                ts="2026-01-0%dT12:0%d:00.000000+00:00" % (i + 1, i)))
        self.state.ready.set()
        await self.state.emit("ready", {"user": BOT_USER})
        await self.state.emit("guild", self.state.guilds[GUILD_ID])

    async def close(self):
        for t in self._tasks:
            t.cancel()

    async def inject(self, type_, data):
        """Test hook: emit a synthetic event (also files messages in cache)."""
        if type_ == "message":
            m = norm_message({
                "id": str(next(self._snow)),
                "channel_id": data.get("channel_id",
                                       MOCK_CHANNELS[0]["id"]),
                "author": {"id": "700000000000000011",
                           "username": data.get("author", "t9_bot")},
                "content": data.get("content", ""),
                "timestamp": _iso_now(),
            })
            self.state.add_message(m)
            return await self.state.emit("message", m)
        return await self.state.emit(type_, data)

    # ----------------------------------------------------------- phone API

    async def info(self):
        return dict(BOT_USER)

    async def guilds(self):
        return [self.state.guilds[GUILD_ID]]

    async def channels(self, gid):
        return [dict(c) for c in MOCK_CHANNELS] if gid == GUILD_ID else []

    async def history(self, cid, limit=20, before=None):
        msgs = self.state.channel_messages(cid)
        if before:
            msgs = [m for m in msgs if int(m["id"]) < int(before)]
        return msgs[-int(limit):]

    async def send(self, cid, content):
        if cid not in self.state.channels:
            raise RuntimeError("unknown channel %s" % cid)
        m = self._mk_msg(cid, BOT_USER["username"], content,
                         author_id=BOT_USER["id"])
        self.state.add_message(m)
        await self.state.emit("message", m)
        self._tasks.append(asyncio.ensure_future(self._autoreply(cid, content)))
        return m

    # ----------------------------------------------------------- helpers

    async def _autoreply(self, cid, content):
        await asyncio.sleep(1.0)
        await self.inject("message", {
            "channel_id": cid,
            "author": "t9_bot",
            "content": "heard you: %s" % content[:60],
        })

    def _mk_msg(self, cid, author, content, ts=None, author_id="0"):
        return {
            "id": str(next(self._snow)),
            "channel_id": str(cid),
            "author": author,
            "author_id": author_id,
            "content": content,
            "timestamp": ts or _iso_now(),
        }


def _iso_now():
    return time.strftime("%Y-%m-%dT%H:%M:%S.000000+00:00", time.gmtime())

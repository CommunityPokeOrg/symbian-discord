"""Shared state for the relay: bot identity, caches and the polled event log.

The Symbian client is a thin UI over this state. Everything the phone can
see is normalised here into small JSON-friendly dicts; Discord payloads
never cross the wire to the phone verbatim.
"""

import asyncio
from collections import deque

MAX_EVENTS = 500
MAX_MESSAGES_PER_CHANNEL = 100
MAX_CHANNELS_PER_GUILD = 200


def norm_user(u):
    """Reduce a Discord user object to what the phone needs."""
    if not u:
        return {}
    return {
        "id": u.get("id", ""),
        "username": u.get("username") or u.get("global_name") or "",
        "bot": bool(u.get("bot")),
    }


def norm_guild(g):
    return {
        "id": g.get("id", ""),
        "name": g.get("name") or "?",
        "unavailable": bool(g.get("unavailable")),
    }


def norm_channel(c, guild_id=None):
    return {
        "id": c.get("id", ""),
        "guild_id": c.get("guild_id") or guild_id or "",
        "name": c.get("name") or "?",
        "type": c.get("type", 0),
        "position": c.get("position", 0),
    }


def norm_message(m):
    a = m.get("author") or {}
    return {
        "id": m.get("id", ""),
        "channel_id": m.get("channel_id", ""),
        "author": a.get("username") or a.get("global_name") or "?",
        "author_id": a.get("id", ""),
        "content": m.get("content") or "",
        "timestamp": m.get("timestamp") or "",
    }


class State(object):
    """Sequenced event log plus per-guild/per-channel caches.

    Events carry a monotonically increasing ``seq`` the phone uses as a
    polling cursor (``GET /api/events?since=<seq>``). The deque is bounded:
    a phone that falls more than MAX_EVENTS behind simply re-syncs.
    """

    def __init__(self):
        self.user = None                # normalised bot user
        self.ready = asyncio.Event()
        self.guilds = {}                # gid -> norm guild
        self.channels = {}              # cid -> norm channel
        self.messages = {}              # cid -> deque(norm_message)
        self.events = deque(maxlen=MAX_EVENTS)
        self.seq = 0
        self._cond = asyncio.Condition()

    async def emit(self, type_, data):
        async with self._cond:
            self.seq += 1
            ev = {"seq": self.seq, "type": type_, "data": data}
            self.events.append(ev)
            self._cond.notify_all()
            return ev

    def events_since(self, seq):
        return [e for e in self.events if e["seq"] > seq]

    async def wait_events(self, seq, timeout):
        """Long-poll: return events after ``seq``, waiting up to ``timeout``."""
        found = self.events_since(seq)
        if found:
            return found
        async with self._cond:
            try:
                await asyncio.wait_for(
                    self._cond.wait_for(lambda: bool(self.events_since(seq))),
                    timeout)
            except asyncio.TimeoutError:
                pass
        return self.events_since(seq)

    def add_message(self, msg):
        q = self.messages.setdefault(
            msg["channel_id"], deque(maxlen=MAX_MESSAGES_PER_CHANNEL))
        q.append(msg)

    def channel_messages(self, cid):
        return list(self.messages.get(cid, ()))

    def guild_channels(self, gid):
        chans = [c for c in self.channels.values() if c["guild_id"] == gid]
        chans.sort(key=lambda c: (c.get("position", 0), c.get("id", "")))
        return chans

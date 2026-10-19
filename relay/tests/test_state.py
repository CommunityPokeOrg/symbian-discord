import unittest

from state import State, norm_message


class StateTest(unittest.IsolatedAsyncioTestCase):

    async def test_emit_assigns_monotonic_seq(self):
        s = State()
        a = await s.emit("message", {"x": 1})
        b = await s.emit("guild", {"y": 2})
        self.assertEqual(a["seq"], 1)
        self.assertEqual(b["seq"], 2)

    async def test_events_since_filters(self):
        s = State()
        await s.emit("a", {})
        await s.emit("b", {})
        await s.emit("c", {})
        self.assertEqual([e["type"] for e in s.events_since(1)], ["b", "c"])
        self.assertEqual(s.events_since(3), [])

    async def test_wait_events_returns_immediately_when_pending(self):
        s = State()
        await s.emit("a", {})
        self.assertEqual(len(await s.wait_events(0, 0.05)), 1)

    async def test_wait_events_blocks_until_emit(self):
        s = State()
        waiter = __import__("asyncio").ensure_future(s.wait_events(0, 5))
        await __import__("asyncio").sleep(0.05)
        await s.emit("x", {})
        self.assertEqual(len(await waiter), 1)

    async def test_wait_events_times_out(self):
        s = State()
        self.assertEqual(await s.wait_events(0, 0.05), [])

    def test_norm_message_shape(self):
        m = norm_message({
            "id": "1", "channel_id": "2",
            "author": {"id": "9", "username": "luke"},
            "content": "hi", "timestamp": "2026-01-01T00:00:00.000000+00:00",
        })
        self.assertEqual(m["author"], "luke")
        self.assertEqual(set(m), {"id", "channel_id", "author",
                                  "author_id", "content", "timestamp"})

    def test_channel_messages_bounded(self):
        s = State()
        for i in range(150):
            s.add_message({"channel_id": "c", "content": str(i)})
        self.assertEqual(len(s.channel_messages("c")), 100)


if __name__ == "__main__":
    unittest.main()

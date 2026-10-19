"""End-to-end test of the HTTP API against the mock backend — the same
calls the PyS60 client makes, in the same order."""
import unittest

import aiohttp
from aiohttp import web

from api import build_app
from mock_backend import GUILD_ID, MOCK_CHANNELS, MockBackend
from state import State


class ApiTest(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.state = State()
        self.backend = MockBackend(self.state)
        await self.backend.start()
        app = build_app(self.backend, self.state,
                        allow_mock_inject=True)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await self.site.start()
        self.port = self.site._server.sockets[0].getsockname()[1]
        self.http = aiohttp.ClientSession(
            "http://127.0.0.1:%d" % self.port)

    async def asyncTearDown(self):
        await self.http.close()
        await self.backend.close()
        await self.runner.cleanup()

    async def get(self, path):
        async with self.http.get(path) as r:
            self.assertEqual(r.status, 200, path)
            return await r.json()

    async def test_health(self):
        self.assertTrue((await self.get("/api/health"))["ok"])

    async def test_info_guilds_channels(self):
        info = await self.get("/api/info")
        self.assertEqual(info["username"], "symbot")

        guilds = await self.get("/api/guilds")
        self.assertEqual([g["name"] for g in guilds], ["Mock Realm"])

        chans = await self.get("/api/guilds/%s/channels" % GUILD_ID)
        self.assertEqual(len(chans), len(MOCK_CHANNELS))
        self.assertEqual(chans[0]["name"], "general")

    async def test_history_and_send_flow(self):
        cid = MOCK_CHANNELS[0]["id"]
        hist = await self.get("/api/channels/%s/messages?limit=10" % cid)
        self.assertGreaterEqual(len(hist), 3)

        async with self.http.post("/api/send", json={
                "channel_id": cid, "content": "hello from s60"}) as r:
            self.assertEqual(r.status, 200)
            body = await r.json()
            self.assertTrue(body["ok"])
            self.assertEqual(body["message"]["author"], "symbot")

        # history now includes the sent message
        hist = await self.get("/api/channels/%s/messages" % cid)
        self.assertEqual(hist[-1]["content"], "hello from s60")

    async def test_send_validation(self):
        async with self.http.post("/api/send", json={
                "channel_id": "", "content": "x"}) as r:
            self.assertEqual(r.status, 400)

    async def test_events_long_poll(self):
        cid = MOCK_CHANNELS[0]["id"]
        before = await self.get("/api/events?since=0&timeout=0")
        latest = before["latest_seq"]
        self.assertGreaterEqual(latest, 2)  # ready + guild

        # inject -> visible immediately
        async with self.http.post("/api/mock/inject", json={
                "type": "message",
                "data": {"channel_id": cid, "author": "t9_bot",
                         "content": "injected"}}) as r:
            self.assertEqual(r.status, 200)
        out = await self.get("/api/events?since=%d&timeout=1" % latest)
        types = [e["type"] for e in out["events"]]
        self.assertIn("message", types)
        self.assertEqual(out["events"][-1]["data"]["content"], "injected")

    async def test_events_timeout_returns_empty(self):
        out = await self.get("/api/events?since=99999&timeout=0")
        self.assertEqual(out["events"], [])


class KeyAuthTest(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.state = State()
        self.backend = MockBackend(self.state)
        await self.backend.start()
        app = build_app(self.backend, self.state, relay_key="sekret")
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await self.site.start()
        self.port = self.site._server.sockets[0].getsockname()[1]
        self.base = "http://127.0.0.1:%d" % self.port

    async def asyncTearDown(self):
        await self.backend.close()
        await self.runner.cleanup()

    async def test_requires_key(self):
        async with aiohttp.ClientSession(self.base) as http:
            async with http.get("/api/info") as r:
                self.assertEqual(r.status, 401)
            async with http.get("/api/info",
                                headers={"X-Relay-Key": "sekret"}) as r:
                self.assertEqual(r.status, 200)


if __name__ == "__main__":
    unittest.main()

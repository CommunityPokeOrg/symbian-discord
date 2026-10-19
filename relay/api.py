"""HTTP API the Symbian client talks to.

Plain JSON over HTTP/1.1 — the most a PyS60 httplib socket can handle.
Keep every payload small and ASCII-safe (utf-8 encoded) for the phone.
"""

import asyncio
import json

from aiohttp import web

MAX_POLL_TIMEOUT = 30  # seconds; PyS60 sockets time out around ~60s


def _json(data, status=200):
    return web.Response(
        text=json.dumps(data, separators=(",", ":")),
        status=status,
        content_type="application/json")


def build_app(backend, state, relay_key=None, allow_mock_inject=False):
    app = web.Application()
    app["backend"] = backend
    app["state"] = state
    app["relay_key"] = relay_key
    app["allow_mock_inject"] = allow_mock_inject

    app.router.add_get("/api/health", health)
    app.router.add_get("/api/info", info)
    app.router.add_get("/api/guilds", guilds)
    app.router.add_get("/api/guilds/{gid}/channels", channels)
    app.router.add_get("/api/channels/{cid}/messages", history)
    app.router.add_get("/api/events", events)
    app.router.add_post("/api/send", send)
    if allow_mock_inject:
        app.router.add_post("/api/mock/inject", mock_inject)

    app.middlewares.append(key_middleware)
    return app


@web.middleware
async def key_middleware(request, handler):
    key = request.app.get("relay_key")
    if key and request.headers.get("X-Relay-Key") != key:
        return _json({"error": "unauthorized"}, status=401)
    return await handler(request)


async def health(request):
    return _json({"ok": True, "service": "symbian-discord-relay"})


async def info(request):
    return _json(await request.app["backend"].info())


async def guilds(request):
    return _json(await request.app["backend"].guilds())


async def channels(request):
    gid = request.match_info["gid"]
    return _json(await request.app["backend"].channels(gid))


async def history(request):
    cid = request.match_info["cid"]
    q = request.rel_url.query
    limit = _int(q.get("limit"), 20, lo=1, hi=50)
    before = q.get("before") or None
    return _json(await request.app["backend"].history(cid, limit, before))


async def events(request):
    q = request.rel_url.query
    since = _int(q.get("since"), 0, lo=0)
    timeout = _int(q.get("timeout"), 20, lo=0, hi=MAX_POLL_TIMEOUT)
    state = request.app["state"]
    found = await state.wait_events(since, timeout)
    return _json({"latest_seq": state.seq, "events": found})


async def send(request):
    try:
        body = await request.json()
    except Exception:
        return _json({"error": "invalid json body"}, status=400)
    cid = str(body.get("channel_id") or "")
    content = (body.get("content") or "")[:2000]
    if not cid or not content:
        return _json({"error": "channel_id and content required"}, status=400)
    try:
        msg = await request.app["backend"].send(cid, content)
    except Exception as e:
        return _json({"error": str(e)}, status=502)
    return _json({"ok": True, "message": msg})


async def mock_inject(request):
    try:
        body = await request.json()
    except Exception:
        return _json({"error": "invalid json body"}, status=400)
    ev = await request.app["backend"].inject(
        body.get("type", "message"), body.get("data") or {})
    return _json({"ok": True, "event": ev})


def _int(value, default, lo=None, hi=None):
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v

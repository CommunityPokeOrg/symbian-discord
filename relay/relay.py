#!/usr/bin/env python3
"""symbian-discord relay — the bridge between a PyS60 phone and Discord.

Run on any machine the phone can reach over plain HTTP (a PC, a Raspberry
Pi, a VPS). It owns the bot token and speaks modern TLS/WebSocket to
Discord so the phone only has to speak HTTP/1.1 + JSON.

Usage:
    DISCORD_BOT_TOKEN=... python3 relay.py            # live mode
    python3 relay.py --mock                           # no token, canned data

Config (env vars or --flag equivalents):
    DISCORD_BOT_TOKEN   bot token (required unless --mock)
    RELAY_HOST          bind address        (default 0.0.0.0)
    RELAY_PORT          listen port         (default 8778)
    RELAY_KEY           shared key the phone must send as X-Relay-Key
    RELAY_MOCK          1 = mock backend, no Discord connection
"""

import argparse
import logging
import os
import sys

from aiohttp import web

from api import build_app
from state import State


def parse_args(argv):
    p = argparse.ArgumentParser(description="symbian-discord relay")
    p.add_argument("--host", default=os.environ.get("RELAY_HOST", "0.0.0.0"))
    p.add_argument("--port", type=int,
                   default=int(os.environ.get("RELAY_PORT", "8778")))
    p.add_argument("--key", default=os.environ.get("RELAY_KEY"),
                   help="shared key phones must send as X-Relay-Key")
    p.add_argument("--token", default=os.environ.get("DISCORD_BOT_TOKEN"))
    p.add_argument("--mock", action="store_true",
                   default=os.environ.get("RELAY_MOCK") == "1",
                   help="serve canned data, never contact Discord")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s")

    state = State()
    if args.mock:
        from mock_backend import MockBackend
        backend = MockBackend(state)
        mode = "mock"
    else:
        if not args.token:
            print("error: set DISCORD_BOT_TOKEN or run with --mock",
                  file=sys.stderr)
            return 2
        from live_backend import LiveBackend
        backend = LiveBackend(args.token, state)
        mode = "live"

    app = build_app(backend, state, relay_key=args.key,
                    allow_mock_inject=args.mock)

    async def on_startup(app):
        await backend.start()

    async def on_cleanup(app):
        await backend.close()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    logging.getLogger("relay").info(
        "listening on http://%s:%s (%s mode)", args.host, args.port, mode)
    web.run_app(app, host=args.host, port=args.port, print=None)
    return 0


if __name__ == "__main__":
    sys.exit(main())

# symbian-discord

A Discord bot client for Symbian OS — run a Discord bot from a Nokia
Series 60 phone over its WLAN connection.

```
┌──────────────────┐   HTTP/1.1 + JSON   ┌───────────────┐   TLS + WebSocket   ┌──────────┐
│  S60 phone       │ ◄────────────────── │  relay        │ ◄────────────────── │  Discord │
│  (PyS60 client)  │   LAN / internet    │  (Python 3)   │    gateway v10      │          │
└──────────────────┘                     └───────────────┘                     └──────────┘
```

Symbian-era TLS can't negotiate with `discord.com` today, so — like every
retro-platform Discord client — the phone never talks to Discord
directly. The **relay** owns the bot token, keeps a resumable gateway
websocket open, and serves a tiny JSON-over-HTTP API the phone can
handle. The **client** is a Python for S60 app that browses
guilds → channels → live messages and sends replies.

## Features

- Guild list → text channel list → channel view with history
- Live incoming messages via long-poll (no per-message round trips)
- Send messages as the bot from the phone's T9 keyboard
- Optional shared-key auth between phone and relay
- **Mock mode** — develop/test the whole stack with canned Discord data,
  no bot token needed
- PyS60 client verified end-to-end under Python 2.x against the relay

## Layout

| Path       | What                                                   |
|------------|--------------------------------------------------------|
| `client/`  | PyS60 app (`default.py` + modules) — copy to the phone |
| `relay/`   | Python 3 relay service + tests                         |
| `docs/`    | Setup guide                                            |

## Quickstart (mock mode, no token)

On the machine the phone will reach:

```sh
cd relay
pip install -r requirements.txt
python3 relay.py --mock          # serves canned "Mock Realm" data
```

On the phone: install Python for S60 2.0, copy `client/*.py` to
`E:\Python\`, run `default.py`, enter `http://<relay-host>:8778`.

## Quickstart (live)

```sh
cd relay
pip install -r requirements.txt
DISCORD_BOT_TOKEN=... python3 relay.py
# optional: RELAY_KEY=shared-secret requires X-Relay-Key on the phone too
```

Requires a Discord application with a bot token and the **Message
Content** privileged intent enabled. See `docs/SETUP.md` for the full
walkthrough — bot creation, relay hosting, phone-side install, and
optional `.sis` packaging.

## Requirements

- **Phone:** Symbian Series 60 3rd edition FP1+ (or Symbian^3 / Anna /
  Belle) with Python for S60 2.0.0, and WLAN data access.
- **Relay host:** Python 3.9+ with `aiohttp` — anything from a desktop to
  a Raspberry Pi to a VPS.

## Status

Experimental. Text channels only (text, announcement, forum); no DMs,
attachments, reactions, or voice — the screen is 240×320, after all.

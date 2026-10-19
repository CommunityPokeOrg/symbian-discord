# relay — Discord bridge for the phone

Python 3 service that owns the bot token, stays connected to the Discord
gateway (resume + heartbeat handled), and serves a small JSON/HTTP API
the PyS60 client can reach over plain HTTP/1.1.

```sh
pip install -r requirements.txt

# live: real Discord
DISCORD_BOT_TOKEN=... python3 relay.py

# mock: canned "Mock Realm" data, no token — develop the client offline
python3 relay.py --mock
```

## HTTP API

All bodies are JSON. `X-Relay-Key: <key>` required on every request when
`RELAY_KEY` is set.

| Method | Path                              | Purpose                                 |
|--------|-----------------------------------|-----------------------------------------|
| GET    | `/api/health`                     | liveness                                |
| GET    | `/api/info`                       | bot user                                |
| GET    | `/api/guilds`                     | guilds the bot is in                    |
| GET    | `/api/guilds/{gid}/channels`      | text channels of a guild                |
| GET    | `/api/channels/{cid}/messages?limit&before` | channel history              |
| GET    | `/api/events?since&timeout`       | long-poll event log (message/guild/...) |
| POST   | `/api/send` `{channel_id, content}` | send a message as the bot             |
| POST   | `/api/mock/inject` (mock only)    | inject a synthetic event                |

Events are `{seq, type, data}`; `type` is `ready | guild | channel |
channel_delete | message | message_delete | disconnected`. The client
keeps the last seen `seq` and polls `since=<seq>`.

## Internals

- `live_backend.py` — gateway v10 websocket (IDENTIFY with GUILDS |
  GUILD_MESSAGES | MESSAGE_CONTENT), reconnect/resume loop, REST for
  history+send.
- `mock_backend.py` — same interface, canned data + auto-reply for tests.
- `state.py` — bounded event log (500) + per-channel message cache (100).
- `api.py` — aiohttp handlers + optional `X-Relay-Key` middleware.

## Tests

```sh
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

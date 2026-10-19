# Setup guide

Three pieces: a Discord bot, the relay, and the phone app.

## 1. Create the Discord bot

1. Go to the Discord Developer Portal → **New Application**.
2. Under **Bot** → **Reset Token**, copy the token.
3. Still under **Bot**, enable **Message Content Intent** (privileged) —
   the relay needs it to read message text.
4. Under **OAuth2 → URL Generator**: scope `bot`, permissions
   *View Channels*, *Send Messages*, *Read Message History*.
5. Open the generated URL to invite the bot to your server.

Keep the token secret. Only the relay holds it — it never reaches the
phone.

## 2. Run the relay

Any machine reachable from the phone over plain HTTP: a PC on the same
WLAN, a Raspberry Pi, or a VPS.

```sh
cd relay
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
DISCORD_BOT_TOKEN=... .venv/bin/python relay.py
```

Environment variables (or `--flag` equivalents):

| Var                | Default   | Meaning                                    |
|--------------------|-----------|--------------------------------------------|
| `DISCORD_BOT_TOKEN`| —         | bot token (required unless `--mock`)       |
| `RELAY_HOST`       | `0.0.0.0` | bind address                               |
| `RELAY_PORT`       | `8778`    | listen port                                |
| `RELAY_KEY`        | unset     | if set, phone must send `X-Relay-Key`      |
| `RELAY_MOCK`       | `0`       | `1` = canned data, no Discord connection   |

Verify: `curl http://<host>:8778/api/health` → `{"ok":true,...}`.

### As a service

```ini
# /etc/systemd/system/symbian-discord-relay.service
[Unit]
Description=symbian-discord relay
After=network-online.target

[Service]
Environment=DISCORD_BOT_TOKEN=...
Environment=RELAY_PORT=8778
# Environment=RELAY_KEY=shared-secret
WorkingDirectory=/opt/symbian-discord/relay
ExecStart=/opt/symbian-discord/relay/.venv/bin/python relay.py
Restart=always

[Install]
WantedBy=multi-user.target
```

## 3. Install the phone app

### Real hardware (S60 3rd ed FP1+/v5, Symbian^3/Anna/Belle)

1. Install **Python for S60 2.0.0** (`Python_2.0.0_for_3rdEd.sis` +
   `PythonScriptShell_2.0.0_3rdEd.sis`). On Belle, use the community
   PyS60 build if needed.
2. Copy these four files to the memory card at `E:\Python\`:

   ```
   client/default.py
   client/discordbot.py
   client/relay_client.py
   client/jsonutil.py
   ```

   (Bluetooth OBEX push, USB mass-storage, or a file manager all work.)
3. Open the Python app → **Run script** → `default.py`.
4. Enter the relay URL, e.g. `http://192.168.1.10:8778`. The app saves it
   to `E:\discordbot.cfg`.

### Emulator

The S60 SDK emulator (Windows, Carbide.c++ era) plus PyS60 works the
same — files go in the emulated `E:\Python\` drive. Point the client at
`http://<host-ip>:8778` with the relay in `--mock` mode for development.

### Optional: package as `.sis`

Use `ensymble`'s `py2sis` on a Python 2.7 machine to bundle the four
files into an installable `.sis` that launches the interpreter and
script automatically.

## Networking notes

- **Same WLAN** is the easy path: phone and relay on one LAN, client URL
  `http://<lan-ip>:8778`.
- **Relay on a VPS:** expose port 8778 and always set `RELAY_KEY` —
  anyone who can reach the port can post as the bot.
- **No HTTPS needed** on the phone side; the token lives only on the
  relay. If the relay leaves your LAN, put it behind a TLS reverse proxy
  and accept that the phone can't reach it — that's the trade-off of
  2008-era TLS.
- The relay does gateway **long-polling** (`GET /api/events?since=seq&
  timeout=20`), so battery and data use stay sane on metered mobile data.

## Troubleshooting

| Symptom                          | Check                                             |
|----------------------------------|---------------------------------------------------|
| "Connect failed: network"        | relay running? port reachable? `curl /api/health` |
| "unauthorized" (401)             | `RELAY_KEY` set on relay but key field blank in app settings |
| "No guilds"                      | bot invited to a server?                          |
| Sends fail, reads work           | bot lacks *Send Messages* permission in channel   |
| Empty channels list              | bot lacks *View Channel* permission               |

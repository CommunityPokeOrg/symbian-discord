# client — PyS60 phone app

A Python for S60 application. Four files, no dependencies beyond what
PyS60 2.0.0 ships:

| File             | Role                                              |
|------------------|---------------------------------------------------|
| `default.py`     | entry point — run this in the PyS60 script shell  |
| `discordbot.py`  | appuifw UI: guilds → channels → live channel view |
| `relay_client.py`| httplib-based JSON client for the relay API       |
| `jsonutil.py`    | RFC 4627 JSON for Python 2.5 (PyS60 has no `json`)|

## Install

Copy all four files to `E:\Python\` on the phone's memory card, then
open the Python application → **Run script** → `default.py`.

## Use

1. **Relay URL** prompt — `http://<relay-host>:8778`. Saved to
   `E:\discordbot.cfg`; **Settings** changes it later (including the
   optional relay key).
2. **Guilds** — pick a server.
3. **Channels** — pick a `#text` channel.
4. **Channel view** — last 30 messages, then live updates polled in the
   background. **Send** types a message on the keypad and posts it as
   the bot. **Back** returns to the channel list.

Own messages are echoed locally when sent; the poll loop skips the
gateway echo of the bot's own messages so nothing double-displays.

# -*- coding: utf-8 -*-
"""Discord bot client UI for Series 60 (PyS60).

Flow: relay URL -> guilds -> text channels -> live channel view.
Channel view shows history then long-polls the relay for new messages
on a worker thread; an Ao_timer drains them onto the Text body.
"""
import appuifw
import e32
import thread
import time

import jsonutil
from relay_client import RelayClient, RelayError

CONFIG_PATH = u"e:\\discordbot.cfg"
POLL_TIMEOUT = 20
DRAIN_SECONDS = 0.4
HISTORY_SIZE = 30


class DiscordBotApp(object):
    def __init__(self):
        self.client = None
        self.bot_name = u"?"
        self.bot_id = u""
        self.guilds = []
        self.channels = []
        self.channel = None
        self.guild = None
        self.seq = 0
        self.polling = False
        self.pending = []
        self.timer = e32.Ao_timer()
        self.lock = e32.Ao_lock()
        self.relay_url, self.relay_key = self._load_config()

    # ------------------------------------------------------------ startup

    def run(self):
        appuifw.app.title = u"Discord"
        appuifw.app.screen = "normal"
        while self.client is None:
            self._connect_prompt()
        self.show_guilds()

    def shutdown(self):
        self.stop_polling()
        appuifw.app.body = appuifw.Text()

    def quit(self):
        self.shutdown()
        self.lock.signal()

    # ------------------------------------------------------------ connect

    def _connect_prompt(self):
        url = appuifw.query(u"Relay URL", "text", self.relay_url)
        if url is None:
            self.quit()
            return
        self.relay_url = url.strip()
        self.client = RelayClient(self.relay_url, self.relay_key)
        try:
            info = self.client.get_info()
            self.bot_name = info.get("username") or u"bot"
            self.bot_id = unicode(info.get("id") or u"")
            appuifw.app.title = u"Discord: %s" % self.bot_name
            self._save_config()
        except RelayError, e:
            appuifw.note(u"Connect failed: %s" % e, "error")
            self.client = None
            if not appuifw.query(u"Retry?", "query"):
                self.quit()
                return

    def reconnect(self):
        try:
            self.client = RelayClient(self.relay_url, self.relay_key)
            info = self.client.get_info()
            self.bot_name = info.get("username") or u"bot"
            self.bot_id = unicode(info.get("id") or u"")
            appuifw.app.title = u"Discord: %s" % self.bot_name
            self._save_config()
            self.show_guilds()
        except RelayError, e:
            self.client = None
            appuifw.note(u"Connect failed: %s" % e, "error")

    # ------------------------------------------------------------ views

    def show_guilds(self):
        self.stop_polling()
        self.channel = None
        try:
            self.guilds = self.client.get_guilds()
        except RelayError, e:
            appuifw.note(u"Load failed: %s" % e, "error")
            self.guilds = []
        if not self.guilds:
            appuifw.note(u"No guilds — invite the bot first")
        names = [unicode(g["name"]) for g in self.guilds]
        self.lb = appuifw.Listbox(names, self.on_guild_select)
        appuifw.app.body = self.lb
        appuifw.app.menu = [
            (u"Open", self.on_guild_select),
            (u"Refresh", self.show_guilds),
            (u"Reconnect", self.reconnect),
            (u"Settings", self.show_settings),
            (u"Exit", self.quit),
        ]

    def on_guild_select(self):
        if not self.guilds:
            return
        self.guild = self.guilds[self.lb.current()]
        self.show_channels()

    def show_channels(self):
        self.stop_polling()
        self.channel = None
        try:
            self.channels = self.client.get_channels(self.guild["id"])
        except RelayError, e:
            appuifw.note(u"Load failed: %s" % e, "error")
            self.channels = []
        names = [u"#%s" % c["name"] for c in self.channels]
        self.lb = appuifw.Listbox(names, self.on_channel_select)
        appuifw.app.body = self.lb
        appuifw.app.menu = [
            (u"Open", self.on_channel_select),
            (u"Refresh", self.show_channels),
            (u"Back", self.show_guilds),
        ]

    def on_channel_select(self):
        if not self.channels:
            return
        self.channel = self.channels[self.lb.current()]
        self.show_channel()

    def show_channel(self):
        self.text = appuifw.Text()
        self.text.color = 0xffffff
        self.text.set(u"#%s — loading...\r" % self.channel["name"])
        appuifw.app.body = self.text
        appuifw.app.menu = [
            (u"Send", self.send_message),
            (u"Refresh", self.refresh_messages),
            (u"Back", self.show_channels),
        ]
        self.refresh_messages()
        self.start_polling()

    # ------------------------------------------------------------ messages

    def refresh_messages(self):
        try:
            msgs = self.client.get_messages(
                self.channel["id"], limit=HISTORY_SIZE)
        except RelayError, e:
            appuifw.note(u"Refresh failed: %s" % e, "error")
            return
        self.text.set(u"")
        for m in msgs:
            self.text.add(self._fmt(m))
        self.text.add(u"—\r")

    def send_message(self):
        text = appuifw.query(u"Message:", "text")
        if not text:
            return
        try:
            self.client.send_message(self.channel["id"], text)
            self.text.add(self._fmt({
                "author": self.bot_name,
                "content": text,
                "timestamp": u"",
            }))
        except RelayError, e:
            appuifw.note(u"Send failed: %s" % e, "error")

    # ------------------------------------------------------------ polling

    def start_polling(self):
        self.polling = True
        thread.start_new_thread(self._poll_loop, ())
        self._drain()

    def stop_polling(self):
        self.polling = False
        self.timer.cancel()
        del self.pending[:]

    def _poll_loop(self):
        while self.polling:
            try:
                res = self.client.poll_events(self.seq, POLL_TIMEOUT)
            except RelayError:
                time.sleep(5)
                continue
            events = res.get("events") or []
            for ev in events:
                s = ev.get("seq") or 0
                if s > self.seq:
                    self.seq = s
                self.pending.append(ev)

    def _drain(self):
        if self.pending:
            items = self.pending[:]
            del self.pending[:]
            for ev in items:
                self._handle_event(ev)
        if self.polling:
            self.timer.after(DRAIN_SECONDS, self._drain)

    def _handle_event(self, ev):
        if ev.get("type") != "message":
            return
        m = ev.get("data") or {}
        if not self.channel:
            return
        if unicode(m.get("channel_id")) != unicode(self.channel["id"]):
            return
        # own sends are already echoed locally by send_message
        if unicode(m.get("author_id")) == self.bot_id:
            return
        self.text.add(self._fmt(m))

    # ------------------------------------------------------------ settings

    def show_settings(self):
        url = appuifw.query(u"Relay URL", "text", self.relay_url)
        if url is None:
            return
        key = appuifw.query(u"Relay key (blank = none)", "text",
                           self.relay_key or u"")
        if key is None:
            return
        self.relay_url = url.strip()
        self.relay_key = key.strip() or None
        self._save_config()
        appuifw.note(u"Saved — reconnect to apply")
        self.reconnect()

    # ------------------------------------------------------------ helpers

    def _fmt(self, m):
        ts = (m.get("timestamp") or u"")
        hhmm = ts[11:16] if len(ts) >= 16 else u"--:--"
        return u"[%s] %s: %s\r" % (
            hhmm, m.get("author") or u"?", m.get("content") or u"")

    def _load_config(self):
        try:
            data = open(CONFIG_PATH, "r").read().decode("utf-8")
            cfg = jsonutil.loads(data)
            return cfg.get("relay") or u"", cfg.get("key")
        except Exception:
            return u"", None

    def _save_config(self):
        try:
            f = open(CONFIG_PATH, "w")
            f.write(jsonutil.dumps({
                "relay": self.relay_url,
                "key": self.relay_key,
            }).encode("utf-8"))
            f.close()
        except Exception:
            pass

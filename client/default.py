# -*- coding: utf-8 -*-
"""Entry point for the PyS60 script shell.

Put this file (plus discordbot.py, relay_client.py, jsonutil.py) in
E:\\Python\\ or C:\\Python\\ and run it from the Python app.
"""
import socket

import appuifw
import e32

socket.setdefaulttimeout(60)

import discordbot

old_exit = appuifw.app.exit_key_handler
app = discordbot.DiscordBotApp()
appuifw.app.exit_key_handler = app.lock.signal
app.run()
app.lock.wait()
app.shutdown()
appuifw.app.exit_key_handler = old_exit

# -*- coding: utf-8 -*-
"""HTTP client for the symbian-discord relay (Python for S60).

Plain HTTP/1.1 + JSON — PyS60's httplib handles this fine over WLAN.
The phone never talks to Discord directly; the relay owns the bot token.
"""
import httplib
import jsonutil


class RelayError(Exception):
    pass


class RelayClient(object):
    """base: e.g. 'http://192.168.1.10:8778' or '192.168.1.10:8778'"""

    def __init__(self, base, key=None):
        base = base.strip()
        if not base:
            raise RelayError("empty relay url")
        if not base.startswith("http://"):
            base = "http://" + base
        self.base = base.rstrip("/")
        hostport = self.base[len("http://"):]
        self.host, _, port = hostport.partition(":")
        self.port = int(port) if port else 80
        self.key = key

    # --------------------------------------------------------- endpoints

    def health(self):
        return self._request("GET", "/api/health")

    def get_info(self):
        return self._request("GET", "/api/info")

    def get_guilds(self):
        return self._request("GET", "/api/guilds")

    def get_channels(self, guild_id):
        return self._request("GET", "/api/guilds/%s/channels" % guild_id)

    def get_messages(self, channel_id, limit=20, before=None):
        path = "/api/channels/%s/messages?limit=%d" % (channel_id, limit)
        if before:
            path += "&before=%s" % before
        return self._request("GET", path)

    def poll_events(self, since, timeout=20):
        return self._request(
            "GET", "/api/events?since=%d&timeout=%d" % (since, timeout))

    def send_message(self, channel_id, content):
        return self._request(
            "POST", "/api/send",
            {"channel_id": str(channel_id), "content": content})

    # --------------------------------------------------------- transport

    def _request(self, method, path, body=None):
        conn = httplib.HTTPConnection(self.host, self.port)
        headers = {"User-Agent": "symbian-discord/0.1"}
        payload = None
        if body is not None:
            payload = jsonutil.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.key:
            headers["X-Relay-Key"] = self.key
        try:
            conn.request(method, path, body=payload, headers=headers)
            resp = conn.getresponse()
            status = resp.status
            data = resp.read()
        except Exception, e:
            conn.close()
            raise RelayError("network: %s" % e)
        conn.close()

        text = data.decode("utf-8") if isinstance(data, str) else data
        try:
            parsed = jsonutil.loads(text)
        except Exception:
            parsed = None
        if status != 200:
            msg = parsed.get("error") if isinstance(parsed, dict) else None
            raise RelayError(msg or "http %d" % status)
        return parsed

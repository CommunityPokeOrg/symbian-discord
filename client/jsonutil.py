# -*- coding: utf-8 -*-
r"""Minimal JSON for Python for S60 (Python 2.5.4).

PyS60 has no json module, so this provides dumps() and loads() covering
the RFC 4627 subset the client needs: dict/list/unicode/str/int/long/
float/bool/None, full string escapes including \uXXXX surrogate pairs.
"""


class JSONError(Exception):
    pass


def dumps(obj):
    """Serialise obj to a JSON str. Non-ASCII characters are emitted raw;
    callers should encode the result as UTF-8 before sending."""
    if obj is None:
        return "null"
    if obj is True:
        return "true"
    if obj is False:
        return "false"
    if isinstance(obj, (int, long)):
        return str(obj)
    if isinstance(obj, float):
        return repr(obj)
    if isinstance(obj, basestring):
        return '"%s"' % _escape(obj)
    if isinstance(obj, dict):
        return "{%s}" % ",".join(
            "%s:%s" % (dumps(k), dumps(v)) for k, v in obj.items())
    if isinstance(obj, (list, tuple)):
        return "[%s]" % ",".join(dumps(i) for i in obj)
    raise JSONError("cannot serialise %r" % type(obj))


def loads(s):
    """Parse JSON text (str or unicode) into Python objects."""
    if not isinstance(s, unicode):
        s = s.decode("utf-8")
    val, pos = _parse(s, _skip(s, 0))
    if _skip(s, pos) != len(s):
        raise JSONError("trailing data at %d" % pos)
    return val


_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}


def _escape(s):
    if not isinstance(s, unicode):
        s = s.decode("utf-8")
    out = []
    for ch in s:
        if ch == '"' or ch == "\\":
            out.append("\\" + ch)
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20:
            out.append("\\u%04x" % ord(ch))
        else:
            out.append(ch)
    return "".join(out)


def _skip(s, pos):
    while pos < len(s) and s[pos] in u" \t\r\n":
        pos += 1
    return pos


def _parse(s, pos):
    if pos >= len(s):
        raise JSONError("unexpected end")
    ch = s[pos]
    if ch == u"{":
        return _parse_object(s, pos + 1)
    if ch == u"[":
        return _parse_array(s, pos + 1)
    if ch == u'"':
        return _parse_string(s, pos + 1)
    if s.startswith(u"true", pos):
        return True, pos + 4
    if s.startswith(u"false", pos):
        return False, pos + 5
    if s.startswith(u"null", pos):
        return None, pos + 4
    return _parse_number(s, pos)


def _parse_string(s, pos):
    out = []
    while True:
        if pos >= len(s):
            raise JSONError("unterminated string")
        ch = s[pos]
        if ch == u'"':
            return u"".join(out), pos + 1
        if ch == u"\\":
            pos += 1
            if pos >= len(s):
                raise JSONError("unterminated escape")
            e = s[pos]
            if e == u"u":
                cp = int(s[pos + 1:pos + 5], 16)
                pos += 4
                # combine UTF-16 surrogate pairs (emoji etc.)
                if 0xD800 <= cp <= 0xDBFF and s[pos + 1:pos + 3] == u"\\u":
                    lo = int(s[pos + 3:pos + 7], 16)
                    if 0xDC00 <= lo <= 0xDFFF:
                        cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00)
                        pos += 6
                out.append(unichr(cp))
            elif e in _ESCAPES:
                out.append(_ESCAPES[e])
            else:
                raise JSONError("bad escape \\%s" % e)
            pos += 1
        else:
            out.append(ch)
            pos += 1


def _parse_number(s, pos):
    end = pos
    while end < len(s) and s[end] in u"+-0123456789.eE":
        end += 1
    text = s[pos:end]
    if not text or text in u"+-.":
        raise JSONError("bad value at %d" % pos)
    try:
        if u"." in text or u"e" in text or u"E" in text:
            return float(text), end
        return int(text), end
    except ValueError:
        raise JSONError("bad number %r" % text)


def _parse_array(s, pos):
    out = []
    pos = _skip(s, pos)
    if pos < len(s) and s[pos] == u"]":
        return out, pos + 1
    while True:
        val, pos = _parse(s, _skip(s, pos))
        out.append(val)
        pos = _skip(s, pos)
        if pos < len(s) and s[pos] == u",":
            pos += 1
            continue
        if pos < len(s) and s[pos] == u"]":
            return out, pos + 1
        raise JSONError("expected , or ] at %d" % pos)


def _parse_object(s, pos):
    out = {}
    pos = _skip(s, pos)
    if pos < len(s) and s[pos] == u"}":
        return out, pos + 1
    while True:
        pos = _skip(s, pos)
        if pos >= len(s) or s[pos] != u'"':
            raise JSONError("expected key at %d" % pos)
        key, pos = _parse_string(s, pos + 1)
        pos = _skip(s, pos)
        if pos >= len(s) or s[pos] != u":":
            raise JSONError("expected : at %d" % pos)
        val, pos = _parse(s, _skip(s, pos + 1))
        out[key] = val
        pos = _skip(s, pos)
        if pos < len(s) and s[pos] == u",":
            pos += 1
            continue
        if pos < len(s) and s[pos] == u"}":
            return out, pos + 1
        raise JSONError("expected , or } at %d" % pos)

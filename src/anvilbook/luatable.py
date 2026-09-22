import re

from .importer import DecodeError, lua_unescape

_SKIP = re.compile(rb'(?:\s+|--[^\n]*)*')
_NAME = re.compile(rb'[A-Za-z_][A-Za-z0-9_]*')
_STRING = re.compile(rb'"((?:[^"\\]|\\.)*)"', re.S)
_NUMBER = re.compile(rb'-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?')
_WORDS = {b'true': True, b'false': False, b'nil': None}


class LuaParseError(Exception):
    pass


class _Parser:
    def __init__(self, text: bytes):
        self.text = text
        self.pos = 0

    def peek(self) -> bytes:
        m = _SKIP.match(self.text, self.pos)
        self.pos = m.end() if m else self.pos
        return self.text[self.pos:self.pos + 1]

    def expect(self, token: bytes) -> None:
        if self.peek() != token:
            raise LuaParseError(f'expected {token!r} at byte {self.pos}')
        self.pos += 1

    def value(self):
        c = self.peek()
        if c == b'{':
            return self.table()
        if c == b'"':
            m = _STRING.match(self.text, self.pos)
            if not m:
                raise LuaParseError(f'unterminated string at byte {self.pos}')
            self.pos = m.end()
            try:
                return lua_unescape(m.group(1)).decode('utf-8', 'replace')
            except DecodeError as e:
                raise LuaParseError(str(e)) from e
        m = _NAME.match(self.text, self.pos)
        if m and m.group(0) in _WORDS:
            self.pos = m.end()
            return _WORDS[m.group(0)]
        m = _NUMBER.match(self.text, self.pos)
        if m:
            self.pos = m.end()
            s = m.group(0)
            return float(s) if re.search(rb'[.eE]', s) else int(s)
        raise LuaParseError(f'unexpected {c!r} at byte {self.pos}')

    def table(self) -> dict:
        self.expect(b'{')
        out: dict = {}
        n = 1
        while True:
            c = self.peek()
            if c == b'}':
                self.pos += 1
                return out
            if not c:
                raise LuaParseError('unterminated table')
            if c == b'[':
                self.pos += 1
                key = self.value()
                self.expect(b']')
                self.expect(b'=')
            else:
                key = n
                n += 1
            out[key] = self.value()
            if self.peek() in (b',', b';'):
                self.pos += 1


def parse_savedvariables(text: bytes) -> dict[str, object]:
    p = _Parser(text)
    out: dict[str, object] = {}
    while p.peek():
        m = _NAME.match(p.text, p.pos)
        if not m:
            raise LuaParseError(f'expected a name at byte {p.pos}')
        p.pos = m.end()
        p.expect(b'=')
        out[m.group(0).decode()] = p.value()
    return out

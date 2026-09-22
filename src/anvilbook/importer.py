import re
from dataclasses import dataclass

import cbor2

DB_START = b'AUCTIONATOR_PRICE_DATABASE = {'
VENDOR_START = b'AUCTIONATOR_VENDOR_PRICE_CACHE = {'

_ESCAPE = re.compile(rb'\\(\d{1,3}|\r\n|.)', re.S)
_SIMPLE = {
    b'a': b'\a', b'b': b'\b', b'f': b'\f', b'n': b'\n', b'r': b'\r', b't': b'\t', b'v': b'\v',
    b'\\': b'\\', b'"': b'"', b"'": b"'",
    b'\n': b'\n', b'\r': b'\n', b'\r\n': b'\n',
}


class DecodeError(Exception):
    pass


@dataclass(frozen=True)
class ItemPrice:
    item_id: int
    min_price: int
    available: int
    day_high: int
    day: int


@dataclass(frozen=True)
class Snapshot:
    realm: str
    prices: list[ItemPrice]
    vendor_prices: dict[int, int]


def lua_unescape(s: bytes) -> bytes:
    def repl(m: re.Match) -> bytes:
        tok = m.group(1)
        if tok[:1].isdigit():
            n = int(tok)
            if n > 255:
                raise DecodeError(f'bad escape \\{tok.decode()}')
            return bytes([n])
        if tok not in _SIMPLE:
            raise DecodeError(f'unknown escape \\{tok!r}')
        return _SIMPLE[tok]

    return _ESCAPE.sub(repl, s)


def _block(text: bytes, marker: bytes) -> bytes:
    start = text.find(marker)
    if start < 0:
        return b''
    end = text.find(b'\nAUCTIONATOR_', start + 1)
    return text[start:end if end >= 0 else len(text)]


def _realm_literal(block: bytes, realm: str) -> bytes:
    key = re.escape(realm.encode())
    m = re.search(rb'(?m)^\["' + key + rb'"\] = (?:"((?:[^"\\]|\\.)*)"|(\{))', block, re.S)
    if not m:
        raise DecodeError(f'realm {realm!r} not found in the price database')
    if m.group(2):
        raise DecodeError(f'realm {realm!r} is stored as a Lua table; only the CBOR string form is supported')
    return lua_unescape(m.group(1))


def _day_map(v) -> dict[int, int]:
    return {int(k): int(n) for k, n in v.items()} if isinstance(v, dict) else {}


def parse_prices(raw: bytes) -> list[ItemPrice]:
    try:
        data = cbor2.loads(raw)
    except cbor2.CBORDecodeError as e:
        raise DecodeError(f'CBOR decode failed: {e}') from e
    if not isinstance(data, dict):
        raise DecodeError('the price database is not a map')
    out = []
    for key, e in data.items():
        if not (isinstance(key, str) and key.isdigit() and isinstance(e, dict) and 'm' in e):
            continue
        highs, avail = _day_map(e.get('h')), _day_map(e.get('a'))
        if not highs and not avail:
            continue
        day = max(highs.keys() | avail.keys())
        out.append(ItemPrice(int(key), int(e['m']), avail.get(day, 0), highs.get(day, int(e['m'])), day))
    return out


def parse_vendor_prices(text: bytes) -> dict[int, int]:
    block = _block(text, VENDOR_START)
    return {int(k): int(v) for k, v in re.findall(rb'(?m)^\["(\d+)"\] = (\d+),', block)}


def _first_realm(block: bytes) -> str:
    found = re.search(rb'(?m)^\["([^"\\]+)"\] = ["{]', block)
    if not found:
        raise DecodeError('no realm in the price database')
    return found.group(1).decode()


def read_snapshot(text: bytes, realm: str | None = None) -> Snapshot:
    block = _block(text, DB_START)
    if not block:
        raise DecodeError('AUCTIONATOR_PRICE_DATABASE not found')
    name = realm or _first_realm(block)
    return Snapshot(name, parse_prices(_realm_literal(block, name)), parse_vendor_prices(text))

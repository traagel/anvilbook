import pytest

from anvilbook.importer import DecodeError, ItemPrice, lua_unescape, read_snapshot
from lua_fixture import entry, savedvariables


@pytest.mark.parametrize('raw, expected', [
    (b'plain', b'plain'),
    (b'a\\\\b', b'a\\b'),
    (b'\\"', b'"'),
    (b"\\'", b"'"),
    (b'\\n', b'\n'),
    (b'\\r', b'\r'),
    (b'\\t', b'\t'),
    (b'\\a\\b\\f\\v', b'\a\b\f\v'),
    (b'\\000', b'\x00'),
    (b'\\65', b'A'),
    (b'\\1234', b'{4'),
    (b'\\\n', b'\n'),
    (b'\\\r\n', b'\n'),
])
def test_lua_unescape(raw, expected):
    assert lua_unescape(raw) == expected


@pytest.mark.parametrize('raw', [b'\\q', b'\\256'])
def test_lua_unescape_rejects_bad_escapes(raw):
    with pytest.raises(DecodeError):
        lua_unescape(raw)


@pytest.mark.parametrize('byte_strings', [True, False])
def test_read_snapshot_round_trip_with_escaped_bytes(byte_strings):
    data = {
        'version': 2,
        '2770': entry(57, 2453, 10, 73),
        '2771': entry(200, 2453, 13),
        '2840': entry(34, 2453, 0),
        '3576': entry(92, 2453, 4360),
        'g:1234:5': entry(1, 2453, 1),
    }
    text = savedvariables(data, vendor={3466: 1900, 2880: 95}, byte_strings=byte_strings)
    assert b'\\' in text

    snap = read_snapshot(text)

    assert snap.realm == 'ClassicBetaPvP'
    assert {p.item_id: p for p in snap.prices} == {
        2770: ItemPrice(2770, 57, 10, 73, 2453),
        2771: ItemPrice(2771, 200, 13, 200, 2453),
        2840: ItemPrice(2840, 34, 0, 34, 2453),
        3576: ItemPrice(3576, 92, 4360, 92, 2453),
    }
    assert snap.vendor_prices == {3466: 1900, 2880: 95}


def test_latest_day_wins():
    e = {'m': 7, 'h': {'2450': 5, '2453': 7}, 'a': {'2450': 3, '2453': 9}, 'l': []}
    snap = read_snapshot(savedvariables({'1': e}))
    assert snap.prices == [ItemPrice(1, 7, 9, 7, 2453)]


def test_empty_database_has_no_prices():
    assert read_snapshot(savedvariables({'version': 2})).prices == []


def test_table_form_is_rejected():
    with pytest.raises(DecodeError, match='Lua table'):
        read_snapshot(savedvariables(None, as_table=True))


def test_unknown_realm_is_rejected():
    with pytest.raises(DecodeError, match='not found'):
        read_snapshot(savedvariables({'version': 2}), realm='Nope')


def test_missing_database_is_rejected():
    with pytest.raises(DecodeError):
        read_snapshot(b'AUCTIONATOR_CONFIG = {\r\n}\r\n')

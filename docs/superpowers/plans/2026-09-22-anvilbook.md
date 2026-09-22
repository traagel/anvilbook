# anvilbook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local web app that imports Auctionator's saved price database, keeps every import as history in SQLite, and shows craft profits, price history, and sell-through.

**Architecture:** A Python package with pure units (importer, store, items, craft) and a thin FastAPI app that wires them, runs a file watcher, and serves one static HTML page. Every unit except the UI has pytest tests that need no network and no WoW install.

**Tech Stack:** Python 3.12+, uv, FastAPI, uvicorn, cbor2, stdlib sqlite3, plain JS, uPlot 1.6.32 (CDN).

**Spec:** `docs/superpowers/specs/2026-09-22-anvilbook-design.md`

## Global Constraints

- Dependencies: `fastapi>=0.136`, `uvicorn>=0.40`, `cbor2>=5.6`. Dev: `pytest>=8`, `httpx>=0.28`. No other dependencies.
- Serve on `127.0.0.1:8765` (env `ANVILBOOK_PORT` overrides the port).
- Data directory: `~/.local/share/anvilbook/` (env `ANVILBOOK_DATA` overrides).
- Money is integer copper everywhere in the backend. Only the UI formats g/s/c.
- AH cut default 0.05. Cast seconds default 3. Max use level default 20. Min listed default 3.
- Forever override default: `{"3490": 100}`.
- Caps default: Blacksmithing 120, Mining 99. A profession with no cap is not craftable.
- Recursion depth for buy-or-craft: 3.
- Commit messages end with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.
- Code comments: why-only. No narration.

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, dependencies, `anvilbook` script |
| `.gitignore` | Ignore venv and caches |
| `src/anvilbook/__init__.py` | Empty package marker |
| `src/anvilbook/importer.py` | Lua string unescape, find realm literal, CBOR decode, vendor cache |
| `src/anvilbook/store.py` | SQLite schema, scans, prices, history, sell-through, settings |
| `src/anvilbook/items.py` | Download and load the item database |
| `src/anvilbook/craft.py` | Buy-or-craft recursion, Pareto options, craft rows |
| `src/anvilbook/watcher.py` | Import the file when it changes; status for the UI |
| `src/anvilbook/app.py` | FastAPI app factory, watcher task, `run()` |
| `src/anvilbook/static/index.html` | The UI |
| `tests/lua_fixture.py` | Build a WoW-style `Auctionator.lua` for tests |
| `tests/test_importer.py`, `tests/test_store.py`, `tests/test_items.py`, `tests/test_craft.py`, `tests/test_app.py` | Tests |

---

### Task 1: Project scaffold and importer

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `src/anvilbook/__init__.py`, `src/anvilbook/importer.py`
- Test: `tests/lua_fixture.py`, `tests/test_importer.py`

**Interfaces:**
- Produces:
  - `class DecodeError(Exception)`
  - `@dataclass(frozen=True) ItemPrice(item_id: int, min_price: int, available: int, day_high: int, day: int)`
  - `@dataclass(frozen=True) Snapshot(realm: str, prices: list[ItemPrice], vendor_prices: dict[int, int])`
  - `lua_unescape(s: bytes) -> bytes`
  - `parse_prices(raw: bytes) -> list[ItemPrice]`
  - `parse_vendor_prices(text: bytes) -> dict[int, int]`
  - `read_snapshot(text: bytes, realm: str | None = None) -> Snapshot`
  - Test helper `tests/lua_fixture.py`: `entry(m, day, available, high=None) -> dict`, `savedvariables(realm_data, realm="ClassicBetaPvP", vendor=None, as_table=False) -> bytes`

- [ ] **Step 1: Create the project files**

`pyproject.toml`:

```toml
[project]
name = "anvilbook"
version = "0.1.0"
description = "Auctionator price history and crafting profit for WoW Classic"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.136",
    "uvicorn>=0.40",
    "cbor2>=5.6",
]

[project.scripts]
anvilbook = "anvilbook.app:run"

[dependency-groups]
dev = [
    "pytest>=8",
    "httpx>=0.28",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/anvilbook"]
```

`.gitignore`:

```
.venv/
__pycache__/
.pytest_cache/
*.egg-info/
```

`src/anvilbook/__init__.py`: empty file.

- [ ] **Step 2: Write the test fixture helper**

`tests/lua_fixture.py`:

```python
import cbor2


def lua_escape(b: bytes) -> bytes:
    out = bytearray()
    for c in b:
        if c == 0x5C:
            out += b'\\\\'
        elif c == 0x22:
            out += b'\\"'
        elif c == 0x0A:
            out += b'\\n'
        elif c == 0x0D:
            out += b'\\r'
        elif c == 0x00:
            out += b'\\000'
        else:
            out.append(c)
    return bytes(out)


def entry(m, day, available, high=None):
    return {'m': m, 'h': {str(day): high if high is not None else m}, 'a': {str(day): available}, 'l': []}


def savedvariables(realm_data, realm='ClassicBetaPvP', vendor=None, as_table=False):
    lines = [b'AUCTIONATOR_CONFIG = {', b'}', b'AUCTIONATOR_PRICE_DATABASE = {', b'["__dbversion"] = 8,']
    if as_table:
        lines += [b'["' + realm.encode() + b'"] = {', b'},']
    else:
        lines.append(b'["' + realm.encode() + b'"] = "' + lua_escape(cbor2.dumps(realm_data)) + b'",')
    lines += [b'}', b'AUCTIONATOR_VENDOR_PRICE_CACHE = {', b'["__dbversion"] = 1,']
    lines += [f'["{k}"] = {v},'.encode() for k, v in (vendor or {}).items()]
    lines.append(b'}')
    return b'\r\n'.join(lines) + b'\r\n'
```

- [ ] **Step 3: Write the failing tests**

`tests/test_importer.py`:

```python
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


def test_read_snapshot_round_trip_with_escaped_bytes():
    data = {
        'version': 2,
        '2770': entry(57, 2453, 10, 73),
        '2771': entry(200, 2453, 13),
        '2840': entry(34, 2453, 0),
        '3576': entry(92, 2453, 4360),
        'g:1234:5': entry(1, 2453, 1),
    }
    text = savedvariables(data, vendor={3466: 1900, 2880: 95})
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
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `cd ~/git/anvilbook && uv run pytest tests/test_importer.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'anvilbook.importer'`

- [ ] **Step 5: Write the importer**

`src/anvilbook/importer.py`:

```python
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


def read_snapshot(text: bytes, realm: str | None = None) -> Snapshot:
    block = _block(text, DB_START)
    if not block:
        raise DecodeError('AUCTIONATOR_PRICE_DATABASE not found')
    if realm is None:
        found = re.search(rb'(?m)^\["([^"\\]+)"\] = ["{]', block)
        if not found:
            raise DecodeError('no realm in the price database')
        realm = found.group(1).decode()
    return Snapshot(realm, parse_prices(_realm_literal(block, realm)), parse_vendor_prices(text))
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_importer.py -q`
Expected: PASS (21 passed)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock .gitignore src tests
git commit -m "feat: decode Auctionator price database

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: SQLite store

**Files:**
- Create: `src/anvilbook/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `Snapshot`, `ItemPrice` from Task 1.
- Produces:
  - `DEFAULT_SETTINGS: dict`
  - `class Store(path: Path | str)` with:
    - `has_hash(file_hash: str) -> bool`
    - `add_scan(snap: Snapshot, file_mtime: datetime, file_hash: str) -> int | None` (None if the hash exists)
    - `scans() -> list[dict]` keys `id, file_mtime, realm, items`
    - `latest_scan_id() -> int | None`
    - `prices(scan_id: int) -> dict[int, dict]` keys `item_id, min_price, available, day_high` (listed rows only)
    - `item_ids() -> set[int]`
    - `vendor_prices() -> dict[int, int]`
    - `history(item_id: int) -> list[dict]` keys `scan_id, file_mtime, min_price (None if not listed), available`
    - `sellthrough(from_id: int, to_id: int) -> list[dict]` keys `item_id, from_available, to_available, change, from_price, to_price`, sorted by `change` ascending
    - `settings() -> dict`, `save_settings(values: dict) -> dict` (raises `KeyError` for unknown keys)

- [ ] **Step 1: Write the failing tests**

`tests/test_store.py`:

```python
from datetime import datetime, timezone

import pytest

from anvilbook.importer import ItemPrice, Snapshot
from anvilbook.store import DEFAULT_SETTINGS, Store

T1 = datetime(2026, 9, 20, 0, 11, tzinfo=timezone.utc)
T2 = datetime(2026, 9, 21, 0, 11, tzinfo=timezone.utc)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / 'test.db')


def snap(*prices, vendor=None):
    return Snapshot('R', list(prices), vendor or {})


def test_add_scan_skips_known_hash(store):
    assert store.add_scan(snap(ItemPrice(1, 100, 10, 100, 2453)), T1, 'h1') == 1
    assert store.add_scan(snap(ItemPrice(1, 100, 10, 100, 2453)), T1, 'h1') is None
    assert store.has_hash('h1')
    assert [s['id'] for s in store.scans()] == [1]
    assert store.latest_scan_id() == 1


def test_prices_skip_items_not_listed_on_scan_day(store):
    sid = store.add_scan(snap(ItemPrice(1, 100, 10, 100, 2453), ItemPrice(9, 7, 3, 7, 2450)), T1, 'h1')
    assert store.prices(sid) == {1: {'item_id': 1, 'min_price': 100, 'available': 10, 'day_high': 100}}
    assert store.scans()[0]['items'] == 1
    assert store.item_ids() == {1, 9}


def test_history_shows_unlisted_as_zero(store):
    store.add_scan(snap(ItemPrice(2, 50, 5, 50, 2453)), T1, 'h1')
    store.add_scan(snap(ItemPrice(1, 90, 4, 90, 2454)), T2, 'h2')
    points = store.history(2)
    assert [(p['min_price'], p['available']) for p in points] == [(50, 5), (None, 0)]
    assert points[0]['file_mtime'] == T1.isoformat()


def test_sellthrough(store):
    store.add_scan(snap(ItemPrice(1, 100, 10, 100, 2453), ItemPrice(2, 50, 5, 50, 2453),
                        ItemPrice(9, 7, 3, 7, 2450)), T1, 'h1')
    store.add_scan(snap(ItemPrice(1, 90, 4, 90, 2454), ItemPrice(3, 30, 7, 30, 2454)), T2, 'h2')
    rows = store.sellthrough(1, 2)
    assert [(r['item_id'], r['from_available'], r['to_available'], r['change']) for r in rows] == [
        (1, 10, 4, -6), (2, 5, 0, -5), (3, 0, 7, 7)]
    assert (rows[0]['from_price'], rows[0]['to_price']) == (100, 90)
    assert rows[1]['to_price'] is None


def test_vendor_prices_are_upserted(store):
    store.add_scan(snap(ItemPrice(1, 1, 1, 1, 1), vendor={3466: 1900}), T1, 'h1')
    store.add_scan(snap(ItemPrice(1, 1, 1, 1, 1), vendor={3466: 1922, 2880: 95}), T2, 'h2')
    assert store.vendor_prices() == {3466: 1922, 2880: 95}


def test_settings(store):
    assert store.settings() == DEFAULT_SETTINGS
    assert store.save_settings({'min_listed': 5})['min_listed'] == 5
    assert store.settings()['skills'] == DEFAULT_SETTINGS['skills']
    with pytest.raises(KeyError):
        store.save_settings({'bogus': 1})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_store.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'anvilbook.store'`

- [ ] **Step 3: Write the store**

`src/anvilbook/store.py`:

```python
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from .importer import Snapshot

WOW_SAVEDVARIABLES = (
    Path.home() / '.local/share/Steam/steamapps/compatdata/2625793156/pfx/drive_c/Program Files (x86)'
    / 'World of Warcraft/_classic_beta_/WTF/Account/1111708535#1/SavedVariables/Auctionator.lua'
)

DEFAULT_SETTINGS = {
    'savedvariables_path': str(WOW_SAVEDVARIABLES),
    'realm': None,
    'skills': {'Blacksmithing': 120, 'Mining': 99},
    'skill_overrides': {'3490': 100},
    'max_use_level': 20,
    'min_listed': 3,
    'cast_seconds': 3,
    'ah_cut': 0.05,
}

SCHEMA = '''
CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY,
    file_mtime TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    realm TEXT NOT NULL,
    file_hash TEXT NOT NULL UNIQUE,
    scan_day INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS prices (
    scan_id INTEGER NOT NULL REFERENCES scans(id),
    item_id INTEGER NOT NULL,
    min_price INTEGER NOT NULL,
    available INTEGER NOT NULL,
    day_high INTEGER NOT NULL,
    day INTEGER NOT NULL,
    PRIMARY KEY (scan_id, item_id)
);
CREATE TABLE IF NOT EXISTS vendor_prices (item_id INTEGER PRIMARY KEY, price INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
'''

# Auctionator keeps the last price of items that are no longer listed, so only rows
# seen on the scan's latest day count as listed.
LISTED = 'p.day = s.scan_day'


class Store:
    def __init__(self, path: Path | str):
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)

    def _query(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, args).fetchall()

    def has_hash(self, file_hash: str) -> bool:
        return bool(self._query('SELECT 1 FROM scans WHERE file_hash = ?', (file_hash,)))

    def add_scan(self, snap: Snapshot, file_mtime: datetime, file_hash: str) -> int | None:
        scan_day = max(p.day for p in snap.prices)
        now = datetime.now(timezone.utc).isoformat(timespec='seconds')
        with self._lock, self._db:
            try:
                cur = self._db.execute(
                    'INSERT INTO scans (file_mtime, imported_at, realm, file_hash, scan_day) VALUES (?, ?, ?, ?, ?)',
                    (file_mtime.isoformat(), now, snap.realm, file_hash, scan_day))
            except sqlite3.IntegrityError:
                return None
            scan_id = cur.lastrowid
            self._db.executemany(
                'INSERT INTO prices VALUES (?, ?, ?, ?, ?, ?)',
                [(scan_id, p.item_id, p.min_price, p.available, p.day_high, p.day) for p in snap.prices])
            self._db.executemany(
                'INSERT INTO vendor_prices VALUES (?, ?) ON CONFLICT(item_id) DO UPDATE SET price = excluded.price',
                list(snap.vendor_prices.items()))
            return scan_id

    def scans(self) -> list[dict]:
        rows = self._query(f'''
            SELECT s.id, s.file_mtime, s.realm, COUNT(p.item_id) AS items
            FROM scans s LEFT JOIN prices p ON p.scan_id = s.id AND {LISTED}
            GROUP BY s.id ORDER BY s.id''')
        return [dict(r) for r in rows]

    def latest_scan_id(self) -> int | None:
        row = self._query('SELECT MAX(id) AS id FROM scans')[0]
        return row['id']

    def prices(self, scan_id: int) -> dict[int, dict]:
        rows = self._query(f'''
            SELECT p.item_id, p.min_price, p.available, p.day_high
            FROM prices p JOIN scans s ON s.id = p.scan_id
            WHERE p.scan_id = ? AND {LISTED}''', (scan_id,))
        return {r['item_id']: dict(r) for r in rows}

    def item_ids(self) -> set[int]:
        return {r['item_id'] for r in self._query('SELECT DISTINCT item_id FROM prices')}

    def vendor_prices(self) -> dict[int, int]:
        return {r['item_id']: r['price'] for r in self._query('SELECT item_id, price FROM vendor_prices')}

    def history(self, item_id: int) -> list[dict]:
        rows = self._query(f'''
            SELECT s.id AS scan_id, s.file_mtime, p.min_price, COALESCE(p.available, 0) AS available
            FROM scans s LEFT JOIN prices p ON p.scan_id = s.id AND p.item_id = ? AND {LISTED}
            ORDER BY s.id''', (item_id,))
        return [dict(r) for r in rows]

    def sellthrough(self, from_id: int, to_id: int) -> list[dict]:
        a, b = self.prices(from_id), self.prices(to_id)
        rows = []
        for item_id in a.keys() | b.keys():
            before, after = a.get(item_id, {}), b.get(item_id, {})
            rows.append({
                'item_id': item_id,
                'from_available': before.get('available', 0),
                'to_available': after.get('available', 0),
                'change': after.get('available', 0) - before.get('available', 0),
                'from_price': before.get('min_price'),
                'to_price': after.get('min_price'),
            })
        rows.sort(key=lambda r: (r['change'], r['item_id']))
        return rows

    def settings(self) -> dict:
        stored = {r['key']: json.loads(r['value']) for r in self._query('SELECT key, value FROM settings')}
        return {**DEFAULT_SETTINGS, **stored}

    def save_settings(self, values: dict) -> dict:
        unknown = values.keys() - DEFAULT_SETTINGS.keys()
        if unknown:
            raise KeyError(f'unknown settings: {sorted(unknown)}')
        with self._lock, self._db:
            self._db.executemany(
                'INSERT INTO settings VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value',
                [(k, json.dumps(v)) for k, v in values.items()])
        return self.settings()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_store.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/anvilbook/store.py tests/test_store.py
git commit -m "feat: store scans, history, sell-through, settings in SQLite

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Item database and craft calculator

**Files:**
- Create: `src/anvilbook/items.py`, `src/anvilbook/craft.py`
- Test: `tests/test_items.py`, `tests/test_craft.py`

**Interfaces:**
- Consumes: price dicts shaped like `Store.prices()` output (`{item_id: {'min_price': int, 'available': int, ...}}`), vendor dict from `Store.vendor_prices()`, settings dict from `Store.settings()`.
- Produces:
  - `load_items(cache: Path) -> dict[int, dict]` with keys `name, icon, quality, requiredLevel, sellPrice, vendorPrice, createdBy`
  - `@dataclass CraftSettings(skills, skill_overrides, max_use_level, min_listed, cast_seconds, ah_cut)` and `CraftSettings.from_dict(s: dict) -> CraftSettings` (raises `ValueError`, `TypeError`, or `KeyError` on bad input)
  - `@dataclass CraftRow(item_id, name, profession, skill, cost, revenue, profit, casts, per_cast, per_hour, listed, path, cheapest_profit, cheapest_casts, cheapest_path)`
  - `class Calculator(items, prices, vendor, settings)` with `options(item_id, depth=0) -> list[tuple[float, float, str]]`, `recipe_options(recipe, depth) -> list[tuple[float, float, str]]`, `rows() -> list[CraftRow]` sorted by `per_hour` descending

- [ ] **Step 1: Write the failing tests**

`tests/test_items.py`:

```python
import json

from anvilbook.items import load_items


def test_load_items_keeps_needed_fields(tmp_path):
    cache = tmp_path / 'items.json'
    cache.write_text(json.dumps([
        {'itemId': 2841, 'name': 'Bronze Bar', 'tooltip': [{'label': 'x'}], 'sellPrice': 50,
         'createdBy': [{'amount': [2, 2]}]},
    ]))
    items = load_items(cache)
    assert list(items) == [2841]
    assert items[2841]['name'] == 'Bronze Bar'
    assert 'tooltip' not in items[2841]
    assert items[2841]['vendorPrice'] is None
```

`tests/test_craft.py`:

```python
import pytest

from anvilbook.craft import Calculator, CraftSettings


def recipe(category, skill, reagents, amount=(1, 1)):
    return {'amount': list(amount), 'requiredSkill': skill, 'category': category,
            'reagents': [{'itemId': i, 'amount': n} for i, n in reagents]}


ITEMS = {
    2770: {'name': 'Copper Ore'},
    2771: {'name': 'Tin Ore'},
    2840: {'name': 'Copper Bar', 'createdBy': [recipe('Mining', 1, [(2770, 1)])]},
    3576: {'name': 'Tin Bar', 'createdBy': [recipe('Mining', 65, [(2771, 1)])]},
    2841: {'name': 'Bronze Bar', 'createdBy': [recipe('Mining', 65, [(2840, 1), (3576, 1)], amount=(2, 2))]},
}
PRICES = {i: {'min_price': p, 'available': 100}
          for i, p in {2770: 57, 2771: 200, 2840: 73, 3576: 248, 2841: 220}.items()}


def settings(**kw):
    base = dict(skills={'Mining': 99}, skill_overrides={}, max_use_level=20, min_listed=3,
                cast_seconds=3, ah_cut=0.05)
    return CraftSettings(**{**base, **kw})


def row(rows, item_id):
    return next((r for r in rows if r.item_id == item_id), None)


def test_bronze_pareto_paths():
    calc = Calculator(ITEMS, PRICES, {}, settings())
    opts = calc.recipe_options(ITEMS[2841]['createdBy'][0], 0)
    assert [(p, c) for p, c, _ in opts] == [(257, 3), (273, 2), (321, 1)]


def test_bronze_row_best_per_cast_and_cheapest():
    r = row(Calculator(ITEMS, PRICES, {}, settings()).rows(), 2841)
    assert r.revenue == pytest.approx(418)
    assert (r.cost, r.casts, r.path) == (321, 1, 'craft')
    assert r.per_cast == pytest.approx(97)
    assert r.per_hour == pytest.approx(97 * 1200)
    assert r.cheapest_profit == pytest.approx(161)
    assert r.cheapest_casts == 3
    assert r.cheapest_path == 'craft[Copper Bar=craft, Tin Bar=craft]'


def test_skill_cap_blocks_recipes():
    calc = Calculator(ITEMS, PRICES, {}, settings(skills={'Mining': 50}))
    rows = calc.rows()
    assert row(rows, 2841) is None and row(rows, 3576) is None
    assert row(rows, 2840) is not None
    assert calc.options(3576) == [(248, 0, 'buy')]


def test_forever_override_unlocks_recipe():
    rows = Calculator(ITEMS, PRICES, {}, settings(skills={'Mining': 50}, skill_overrides={2841: 50})).rows()
    assert row(rows, 2841) is not None


def test_profession_without_cap_is_not_craftable():
    assert Calculator(ITEMS, PRICES, {}, settings(skills={})).rows() == []


def test_filters():
    high_level = {**ITEMS, 2841: {**ITEMS[2841], 'requiredLevel': 25}}
    assert row(Calculator(high_level, PRICES, {}, settings()).rows(), 2841) is None
    assert Calculator(ITEMS, PRICES, {}, settings(min_listed=200)).rows() == []


def test_vendor_price_beats_ah():
    items = {**ITEMS, 2771: {'name': 'Tin Ore', 'vendorPrice': 150}}
    assert Calculator(items, PRICES, {}, settings()).options(2771) == [(150, 0, 'buy')]
    assert Calculator(ITEMS, PRICES, {2771: 120}, settings()).options(2771) == [(120, 0, 'buy')]


def test_self_referencing_recipe_terminates():
    items = {1: {'name': 'Loop', 'createdBy': [recipe('Mining', 1, [(1, 1)])]}}
    prices = {1: {'min_price': 100, 'available': 10}}
    assert Calculator(items, prices, {}, settings()).rows() == []


def test_settings_from_dict_converts_types():
    s = CraftSettings.from_dict({'skills': {'Mining': 99}, 'skill_overrides': {'3490': 100},
                                 'max_use_level': 20, 'min_listed': 3, 'cast_seconds': 3, 'ah_cut': 0.05,
                                 'savedvariables_path': 'x', 'realm': None})
    assert s.skill_overrides == {3490: 100}
    with pytest.raises(ValueError):
        CraftSettings.from_dict({'skills': {}, 'skill_overrides': {}, 'max_use_level': 'x',
                                 'min_listed': 3, 'cast_seconds': 3, 'ah_cut': 0.05})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_items.py tests/test_craft.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'anvilbook.items'` and `'anvilbook.craft'`

- [ ] **Step 3: Write the item loader**

`src/anvilbook/items.py`:

```python
import json
import urllib.request
from pathlib import Path

URL = 'https://raw.githubusercontent.com/nexus-devs/wow-classic-items/master/data/json/data.json'
FIELDS = ('name', 'icon', 'quality', 'requiredLevel', 'sellPrice', 'vendorPrice', 'createdBy')


def load_items(cache: Path) -> dict[int, dict]:
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        part = cache.with_suffix('.part')
        urllib.request.urlretrieve(URL, part)
        part.replace(cache)
    return {x['itemId']: {k: x.get(k) for k in FIELDS} for x in json.loads(cache.read_bytes())}
```

- [ ] **Step 4: Write the calculator**

`src/anvilbook/craft.py`:

```python
from dataclasses import dataclass
from itertools import product

# Deep enough for ore -> bar -> alloy -> item; also stops recipe cycles.
MAX_DEPTH = 3

Option = tuple[float, float, str]


@dataclass
class CraftSettings:
    skills: dict[str, int]
    skill_overrides: dict[int, int]
    max_use_level: int
    min_listed: int
    cast_seconds: float
    ah_cut: float

    @classmethod
    def from_dict(cls, s: dict) -> 'CraftSettings':
        return cls(
            skills={str(k): int(v) for k, v in s['skills'].items()},
            skill_overrides={int(k): int(v) for k, v in s['skill_overrides'].items()},
            max_use_level=int(s['max_use_level']),
            min_listed=int(s['min_listed']),
            cast_seconds=float(s['cast_seconds']),
            ah_cut=float(s['ah_cut']),
        )


@dataclass
class CraftRow:
    item_id: int
    name: str
    profession: str
    skill: int
    cost: float
    revenue: float
    profit: float
    casts: float
    per_cast: float
    per_hour: float
    listed: int
    path: str
    cheapest_profit: float
    cheapest_casts: float
    cheapest_path: str


def pareto(opts: list[Option]) -> list[Option]:
    front: list[Option] = []
    for o in sorted(opts, key=lambda o: (o[0], o[1])):
        if not front or o[1] < front[-1][1]:
            front.append(o)
    return front


class Calculator:
    def __init__(self, items: dict[int, dict], prices: dict[int, dict], vendor: dict[int, int],
                 settings: CraftSettings):
        self.items = items
        self.prices = prices
        self.vendor = vendor
        self.s = settings
        self._memo: dict[tuple[int, int], list[Option]] = {}

    def skill(self, item_id: int, recipe: dict) -> int:
        return self.s.skill_overrides.get(item_id, recipe.get('requiredSkill') or 0)

    def can_craft(self, item_id: int, recipe: dict) -> bool:
        cap = self.s.skills.get(recipe.get('category'))
        return cap is not None and self.skill(item_id, recipe) <= cap

    def buy_price(self, item_id: int) -> int | None:
        ah = (self.prices.get(item_id) or {}).get('min_price')
        vendor = self.vendor.get(item_id) or (self.items.get(item_id) or {}).get('vendorPrice')
        found = [p for p in (ah, vendor) if p]
        return min(found) if found else None

    def options(self, item_id: int, depth: int = 0) -> list[Option]:
        key = (item_id, depth)
        if key not in self._memo:
            opts: list[Option] = []
            price = self.buy_price(item_id)
            if price:
                opts.append((price, 0, 'buy'))
            if depth < MAX_DEPTH:
                for recipe in (self.items.get(item_id) or {}).get('createdBy') or []:
                    if self.can_craft(item_id, recipe):
                        n = sum(recipe['amount']) / 2
                        opts += [(p / n, c / n, path) for p, c, path in self.recipe_options(recipe, depth + 1)]
            self._memo[key] = pareto(opts)
        return self._memo[key]

    def recipe_options(self, recipe: dict, depth: int) -> list[Option]:
        per_reagent = []
        for r in recipe['reagents']:
            name = (self.items.get(r['itemId']) or {}).get('name', str(r['itemId']))
            per_reagent.append([(p * r['amount'], c * r['amount'], name, path)
                                for p, c, path in self.options(r['itemId'], depth)])
        out = []
        for combo in product(*per_reagent):
            crafted = [f'{name}={path}' for _, _, name, path in combo if path != 'buy']
            out.append((sum(o[0] for o in combo), 1 + sum(o[1] for o in combo),
                        'craft' + (f"[{', '.join(crafted)}]" if crafted else '')))
        return pareto(out)

    def rows(self) -> list[CraftRow]:
        out = []
        for item_id, price in self.prices.items():
            item = self.items.get(item_id)
            if (not item or (item.get('requiredLevel') or 0) > self.s.max_use_level
                    or price['available'] < self.s.min_listed):
                continue
            for recipe in item.get('createdBy') or []:
                if not self.can_craft(item_id, recipe):
                    continue
                n = sum(recipe['amount']) / 2
                revenue = max(price['min_price'] * (1 - self.s.ah_cut), item.get('sellPrice') or 0) * n
                opts = self.recipe_options(recipe, 0)
                if not opts:
                    continue
                cost, casts, path = max(opts, key=lambda o: (revenue - o[0]) / o[1])
                cheap_cost, cheap_casts, cheap_path = opts[0]
                if revenue - cost <= 0:
                    continue
                per_cast = (revenue - cost) / casts
                out.append(CraftRow(
                    item_id, item['name'], recipe.get('category'), self.skill(item_id, recipe),
                    cost, revenue, revenue - cost, casts, per_cast, per_cast * 3600 / self.s.cast_seconds,
                    price['available'], path, revenue - cheap_cost, cheap_casts, cheap_path))
        out.sort(key=lambda r: -r.per_hour)
        return out
```

`opts[0]` is the cheapest option because `pareto` sorts by price first.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_items.py tests/test_craft.py -q`
Expected: PASS (10 passed)

- [ ] **Step 6: Commit**

```bash
git add src/anvilbook/items.py src/anvilbook/craft.py tests/test_items.py tests/test_craft.py
git commit -m "feat: recursive buy-or-craft profit calculator

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Watcher and API

**Files:**
- Create: `src/anvilbook/watcher.py`, `src/anvilbook/app.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `read_snapshot`, `DecodeError` (Task 1); `Store` (Task 2); `load_items`, `Calculator`, `CraftSettings` (Task 3).
- Produces:
  - `class Importer(store: Store)` with `status: dict` (keys `path, found, last_import, last_error`) and `run(force: bool = False) -> int | None`
  - `create_app(data_dir: Path | None = None, watch: bool = True) -> FastAPI`
  - `run() -> None` (console script entry)
  - HTTP endpoints listed in the spec. `GET /api/sellthrough` query params are `from` and `to`.

- [ ] **Step 1: Write the failing tests**

`tests/test_app.py`:

```python
import json

import pytest
from fastapi.testclient import TestClient

from anvilbook.app import create_app
from lua_fixture import entry, savedvariables


def recipe(skill, reagents, amount=(1, 1)):
    return {'amount': list(amount), 'requiredSkill': skill, 'category': 'Mining',
            'reagents': [{'itemId': i, 'amount': n} for i, n in reagents]}


ITEMS = [
    {'itemId': 2770, 'name': 'Copper Ore'},
    {'itemId': 2771, 'name': 'Tin Ore'},
    {'itemId': 2840, 'name': 'Copper Bar', 'createdBy': [recipe(1, [(2770, 1)])]},
    {'itemId': 3576, 'name': 'Tin Bar', 'createdBy': [recipe(65, [(2771, 1)])]},
    {'itemId': 2841, 'name': 'Bronze Bar', 'createdBy': [recipe(65, [(2840, 1), (3576, 1)], (2, 2))]},
]
PRICES = {2770: 57, 2771: 200, 2840: 73, 3576: 248, 2841: 220}


@pytest.fixture
def env(tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    (data / 'items.json').write_text(json.dumps(ITEMS))
    sv = tmp_path / 'Auctionator.lua'
    sv.write_bytes(savedvariables({str(i): entry(p, 2453, 100) for i, p in PRICES.items()}))
    with TestClient(create_app(data, watch=False)) as client:
        assert client.put('/api/settings', json={'savedvariables_path': str(sv)}).status_code == 200
        yield client, sv


def test_import_and_crafts(env):
    client, _ = env
    assert client.post('/api/import').json()['scan_id'] == 1
    assert client.post('/api/import').json()['scan_id'] is None
    names = [r['name'] for r in client.get('/api/crafts').json()]
    assert 'Bronze Bar' in names
    assert client.get('/api/status').json()['scans'] == 1


def test_search_and_history(env):
    client, _ = env
    client.post('/api/import')
    hits = client.get('/api/items/search', params={'q': 'bron'}).json()
    assert [h['item_id'] for h in hits] == [2841]
    points = client.get('/api/items/2841/history').json()['points']
    assert [(p['min_price'], p['available']) for p in points] == [(220, 100)]
    assert client.get('/api/items/999999/history').status_code == 404


def test_sellthrough_between_two_scans(env):
    client, sv = env
    client.post('/api/import')
    assert client.get('/api/sellthrough').json()['rows'] == []
    sv.write_bytes(savedvariables({'2841': entry(220, 2454, 40)}))
    client.post('/api/import')
    res = client.get('/api/sellthrough').json()
    assert (res['from'], res['to']) == (1, 2)
    bronze = next(r for r in res['rows'] if r['item_id'] == 2841)
    assert (bronze['change'], bronze['name']) == (-60, 'Bronze Bar')


def test_empty_database_is_not_stored(env):
    client, sv = env
    sv.write_bytes(savedvariables({'version': 2}))
    res = client.post('/api/import').json()
    assert res['scan_id'] is None
    assert 'no price data' in res['last_error']
    assert client.get('/api/scans').json() == []


def test_missing_file_reports_status(env):
    client, sv = env
    sv.unlink()
    res = client.post('/api/import').json()
    assert res['found'] is False


def test_bad_settings_are_rejected(env):
    client, _ = env
    assert client.put('/api/settings', json={'bogus': 1}).status_code == 400
    assert client.put('/api/settings', json={'min_listed': 'x'}).status_code == 400


def test_index_is_served(env):
    client, _ = env
    assert 'anvilbook' in client.get('/').text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_app.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'anvilbook.app'`

- [ ] **Step 3: Write the watcher**

`src/anvilbook/watcher.py`:

```python
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

from .importer import DecodeError, read_snapshot
from .store import Store

log = logging.getLogger(__name__)


class Importer:
    def __init__(self, store: Store):
        self.store = store
        self.status = {'path': None, 'found': False, 'last_import': None, 'last_error': None}
        self._mtime: float | None = None

    def _error(self, message: str) -> None:
        if message != self.status['last_error']:
            log.warning(message)
        self.status['last_error'] = message

    def run(self, force: bool = False) -> int | None:
        s = self.store.settings()
        path = Path(s['savedvariables_path']).expanduser()
        self.status['path'] = str(path)
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            self.status['found'] = False
            self._error('SavedVariables file not found')
            return None
        self.status['found'] = True
        if mtime == self._mtime and not force:
            return None
        text = path.read_bytes()
        file_hash = hashlib.sha256(text).hexdigest()
        if self.store.has_hash(file_hash):
            self._mtime = mtime
            return None
        try:
            snap = read_snapshot(text, s['realm'])
        except DecodeError as e:
            # WoW can be in the middle of a write; keep _mtime unset so the next poll retries.
            self._error(f'decode failed: {e}')
            return None
        self._mtime = mtime
        if not snap.prices:
            self._error('The file has no price data. Scan the AH, then /reload.')
            return None
        scan_id = self.store.add_scan(snap, datetime.fromtimestamp(mtime, timezone.utc), file_hash)
        self.status['last_import'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        self.status['last_error'] = None
        log.info('imported scan %s with %d items', scan_id, len(snap.prices))
        return scan_id
```

- [ ] **Step 4: Write the app**

`src/anvilbook/app.py`:

```python
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

import uvicorn
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from .craft import Calculator, CraftSettings
from .items import load_items
from .store import Store
from .watcher import Importer

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / 'static'
POLL_SECONDS = 5


def create_app(data_dir: Path | None = None, watch: bool = True) -> FastAPI:
    data_dir = Path(data_dir or os.environ.get('ANVILBOOK_DATA') or Path.home() / '.local/share/anvilbook')
    data_dir.mkdir(parents=True, exist_ok=True)
    store = Store(data_dir / 'anvilbook.db')
    importer = Importer(store)
    cache: dict[str, dict[int, dict]] = {}

    def items() -> dict[int, dict]:
        if 'items' not in cache:
            cache['items'] = load_items(data_dir / 'items.json')
        return cache['items']

    async def watch_loop() -> None:
        while True:
            try:
                await asyncio.to_thread(importer.run)
            except Exception:
                log.exception('watcher step failed')
            await asyncio.sleep(POLL_SECONDS)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await asyncio.to_thread(items)
        task = asyncio.create_task(watch_loop()) if watch else None
        yield
        if task:
            task.cancel()

    app = FastAPI(title='anvilbook', lifespan=lifespan)

    @app.get('/')
    def index():
        return FileResponse(STATIC / 'index.html')

    @app.get('/api/status')
    def status():
        return {**importer.status, 'scans': len(store.scans())}

    @app.post('/api/import')
    def do_import():
        return {'scan_id': importer.run(force=True), **importer.status}

    @app.get('/api/scans')
    def scans():
        return store.scans()

    @app.get('/api/crafts')
    def crafts():
        scan_id = store.latest_scan_id()
        if scan_id is None:
            return []
        calc = Calculator(items(), store.prices(scan_id), store.vendor_prices(),
                          CraftSettings.from_dict(store.settings()))
        return [asdict(r) for r in calc.rows()]

    @app.get('/api/items/search')
    def search(q: str, limit: int = 20):
        q = q.lower()
        known = items()
        hits = [{'item_id': i, 'name': known[i]['name'], 'icon': known[i]['icon']}
                for i in store.item_ids() if i in known and q in known[i]['name'].lower()]
        return sorted(hits, key=lambda h: h['name'])[:limit]

    @app.get('/api/items/{item_id}/history')
    def history(item_id: int):
        item = items().get(item_id)
        if not item:
            raise HTTPException(404, 'unknown item')
        return {'item_id': item_id, 'name': item['name'], 'points': store.history(item_id)}

    @app.get('/api/sellthrough')
    def sellthrough(from_id: int | None = Query(None, alias='from'), to_id: int | None = Query(None, alias='to')):
        ids = [s['id'] for s in store.scans()]
        if from_id is None or to_id is None:
            if len(ids) < 2:
                return {'from': None, 'to': None, 'rows': []}
            from_id, to_id = ids[-2], ids[-1]
        known = items()
        rows = store.sellthrough(from_id, to_id)
        for r in rows:
            r['name'] = (known.get(r['item_id']) or {}).get('name') or str(r['item_id'])
        return {'from': from_id, 'to': to_id, 'rows': rows}

    @app.get('/api/settings')
    def get_settings():
        return store.settings()

    @app.put('/api/settings')
    def put_settings(values: dict = Body(...)):
        try:
            CraftSettings.from_dict({**store.settings(), **values})
            return store.save_settings(values)
        except (KeyError, ValueError, TypeError, AttributeError) as e:
            raise HTTPException(400, str(e))

    return app


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(create_app(), host='127.0.0.1', port=int(os.environ.get('ANVILBOOK_PORT', 8765)))
```

- [ ] **Step 5: Create a placeholder page so the index test can pass**

`src/anvilbook/static/index.html` (Task 5 replaces it with the full UI):

```html
<!doctype html><title>anvilbook</title>
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest -q`
Expected: PASS (all tests, 44 passed)

- [ ] **Step 7: Commit**

```bash
git add src/anvilbook/watcher.py src/anvilbook/app.py src/anvilbook/static/index.html tests/test_app.py
git commit -m "feat: file watcher and JSON API

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: UI

**Files:**
- Modify: `src/anvilbook/static/index.html` (replace the placeholder)

**Interfaces:**
- Consumes: the API from Task 4. Craft rows have the `CraftRow` fields. Sell-through response is `{from, to, rows}`. History response is `{item_id, name, points: [{scan_id, file_mtime, min_price, available}]}`.

- [ ] **Step 1: Write the page**

`src/anvilbook/static/index.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>anvilbook</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/uplot@1.6.32/dist/uPlot.min.css">
<script src="https://cdn.jsdelivr.net/npm/uplot@1.6.32/dist/uPlot.iife.min.js"></script>
<style>
:root { --bg:#fff; --fg:#1b1b1f; --muted:#6b6b76; --line:#e3e3e8; --accent:#b8860b; --bad:#c0392b; --good:#2e8b57; --series2:#4a78c2; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#16161a; --fg:#e8e8ee; --muted:#9a9aa6; --line:#2c2c33; --accent:#e0b04a; --bad:#e06c5c; --good:#5cbf8a; --series2:#7aa2e8; }
}
body { margin:0; font:14px/1.4 system-ui, sans-serif; background:var(--bg); color:var(--fg); }
header { display:flex; gap:1rem; align-items:center; padding:.6rem 1rem; border-bottom:1px solid var(--line); flex-wrap:wrap; }
header h1 { font-size:1rem; margin:0; color:var(--accent); }
nav button { background:none; border:0; border-bottom:2px solid transparent; color:var(--muted); padding:.3rem .6rem; cursor:pointer; font:inherit; }
nav button.active { color:var(--fg); border-bottom-color:var(--accent); }
#status { margin-left:auto; color:var(--muted); font-size:12px; }
#status.error { color:var(--bad); }
main { padding:1rem; }
section { display:none; }
section.active { display:block; }
.wrap { overflow-x:auto; }
table { border-collapse:collapse; width:100%; }
th, td { padding:.3rem .5rem; border-bottom:1px solid var(--line); text-align:right; white-space:nowrap; }
th:first-child, td:first-child { text-align:left; }
th { cursor:pointer; user-select:none; color:var(--muted); font-weight:600; position:sticky; top:0; background:var(--bg); }
tbody tr { cursor:pointer; }
tr.detail td { text-align:left; white-space:normal; color:var(--muted); }
.pos { color:var(--good); }
.neg { color:var(--bad); }
.note { color:var(--muted); font-size:12px; margin:.5rem 0; }
label { display:block; margin:.6rem 0; }
input, textarea, select, button { font:inherit; background:var(--bg); color:var(--fg); border:1px solid var(--line); padding:.3rem .5rem; }
textarea { display:block; width:100%; max-width:40rem; height:6rem; font-family:monospace; }
input[type=text] { width:100%; max-width:40rem; }
</style>
</head>
<body>
<header>
  <h1>anvilbook</h1>
  <nav>
    <button data-tab="crafts" class="active">Crafts</button>
    <button data-tab="history">History</button>
    <button data-tab="sellthrough">Sell-through</button>
    <button data-tab="settings">Settings</button>
  </nav>
  <button id="import">Import now</button>
  <span id="status"></span>
</header>
<main>
  <section id="crafts" class="active">
    <p class="note">Best path by profit per cast. Click a row to see the cheapest path.</p>
    <div class="wrap"><table id="crafts-table"></table></div>
  </section>
  <section id="history">
    <input id="search" type="text" placeholder="Search an item" autocomplete="off">
    <select id="search-results"></select>
    <h3 id="history-title"></h3>
    <div id="chart"></div>
  </section>
  <section id="sellthrough">
    <label>From <select id="st-from"></select></label>
    <label>To <select id="st-to"></select></label>
    <p class="note">A drop in listed count means sales or expired auctions. Green: fewer listed (selling).</p>
    <div class="wrap"><table id="st-table"></table></div>
  </section>
  <section id="settings">
    <form id="settings-form"></form>
  </section>
</main>
<script>
const $ = s => document.querySelector(s);
const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

async function api(path, opts) {
  const r = await fetch(path, opts);
  const body = await r.json();
  if (!r.ok) throw new Error(body.detail || r.statusText);
  return body;
}

function money(c) {
  if (c == null) return '';
  const sign = c < 0 ? '-' : '';
  c = Math.round(Math.abs(c));
  const g = Math.floor(c / 10000), s = Math.floor(c / 100) % 100, cu = String(c % 100).padStart(2, '0');
  return sign + (g ? `${g}g ${String(s).padStart(2, '0')}s ${cu}c` : `${s}s ${cu}c`);
}

function renderTable(el, cols, rows, onRowClick) {
  const key = el.dataset.sortKey, dir = Number(el.dataset.sortDir || -1);
  const sorted = key ? [...rows].sort((a, b) => {
    const x = a[key] ?? -Infinity, y = b[key] ?? -Infinity;
    return (x > y ? 1 : x < y ? -1 : 0) * dir;
  }) : rows;
  el.innerHTML = '';
  const head = el.createTHead().insertRow();
  for (const c of cols) {
    const th = document.createElement('th');
    th.textContent = c.label + (c.key === key ? (dir > 0 ? ' ▲' : ' ▼') : '');
    th.onclick = () => {
      el.dataset.sortDir = c.key === key ? -dir : -1;
      el.dataset.sortKey = c.key;
      renderTable(el, cols, rows, onRowClick);
    };
    head.appendChild(th);
  }
  const body = el.createTBody();
  for (const r of sorted) {
    const tr = body.insertRow();
    for (const c of cols) {
      const td = tr.insertCell();
      td.textContent = c.fmt ? c.fmt(r[c.key], r) : (r[c.key] ?? '');
      if (c.cls) td.className = c.cls(r[c.key], r);
    }
    if (onRowClick) tr.onclick = () => onRowClick(r, tr);
  }
}

const craftCols = [
  {key: 'name', label: 'Item'},
  {key: 'profession', label: 'Profession'},
  {key: 'skill', label: 'Skill'},
  {key: 'cost', label: 'Cost', fmt: money},
  {key: 'revenue', label: 'Net sale', fmt: money},
  {key: 'profit', label: 'Profit', fmt: money},
  {key: 'casts', label: 'Casts', fmt: v => v.toFixed(1)},
  {key: 'per_cast', label: 'Per cast', fmt: money},
  {key: 'per_hour', label: 'Per hour', fmt: money},
  {key: 'listed', label: 'Listed'},
];

async function loadCrafts() {
  const rows = await api('/api/crafts');
  renderTable($('#crafts-table'), craftCols, rows, (r, tr) => {
    const next = tr.nextElementSibling;
    if (next && next.classList.contains('detail')) { next.remove(); return; }
    const d = tr.parentNode.insertRow(tr.sectionRowIndex + 1);
    d.className = 'detail';
    const td = d.insertCell();
    td.colSpan = craftCols.length;
    td.textContent = `Best per cast: ${r.path}. Cheapest path: ${money(r.cheapest_profit)} profit in ` +
      `${r.cheapest_casts.toFixed(1)} casts, ${r.cheapest_path}.`;
  });
}

let chart, searchTimer;
$('#search').oninput = () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(async () => {
    const q = $('#search').value.trim();
    if (q.length < 2) return;
    const hits = await api('/api/items/search?q=' + encodeURIComponent(q));
    const sel = $('#search-results');
    sel.innerHTML = '';
    for (const h of hits) sel.add(new Option(h.name, h.item_id));
    if (hits.length) showHistory(hits[0].item_id);
  }, 250);
};
$('#search-results').onchange = e => showHistory(e.target.value);

async function showHistory(id) {
  const h = await api(`/api/items/${id}/history`);
  $('#history-title').textContent = h.name;
  const data = [
    h.points.map(p => Date.parse(p.file_mtime) / 1000),
    h.points.map(p => p.min_price == null ? null : p.min_price / 10000),
    h.points.map(p => p.available),
  ];
  const axis = {stroke: css('--muted'), grid: {stroke: css('--line')}, ticks: {stroke: css('--line')}};
  const opts = {
    width: Math.min(900, $('main').clientWidth - 20), height: 320,
    series: [{}, {label: 'Lowest price', stroke: css('--accent'), scale: 'g', value: (u, v) => v == null ? '' : money(v * 10000)},
             {label: 'Listed', stroke: css('--series2'), scale: 'n'}],
    axes: [axis, {...axis, scale: 'g', label: 'gold'}, {...axis, scale: 'n', side: 1, label: 'listed', grid: {show: false}}],
  };
  if (chart) chart.destroy();
  chart = new uPlot(opts, data, $('#chart'));
}

async function loadScans() {
  const scans = await api('/api/scans');
  for (const sel of [$('#st-from'), $('#st-to')]) {
    sel.innerHTML = '';
    for (const s of scans) sel.add(new Option(`#${s.id} ${new Date(s.file_mtime).toLocaleString()} (${s.items} items)`, s.id));
  }
  if (scans.length >= 2) {
    $('#st-from').value = scans[scans.length - 2].id;
    $('#st-to').value = scans[scans.length - 1].id;
  }
}

async function loadSellthrough() {
  const f = $('#st-from').value, t = $('#st-to').value;
  if (!f || !t || f === t) {
    $('#st-table').innerHTML = '<tr><td>Import at least 2 scans, and pick 2 different scans.</td></tr>';
    return;
  }
  const res = await api(`/api/sellthrough?from=${f}&to=${t}`);
  renderTable($('#st-table'), [
    {key: 'name', label: 'Item'},
    {key: 'from_available', label: 'Listed before'},
    {key: 'to_available', label: 'Listed after'},
    {key: 'change', label: 'Change', cls: v => v < 0 ? 'pos' : v > 0 ? 'neg' : ''},
    {key: 'from_price', label: 'Price before', fmt: money},
    {key: 'to_price', label: 'Price after', fmt: money},
  ], res.rows);
}
$('#st-from').onchange = loadSellthrough;
$('#st-to').onchange = loadSellthrough;

async function loadSettings() {
  const s = await api('/api/settings');
  const f = $('#settings-form');
  f.innerHTML = '';
  const field = (key, label, type) => {
    const l = document.createElement('label');
    l.textContent = label + ' ';
    const i = document.createElement(type === 'json' ? 'textarea' : 'input');
    if (type !== 'json') i.type = type;
    if (type === 'number') i.step = 'any';
    i.name = key;
    i.dataset.kind = type;
    i.value = type === 'json' ? JSON.stringify(s[key], null, 2) : (s[key] ?? '');
    l.appendChild(i);
    f.appendChild(l);
  };
  field('savedvariables_path', 'SavedVariables file', 'text');
  field('realm', 'Realm (empty = first realm in the file)', 'text');
  field('skills', 'Profession caps (JSON)', 'json');
  field('skill_overrides', 'Forever recipe levels, item id to skill (JSON)', 'json');
  field('max_use_level', 'Max use level', 'number');
  field('min_listed', 'Min listed', 'number');
  field('cast_seconds', 'Cast seconds', 'number');
  field('ah_cut', 'AH cut (0.05 = 5%)', 'number');
  const save = document.createElement('button');
  save.textContent = 'Save';
  const msg = document.createElement('span');
  msg.className = 'note';
  f.append(save, msg);
  f.onsubmit = async e => {
    e.preventDefault();
    try {
      const out = {};
      for (const el of f.elements) {
        if (!el.name) continue;
        const k = el.dataset.kind;
        out[el.name] = k === 'json' ? JSON.parse(el.value) : k === 'number' ? Number(el.value) : (el.value || null);
      }
      await api('/api/settings', {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(out)});
      msg.textContent = ' Saved.';
      loadCrafts();
    } catch (err) {
      msg.textContent = ' ' + err.message;
    }
  };
}

let lastScans = null;
async function refreshStatus() {
  try {
    const s = await api('/api/status');
    const el = $('#status');
    el.textContent = s.last_error || `${s.scans} scans. Last import: ${s.last_import ? new Date(s.last_import).toLocaleString() : 'none since start'}`;
    el.className = s.last_error ? 'error' : '';
    if (s.scans !== lastScans) {
      lastScans = s.scans;
      loadCrafts();
      await loadScans();
      loadSellthrough();
    }
  } catch (err) {
    $('#status').textContent = 'Server not reachable';
    $('#status').className = 'error';
  }
}

$('#import').onclick = async () => { await api('/api/import', {method: 'POST'}); refreshStatus(); };
for (const b of document.querySelectorAll('nav button')) {
  b.onclick = () => {
    document.querySelectorAll('nav button, section').forEach(e => e.classList.remove('active'));
    b.classList.add('active');
    $('#' + b.dataset.tab).classList.add('active');
  };
}

refreshStatus();
loadSettings();
setInterval(refreshStatus, 5000);
</script>
</body>
</html>
```

- [ ] **Step 2: Run the full test suite**

Run: `uv run pytest -q`
Expected: PASS (44 passed). `test_index_is_served` still finds "anvilbook" in the page.

- [ ] **Step 3: Smoke-test the real server**

Run: `ANVILBOOK_PORT=8765 uv run anvilbook` in the background. The first start downloads `items.json` (about 35 MB).
Then run:

```bash
curl -s 127.0.0.1:8765/api/status
curl -s 127.0.0.1:8765/api/settings
curl -s -o /dev/null -w '%{http_code}\n' 127.0.0.1:8765/
```

Expected: status JSON with `"found": true` and the SavedVariables path, settings JSON with the defaults, and `200` for the page. Stop the server after the check.

- [ ] **Step 4: Commit**

```bash
git add src/anvilbook/static/index.html
git commit -m "feat: crafts, history, sell-through, and settings UI

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

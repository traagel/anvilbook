import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from .disenchant import DEFAULT_TABLE
from .importer import Snapshot

DEFAULT_SETTINGS = {
    'savedvariables_path': '',
    'export_path': '',
    'character': None,
    'realm': None,
    'skills': {'Blacksmithing': 120, 'Mining': 99},
    'skill_overrides': {'3490': 100},
    'max_use_level': 20,
    'min_listed': 3,
    'min_scan_items': 100,
    'cast_seconds': 3,
    'ah_cut': 0.05,
    'assume_enchanter': False,
    'disenchant_table': DEFAULT_TABLE,
    'min_disenchant_samples': 20,
    'server_url': '',
    'server_username': '',
    'server_token': '',
    'push_prices': False,
    'published_characters': {},
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

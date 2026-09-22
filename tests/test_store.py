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

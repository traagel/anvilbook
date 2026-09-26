import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from anvilbook.server.api import create_server

URL = os.environ.get('ANVILBOOK_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not URL, reason='ANVILBOOK_TEST_DATABASE_URL is not set')

NOW = datetime.now(timezone.utc)
REALM = 'Classic Beta PvP'


@pytest.fixture
def client(database):
    with TestClient(create_server(database)) as client:
        token = client.post('/api/register',
                            json={'username': 'thordak', 'password': 'a long password'}).json()['token']
        headers = {'Authorization': f'Bearer {token}'}
        client.post('/api/push/scan', headers=headers, json={
            'realm': REALM, 'taken_at': (NOW - timedelta(hours=2)).isoformat(),
            'prices': [{'item_id': 2770, 'min_price': 60, 'available': 100, 'name': 'Copper Ore'},
                       {'item_id': 999999, 'min_price': 500, 'available': 3, 'name': 'Forever Ingot'}]})
        client.post('/api/push/scan', headers=headers, json={
            'realm': REALM, 'taken_at': NOW.isoformat(),
            'prices': [{'item_id': 2770, 'min_price': 57, 'available': 400, 'name': 'Copper Ore'}]})
        client.post('/api/push/character', headers=headers, json={
            'realm': REALM, 'name': 'Thordak', 'published': True,
            'professions': {'Blacksmithing': {'rank': 148, 'maxRank': 150}}, 'recipes': {}})
        client.post('/api/push/character', headers=headers, json={
            'realm': REALM, 'name': 'Hidden', 'published': False,
            'professions': {'Mining': {'rank': 50, 'maxRank': 150}}, 'recipes': {}})
        client.headers.clear()
        yield client


def test_realms_are_listed(client):
    assert [r['name'] for r in client.get('/api/realms').json()] == [REALM]


def test_current_price_comes_from_the_newest_scan(client):
    item = client.get(f'/api/items/2770?realm={REALM}').json()
    assert (item['min_price'], item['available']) == (57, 400)
    assert item['name'] == 'Copper Ore'


def test_items_missing_from_the_item_database_still_work(client):
    found = client.get(f'/api/items/search?q=forever&realm={REALM}').json()
    assert [i['item_id'] for i in found] == [999999]
    assert found[0]['name'] == 'Forever Ingot'


def test_history_returns_a_point_per_scan(client):
    points = client.get(f'/api/items/2770/history?realm={REALM}').json()['points']
    assert [p['min_price'] for p in points] == [60, 57]


def test_unknown_item_or_realm_gives_404(client):
    assert client.get(f'/api/items/123?realm={REALM}').status_code == 404
    assert client.get('/api/items/2770?realm=Nowhere').status_code == 404


def test_only_published_characters_are_listed(client):
    characters = client.get(f'/api/characters?realm={REALM}').json()
    assert [c['name'] for c in characters] == ['Thordak']
    assert characters[0]['professions'] == {'Blacksmithing': 148}


def test_reads_need_no_account(client):
    assert 'Authorization' not in client.headers
    assert client.get('/api/realms').status_code == 200

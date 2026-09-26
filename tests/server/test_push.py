import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from anvilbook.server.api import create_server

URL = os.environ.get('ANVILBOOK_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not URL, reason='ANVILBOOK_TEST_DATABASE_URL is not set')

NOW = datetime.now(timezone.utc)


@pytest.fixture
def client(database):
    with TestClient(create_server(database)) as client:
        token = client.post('/api/register',
                            json={'username': 'thordak', 'password': 'a long password'}).json()['token']
        client.headers['Authorization'] = f'Bearer {token}'
        yield client


def scan(taken_at=NOW, prices=None):
    return {'realm': 'Classic Beta PvP', 'taken_at': taken_at.isoformat(),
            'prices': prices or [{'item_id': 2770, 'min_price': 57, 'available': 400, 'name': 'Copper Ore'}]}


def test_push_stores_the_scan(client, database):
    assert client.post('/api/push/scan', json=scan()).json()['stored'] == 1
    rows = database.query('SELECT item_id, min_price, available, name FROM prices')
    assert rows == [{'item_id': 2770, 'min_price': 57, 'available': 400, 'name': 'Copper Ore'}]


def test_the_same_scan_pushed_twice_replaces_itself(client, database):
    client.post('/api/push/scan', json=scan())
    client.post('/api/push/scan', json=scan(prices=[{'item_id': 2770, 'min_price': 60, 'available': 1}]))
    assert database.query('SELECT count(*) AS n FROM scans')[0]['n'] == 1
    assert database.query('SELECT min_price FROM prices') == [{'min_price': 60}]


@pytest.mark.parametrize('body, expected', [
    (scan(prices=[{'item_id': 2770, 'min_price': 0}]), 'price'),
    (scan(prices=[{'item_id': 2770, 'min_price': 10 ** 12}]), 'price'),
    (scan(taken_at=NOW + timedelta(days=3)), 'taken'),
    (scan(taken_at=NOW - timedelta(days=5)), 'taken'),
    ({'realm': '', 'taken_at': NOW.isoformat(), 'prices': []}, 'realm'),
])
def test_nonsense_is_rejected_with_a_reason(client, body, expected):
    response = client.post('/api/push/scan', json=body)
    assert response.status_code == 400
    assert expected in response.json()['detail'].lower()


def test_too_many_rows_are_rejected(client):
    prices = [{'item_id': i, 'min_price': 10} for i in range(20001)]
    response = client.post('/api/push/scan', json=scan(prices=prices))
    assert response.status_code == 400
    assert 'rows' in response.json()['detail'].lower()


def test_an_oversized_body_is_refused(client):
    huge = scan(prices=[{'item_id': 2770, 'min_price': 57, 'name': 'x' * 6_000_000}])
    response = client.post('/api/push/scan', json=huge)
    assert response.status_code == 400
    assert '5 mb' in response.json()['detail'].lower()


def test_unknown_fields_from_a_newer_client_are_ignored(client):
    body = {**scan(), 'client_version': '9.9.9', 'extra': {'anything': True}}
    body['prices'][0]['future_field'] = 1
    assert client.post('/api/push/scan', json=body).status_code == 200


def test_pushing_needs_a_token(database):
    with TestClient(create_server(database)) as anonymous:
        assert anonymous.post('/api/push/scan', json=scan()).status_code == 401


def test_character_push_and_unpublish(client, database):
    body = {'realm': 'Classic Beta PvP', 'name': 'Thordak', 'published': True,
            'professions': {'Blacksmithing': {'rank': 148, 'maxRank': 150}},
            'recipes': {'3490': {'name': 'Deadly Bronze Poniard', 'minMade': 1, 'maxMade': 1,
                                 'difficulty': 'easy', 'profession': 'Blacksmithing',
                                 'reagents': [{'id': 2841, 'count': 4}]}}}
    assert client.post('/api/push/character', json=body).status_code == 200
    assert database.query('SELECT name, published FROM characters') == [{'name': 'Thordak', 'published': True}]
    assert database.query('SELECT item_id, profession FROM character_recipes') == \
        [{'item_id': 3490, 'profession': 'Blacksmithing'}]

    client.post('/api/push/character', json={**body, 'published': False})
    assert database.query('SELECT published FROM characters') == [{'published': False}]

    assert client.delete('/api/push/character/Classic Beta PvP/Thordak').status_code == 200
    assert database.query('SELECT id FROM characters') == []


def test_rate_limit_stops_a_flood(client):
    for _ in range(20):
        client.post('/api/push/scan', json=scan(taken_at=NOW - timedelta(seconds=_ + 1)))
    flooded = client.post('/api/push/scan', json=scan(taken_at=NOW - timedelta(seconds=99)))
    assert flooded.status_code == 429

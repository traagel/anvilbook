"""Hostile and malformed input. Every case here returned 500, or stored nonsense, once."""
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
        client.headers['Authorization'] = f'Bearer {token}'
        yield client


def scan(taken_at=NOW, prices=None):
    return {'realm': REALM, 'taken_at': taken_at.isoformat(),
            'prices': prices or [{'item_id': 2770, 'min_price': 57, 'available': 400, 'name': 'Copper Ore'}]}


def character(**changes):
    body = {'realm': REALM, 'name': 'Thordak', 'published': True,
            'professions': {'Blacksmithing': {'rank': 148, 'maxRank': 150}},
            'recipes': {'3490': {'name': 'Deadly Bronze Poniard', 'minMade': 1, 'maxMade': 1,
                                 'difficulty': 'easy', 'profession': 'Blacksmithing',
                                 'reagents': [{'id': 2841, 'count': 4}]}}}
    return {**body, **changes}


def test_a_repeated_item_id_does_not_destroy_the_stored_scan(client, database):
    client.post('/api/push/scan', json=scan())
    again = client.post('/api/push/scan', json=scan(prices=[
        {'item_id': 2770, 'min_price': 60}, {'item_id': 2770, 'min_price': 61}]))
    assert again.status_code in (200, 400)
    scans = database.query('SELECT id, item_count FROM scans')
    prices = database.query('SELECT item_id, min_price FROM prices')
    assert len(scans) == 1
    assert scans[0]['item_count'] == len(prices)
    assert len(prices) == 1


@pytest.mark.parametrize('prices', [
    [{'item_id': 2770, 'min_price': 5, 'available': 3_000_000_000}],
    [{'item_id': 10 ** 20, 'min_price': 5}],
    [{'item_id': 2770, 'min_price': 5, 'day_high': 10 ** 20}],
])
def test_out_of_range_numbers_are_refused_not_crashed(client, prices):
    response = client.post('/api/push/scan', json=scan(prices=prices))
    assert response.status_code == 400
    assert response.json()['detail']


def test_a_price_up_to_ten_million_gold_is_accepted(client):
    response = client.post('/api/push/scan', json=scan(prices=[{'item_id': 2770, 'min_price': 10_000_000 * 10_000}]))
    assert response.status_code == 200


def test_a_scan_from_the_future_is_refused(client):
    response = client.post('/api/push/scan', json=scan(taken_at=NOW + timedelta(hours=6)))
    assert response.status_code == 400
    assert 'future' in response.json()['detail'].lower()


def test_an_oversized_body_is_refused(client):
    huge = scan(prices=[{'item_id': 2770, 'min_price': 57, 'name': 'x' * 6_000_000}])
    response = client.post('/api/push/scan', json=huge)
    assert response.status_code == 400
    assert '5 mb' in response.json()['detail'].lower()


def test_an_oversized_chunked_body_is_refused(client, database):
    def chunks():
        head = b'{"realm": "' + REALM.encode() + b'", "taken_at": "' + NOW.isoformat().encode() \
            + b'", "prices": [{"item_id": 2770, "min_price": 57, "name": "'
        yield head
        for _ in range(6):
            yield b'x' * 1_000_000
        yield b'"}]}'

    response = client.post('/api/push/scan', content=chunks(),
                           headers={'Content-Type': 'application/json'})
    assert response.status_code == 400
    assert database.query('SELECT id FROM scans') == []


@pytest.mark.parametrize('body', [
    character(professions={'Mining': 5}),
    character(professions=['Mining']),
    character(recipes={'abc': {'name': 'x', 'reagents': []}}),
    character(professions={'Mining': {'rank': 10 ** 12, 'maxRank': 1}}),
    character(recipes={'3490': {'name': 'x', 'reagents': 'oops'}}),
    character(recipes={'3490': {'name': 'x', 'reagents': [1, 2]}}),
])
def test_malformed_character_payloads_are_refused_not_crashed(client, body):
    response = client.post('/api/push/character', json=body)
    assert response.status_code == 400
    assert response.json()['detail']


def test_a_published_character_never_breaks_the_public_crafts_page(client, tmp_path, database):
    client.post('/api/push/scan', json=scan())
    client.post('/api/push/character', json=character(recipes={'3490': {'name': 'x', 'reagents': 'oops'}}))
    # Whatever the push did, an anonymous visitor must still get an answer.
    with TestClient(create_server(database, data_dir=tmp_path)) as visitor:
        for name in [c['name'] for c in visitor.get(f'/api/characters?realm={REALM}').json()]:
            assert visitor.get(f'/api/crafts?realm={REALM}&character={name}').status_code in (200, 404)


def test_too_many_recipes_are_refused(client):
    recipes = {str(i): {'name': 'x', 'minMade': 1, 'maxMade': 1, 'profession': 'Blacksmithing',
                        'reagents': [{'id': 2841, 'count': 1}]} for i in range(3001)}
    response = client.post('/api/push/character', json=character(recipes=recipes))
    assert response.status_code == 400
    assert 'recipes' in response.json()['detail'].lower()


def test_account_creation_is_rate_limited(database):
    with TestClient(create_server(database)) as flood:
        codes = [flood.post('/api/register',
                            json={'username': f'user{i}', 'password': 'a long password'}).status_code
                 for i in range(12)]
    assert 429 in codes


def test_a_second_account_cannot_reuse_a_name_in_another_case(client, database):
    again = client.post('/api/register', json={'username': 'THORDAK', 'password': 'a long password'})
    assert again.status_code == 409
    assert database.query('SELECT count(*) AS n FROM users')[0]['n'] == 1


def test_search_survives_a_hostile_limit(client):
    client.post('/api/push/scan', json=scan())
    assert client.get(f'/api/items/search?q=copper&realm={REALM}&limit=-1').status_code == 422


def test_search_finds_an_item_the_client_could_not_name(client):
    client.post('/api/push/scan', json=scan(prices=[{'item_id': 999999, 'min_price': 500, 'available': 3}]))
    found = client.get(f'/api/items/search?q=999999&realm={REALM}').json()
    assert [i['item_id'] for i in found] == [999999]

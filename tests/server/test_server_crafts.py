import json
import os
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from anvilbook.server.api import create_server

URL = os.environ.get('ANVILBOOK_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not URL, reason='ANVILBOOK_TEST_DATABASE_URL is not set')

REALM = 'Classic Beta PvP'
ITEMS = [
    {'itemId': 2770, 'name': 'Copper Ore'},
    {'itemId': 2840, 'name': 'Copper Bar',
     'createdBy': [{'amount': [1, 1], 'requiredSkill': 1, 'category': 'Mining',
                    'reagents': [{'itemId': 2770, 'amount': 1}]}]},
]


@pytest.fixture
def client(database, tmp_path):
    (tmp_path / 'items.json').write_text(json.dumps(ITEMS))
    with TestClient(create_server(database, data_dir=tmp_path)) as client:
        token = client.post('/api/register',
                            json={'username': 'thordak', 'password': 'a long password'}).json()['token']
        headers = {'Authorization': f'Bearer {token}'}
        client.post('/api/push/scan', headers=headers, json={
            'realm': REALM, 'taken_at': datetime.now(timezone.utc).isoformat(),
            'prices': [{'item_id': 2770, 'min_price': 57, 'available': 400, 'name': 'Copper Ore'},
                       {'item_id': 2840, 'min_price': 90, 'available': 200, 'name': 'Copper Bar'}]})
        client.post('/api/push/character', headers=headers, json={
            'realm': REALM, 'name': 'Thordak', 'published': True,
            'professions': {'Mining': {'rank': 99, 'maxRank': 150}},
            'recipes': {'2840': {'name': 'Copper Bar', 'minMade': 2, 'maxMade': 2, 'difficulty': 'easy',
                                 'profession': 'Mining', 'reagents': [{'id': 2770, 'count': 1}]}}})
        yield client


def test_crafts_from_the_item_database(client):
    rows = client.get(f'/api/crafts?realm={REALM}').json()
    bar = next(r for r in rows if r['item_id'] == 2840)
    assert bar['cost'] == 57
    assert bar['profit'] == pytest.approx(90 * 0.95 - 57)


def test_a_published_character_uses_its_own_recipes(client):
    rows = client.get(f'/api/crafts?realm={REALM}&character=Thordak').json()
    bar = next(r for r in rows if r['item_id'] == 2840)
    assert bar['difficulty'] == 'easy'
    assert bar['revenue'] == pytest.approx(90 * 0.95 * 2)  # the character's recipe makes 2


def test_unknown_character_or_realm_gives_404(client):
    assert client.get(f'/api/crafts?realm={REALM}&character=Nobody').status_code == 404
    assert client.get('/api/crafts?realm=Nowhere').status_code == 404

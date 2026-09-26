import os

import pytest

URL = os.environ.get('ANVILBOOK_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not URL, reason='ANVILBOOK_TEST_DATABASE_URL is not set')


def test_schema_is_created_and_can_be_reapplied(database):
    from anvilbook.server.db import Database
    Database(URL)  # a second start must not fail
    tables = {r['table_name'] for r in database.query(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}
    assert {'users', 'tokens', 'realms', 'scans', 'prices',
            'characters', 'character_skills', 'character_recipes'} <= tables


def test_query_and_execute_round_trip(database):
    row = database.execute("INSERT INTO realms (name) VALUES (%s) RETURNING id, name", ('Test Realm',))
    assert row['name'] == 'Test Realm'
    assert database.query('SELECT name FROM realms') == [{'name': 'Test Realm'}]


def test_health_endpoint(database):
    import anvilbook
    from fastapi.testclient import TestClient
    from anvilbook.server.api import create_server
    with TestClient(create_server(database)) as client:
        assert client.get('/healthz').json() == {'ok': True, 'version': anvilbook.__version__}

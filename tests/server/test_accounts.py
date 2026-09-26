import os

import pytest
from fastapi.testclient import TestClient

from anvilbook.server.api import create_server

URL = os.environ.get('ANVILBOOK_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not URL, reason='ANVILBOOK_TEST_DATABASE_URL is not set')


@pytest.fixture
def client(database):
    with TestClient(create_server(database)) as client:
        yield client


def test_register_then_login(client):
    registered = client.post('/api/register', json={'username': 'thordak', 'password': 'a long password'})
    assert registered.status_code == 200
    token = registered.json()['token']

    logged_in = client.post('/api/login', json={'username': 'thordak', 'password': 'a long password'})
    assert logged_in.status_code == 200
    assert logged_in.json()['token'] != token  # a new session, both valid


def test_duplicate_username_is_rejected(client):
    client.post('/api/register', json={'username': 'thordak', 'password': 'a long password'})
    again = client.post('/api/register', json={'username': 'thordak', 'password': 'another password'})
    assert again.status_code == 409
    assert 'taken' in again.json()['detail'].lower()


@pytest.mark.parametrize('body, field', [
    ({'username': 'ab', 'password': 'a long password'}, 'username'),
    ({'username': 'thordak', 'password': 'short'}, 'password'),
])
def test_bad_credentials_are_explained(client, body, field):
    response = client.post('/api/register', json=body)
    assert response.status_code == 400
    assert field.lower() in response.json()['detail'].lower()


def test_wrong_password_and_unknown_user_look_the_same(client):
    client.post('/api/register', json={'username': 'thordak', 'password': 'a long password'})
    wrong = client.post('/api/login', json={'username': 'thordak', 'password': 'not the password'})
    missing = client.post('/api/login', json={'username': 'nobody', 'password': 'a long password'})
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json() == missing.json()


def test_logout_revokes_the_token(client):
    token = client.post('/api/register', json={'username': 'thordak', 'password': 'a long password'}).json()['token']
    auth = {'Authorization': f'Bearer {token}'}
    assert client.post('/api/logout', headers=auth).status_code == 200
    assert client.post('/api/logout', headers=auth).status_code == 401


@pytest.mark.parametrize('header', [None, 'Bearer nope', 'nonsense'])
def test_missing_or_stale_tokens_give_401(client, header):
    headers = {'Authorization': header} if header else {}
    assert client.delete('/api/account', headers=headers).status_code == 401


def test_delete_account_removes_everything(client, database):
    token = client.post('/api/register', json={'username': 'thordak', 'password': 'a long password'}).json()['token']
    assert client.delete('/api/account', headers={'Authorization': f'Bearer {token}'}).status_code == 200
    assert database.query('SELECT id FROM users') == []
    assert database.query('SELECT token_hash FROM tokens') == []

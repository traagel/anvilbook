import os

import pytest
from fastapi.testclient import TestClient

from anvilbook.server.api import create_server

URL = os.environ.get('ANVILBOOK_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not URL, reason='ANVILBOOK_TEST_DATABASE_URL is not set')


def test_the_page_is_served(database):
    with TestClient(create_server(database)) as client:
        page = client.get('/')
        assert page.status_code == 200
        assert 'anvilbook' in page.text
        assert client.get('/logo.svg').status_code == 200

import os

import pytest

URL = os.environ.get('ANVILBOOK_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not URL, reason='ANVILBOOK_TEST_DATABASE_URL is not set')


@pytest.fixture
def database():
    from anvilbook.server.db import Database
    db = Database(URL)
    db.reset()
    return db

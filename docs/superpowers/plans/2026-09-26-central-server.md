# Central server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A hosted service that collects price scans and character crafting pushed by anvilbook clients, and a public site where anyone can check prices and crafting profits.

**Architecture:** The server lives in this repository under `src/anvilbook/server/`, installed through the optional `server` extra, so the desktop app is untouched. It speaks plain SQL to Postgres and reuses `craft.py`, `items.py`, and `disenchant.py`, so the site and the app compute profits with the same code. The client gains `push.py` and a Share tab, both opt-in.

**Tech Stack:** Python 3.12+, FastAPI, psycopg 3, Postgres, `hashlib.scrypt`, plain JS with uPlot, Docker, k3s.

**Spec:** `docs/superpowers/specs/2026-09-26-central-server-design.md`

## Global Constraints

- Server package: `src/anvilbook/server/`. Client push: `src/anvilbook/push.py`. Deployment: `deploy/`.
- Optional dependency only: `[project.optional-dependencies] server = ["psycopg[binary]>=3.2"]`. The desktop install must not grow.
- The client uses `urllib.request` from the standard library. No new client dependency.
- Passwords: `hashlib.scrypt`, `n=2**15, r=8, p=1`, 16-byte salt, 32-byte key, stored as `scrypt$n$r$p$salt$key`.
- Tokens: 32 random bytes hex encoded, sent as `Authorization: Bearer <token>`, stored only as a SHA-256 hash.
- Limits: 5 MB per request, 20 pushes per hour per account, 20000 price rows per scan, prices from 1 to 1_000_000_00 copper, `taken_at` within 2 days of now.
- Sharing is opt-in: prices and per-character crafting are separate switches, both default off.
- No IP addresses stored. No email, no password reset.
- Server listens on `PORT` (default 8000) and reads `DATABASE_URL`. TLS is the operator's.
- Database tests skip unless `ANVILBOOK_TEST_DATABASE_URL` is set; CI sets it.
- The existing 102 tests keep passing untouched.
- Commit messages end with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.
- Comments: why-only, no narration.

## Review Focus

These are the inputs most likely to bite a real user. Each has a test in the task that owns the code.

1. **The server is unreachable or slow when a scan is pushed.** The import must still succeed, local data must be kept, and the status bar must say the push failed (Task 7).
2. **The same scan is pushed twice** after a retry or a restart. The second push replaces the first instead of doubling the history (Task 3).
3. **An oversized or absurd payload** (too many rows, negative prices, a `taken_at` from next year) returns a clear 400 rather than storing nonsense or exhausting memory (Task 3).
4. **An item id the item database has never heard of**, which Forever produces, still shows in search and price views with the name the pusher sent (Task 4).
5. **A stale or revoked token**, and a duplicate username on register, return 401 and 409 with a plain message, never a 500 (Task 2).

---

### Task 1: Server skeleton, database, health

**Files:**
- Create: `src/anvilbook/server/__init__.py`, `src/anvilbook/server/db.py`, `src/anvilbook/server/schema.sql`, `src/anvilbook/server/api.py`
- Create: `deploy/Dockerfile`, `deploy/k8s.yaml`
- Modify: `pyproject.toml`
- Test: `tests/server/conftest.py`, `tests/server/test_db.py`

**Interfaces:**
- Produces: `Database(url: str)` with `.connect()` (context manager yielding a psycopg connection with `dict_row`), `.query(sql, args=()) -> list[dict]`, `.execute(sql, args=()) -> dict | None`, and `.reset()` for tests. `create_server(database: Database) -> FastAPI` with `GET /healthz`.

- [ ] **Step 1: Add the extra and the test fixture**

`pyproject.toml`, after `dependencies`:

```toml
[project.optional-dependencies]
server = ["psycopg[binary]>=3.2"]
```

`tests/server/conftest.py`:

```python
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
```

- [ ] **Step 2: Write the failing test**

`tests/server/test_db.py`:

```python
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
    from fastapi.testclient import TestClient
    from anvilbook.server.api import create_server
    with TestClient(create_server(database)) as client:
        assert client.get('/healthz').json() == {'ok': True}
```

- [ ] **Step 3: Run it and watch it fail**

Run: `uv run --extra server pytest tests/server -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'anvilbook.server'`, or skips if no database is configured. Start one with
`docker run -d --name anvilbook-pg -e POSTGRES_PASSWORD=dev -p 5433:5432 postgres:17` and
`export ANVILBOOK_TEST_DATABASE_URL=postgresql://postgres:dev@localhost:5433/postgres`.

- [ ] **Step 4: Write the schema**

`src/anvilbook/server/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS tokens (
    token_hash TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS realms (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS scans (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    realm_id BIGINT NOT NULL REFERENCES realms(id),
    taken_at TIMESTAMPTZ NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    item_count INTEGER NOT NULL,
    UNIQUE (user_id, realm_id, taken_at)
);
CREATE TABLE IF NOT EXISTS prices (
    scan_id BIGINT NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    item_id BIGINT NOT NULL,
    name TEXT,
    min_price BIGINT NOT NULL,
    available INTEGER NOT NULL DEFAULT 0,
    day_high BIGINT,
    PRIMARY KEY (scan_id, item_id)
);
CREATE INDEX IF NOT EXISTS prices_item ON prices (item_id);
CREATE TABLE IF NOT EXISTS characters (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    realm_id BIGINT NOT NULL REFERENCES realms(id),
    name TEXT NOT NULL,
    published BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, realm_id, name)
);
CREATE TABLE IF NOT EXISTS character_skills (
    character_id BIGINT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    profession TEXT NOT NULL,
    rank INTEGER NOT NULL,
    max_rank INTEGER NOT NULL,
    PRIMARY KEY (character_id, profession)
);
CREATE TABLE IF NOT EXISTS character_recipes (
    character_id BIGINT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    item_id BIGINT NOT NULL,
    name TEXT,
    min_made INTEGER NOT NULL DEFAULT 1,
    max_made INTEGER NOT NULL DEFAULT 1,
    difficulty TEXT,
    profession TEXT NOT NULL,
    reagents JSONB NOT NULL,
    PRIMARY KEY (character_id, item_id)
);
```

- [ ] **Step 5: Write the database wrapper and the app factory**

`src/anvilbook/server/db.py`:

```python
import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

SCHEMA = (Path(__file__).parent / 'schema.sql').read_text()
TABLES = ['character_recipes', 'character_skills', 'characters', 'prices', 'scans', 'tokens',
          'users', 'realms']


class Database:
    def __init__(self, url: str | None = None):
        self.url = url or os.environ['DATABASE_URL']
        with self.connect() as conn:
            conn.execute(SCHEMA)

    @contextmanager
    def connect(self):
        with psycopg.connect(self.url, row_factory=dict_row, autocommit=True) as conn:
            yield conn

    def query(self, sql: str, args: tuple = ()) -> list[dict]:
        with self.connect() as conn:
            return conn.execute(sql, args).fetchall()

    def execute(self, sql: str, args: tuple = ()) -> dict | None:
        with self.connect() as conn:
            cursor = conn.execute(sql, args)
            return cursor.fetchone() if cursor.description else None

    def reset(self) -> None:
        """Empties every table. Tests only."""
        with self.connect() as conn:
            conn.execute('TRUNCATE ' + ', '.join(TABLES) + ' RESTART IDENTITY CASCADE')
```

`src/anvilbook/server/api.py`:

```python
import logging
import os

from fastapi import FastAPI

from .db import Database

log = logging.getLogger(__name__)


def create_server(database: Database | None = None) -> FastAPI:
    database = database or Database()
    app = FastAPI(title='anvilbook server')

    @app.get('/healthz')
    def healthz():
        database.query('SELECT 1')
        return {'ok': True}

    return app


def run() -> None:
    import uvicorn
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    uvicorn.run(create_server(), host='0.0.0.0', port=int(os.environ.get('PORT', 8000)))
```

Add to `pyproject.toml` scripts: `anvilbook-server = "anvilbook.server.api:run"`.

- [ ] **Step 6: Run the tests**

Run: `uv run --extra server pytest tests/server -q`
Expected: PASS (3 passed)

- [ ] **Step 7: Write the deployment files**

`deploy/Dockerfile`:

```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir '.[server]' && useradd --create-home anvilbook
USER anvilbook
ENV PORT=8000 ANVILBOOK_DATA=/data
EXPOSE 8000
CMD ["anvilbook-server"]
```

`deploy/k8s.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: anvilbook
spec:
  replicas: 1
  selector:
    matchLabels: {app: anvilbook}
  template:
    metadata:
      labels: {app: anvilbook}
    spec:
      containers:
        - name: anvilbook
          image: ghcr.io/traagel/anvilbook-server:latest
          ports: [{containerPort: 8000}]
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef: {name: anvilbook, key: database-url}
          volumeMounts:
            - {name: data, mountPath: /data}
          livenessProbe:
            httpGet: {path: /healthz, port: 8000}
            initialDelaySeconds: 20
          readinessProbe:
            httpGet: {path: /healthz, port: 8000}
      volumes:
        - name: data
          persistentVolumeClaim: {claimName: anvilbook-data}
---
apiVersion: v1
kind: Service
metadata:
  name: anvilbook
spec:
  selector: {app: anvilbook}
  ports: [{port: 80, targetPort: 8000}]
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: anvilbook-data
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests: {storage: 1Gi}
```

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml src/anvilbook/server deploy tests/server
git commit -m "feat(server): database, schema and health endpoint

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Accounts

**Files:**
- Create: `src/anvilbook/server/auth.py`
- Modify: `src/anvilbook/server/api.py`
- Test: `tests/server/test_auth.py`, `tests/server/test_accounts.py`

**Interfaces:**
- Consumes: `Database`, `create_server` (Task 1).
- Produces: `hash_password(password, salt=None) -> str`, `verify_password(password, stored) -> bool`, `new_token() -> tuple[str, str]`, `token_hash(token) -> str`, `check_username(name) -> None`, `check_password(password) -> None` (both raise `ValueError`), and a FastAPI dependency `current_user` returning `{'id': int, 'username': str}`.
  Endpoints: `POST /api/register`, `POST /api/login`, `POST /api/logout`, `DELETE /api/account`, all returning `{'token': str, 'username': str}` except logout and delete which return `{'ok': True}`.

- [ ] **Step 1: Write the failing unit tests**

`tests/server/test_auth.py` (no database needed):

```python
import pytest

from anvilbook.server.auth import (check_password, check_username, hash_password, new_token,
                                   token_hash, verify_password)


def test_password_round_trip():
    stored = hash_password('correct horse battery')
    assert stored.startswith('scrypt$')
    assert verify_password('correct horse battery', stored)
    assert not verify_password('wrong', stored)


def test_same_password_gets_a_different_hash():
    assert hash_password('correct horse battery') != hash_password('correct horse battery')


@pytest.mark.parametrize('stored', ['', 'nonsense', 'scrypt$1$2$3', 'scrypt$a$b$c$d$e'])
def test_broken_hashes_do_not_raise(stored):
    assert verify_password('anything', stored) is False


def test_tokens_are_random_and_only_stored_hashed():
    token, stored = new_token()
    assert len(token) == 64 and token != stored
    assert token_hash(token) == stored
    assert new_token()[0] != token


@pytest.mark.parametrize('name', ['ab', 'x' * 33, 'has space', 'bad/char', ''])
def test_bad_usernames_are_rejected(name):
    with pytest.raises(ValueError):
        check_username(name)


def test_good_username_passes():
    check_username('Thordak_1')


def test_short_passwords_are_rejected():
    with pytest.raises(ValueError):
        check_password('short')
    check_password('long enough password')
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run --extra server pytest tests/server/test_auth.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'anvilbook.server.auth'`

- [ ] **Step 3: Write `auth.py`**

```python
import hashlib
import hmac
import re
import secrets

SCRYPT = {'n': 2 ** 15, 'r': 8, 'p': 1, 'dklen': 32}
USERNAME = re.compile(r'^[A-Za-z0-9_-]{3,32}$')
MIN_PASSWORD = 10


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, **SCRYPT)
    return f"scrypt${SCRYPT['n']}${SCRYPT['r']}${SCRYPT['p']}${salt.hex()}${key.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        kind, n, r, p, salt, key = stored.split('$')
        if kind != 'scrypt':
            return False
        candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r),
                                   p=int(p), dklen=len(key) // 2)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, bytes.fromhex(key))


def new_token() -> tuple[str, str]:
    token = secrets.token_hex(32)
    return token, token_hash(token)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def check_username(name: str) -> None:
    if not USERNAME.match(name or ''):
        raise ValueError('Usernames are 3 to 32 letters, digits, underscores or hyphens')


def check_password(password: str) -> None:
    if len(password or '') < MIN_PASSWORD:
        raise ValueError(f'Passwords need at least {MIN_PASSWORD} characters')
```

- [ ] **Step 4: Run the unit tests**

Run: `uv run --extra server pytest tests/server/test_auth.py -q`
Expected: PASS (14 passed)

- [ ] **Step 5: Write the failing endpoint tests**

`tests/server/test_accounts.py`:

```python
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
```

- [ ] **Step 6: Run them and watch them fail**

Run: `uv run --extra server pytest tests/server/test_accounts.py -q`
Expected: FAIL with 404, because the endpoints do not exist.

- [ ] **Step 7: Add the endpoints to `api.py`**

Inside `create_server`, after `healthz`:

```python
    def user_for(authorization: str | None) -> dict:
        prefix = 'Bearer '
        if not authorization or not authorization.startswith(prefix):
            raise HTTPException(401, 'Sign in first')
        row = database.execute("""
            UPDATE tokens SET last_used_at = now() WHERE token_hash = %s
            RETURNING (SELECT username FROM users WHERE users.id = tokens.user_id) AS username, user_id AS id
            """, (token_hash(authorization[len(prefix):]),))
        if not row:
            raise HTTPException(401, 'Sign in again')
        return row

    def current_user(authorization: str | None = Header(None)) -> dict:
        return user_for(authorization)

    def issue_token(user_id: int) -> str:
        token, stored = new_token()
        database.execute('INSERT INTO tokens (token_hash, user_id) VALUES (%s, %s)', (stored, user_id))
        return token

    @app.post('/api/register')
    def register(body: dict = Body(...)):
        username, password = str(body.get('username') or ''), str(body.get('password') or '')
        try:
            check_username(username)
            check_password(password)
        except ValueError as e:
            raise HTTPException(400, str(e))
        if database.query('SELECT id FROM users WHERE lower(username) = lower(%s)', (username,)):
            raise HTTPException(409, 'That username is taken')
        user = database.execute('INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id',
                                (username, hash_password(password)))
        return {'token': issue_token(user['id']), 'username': username}

    @app.post('/api/login')
    def login(body: dict = Body(...)):
        username, password = str(body.get('username') or ''), str(body.get('password') or '')
        rows = database.query('SELECT id, username, password_hash FROM users WHERE lower(username) = lower(%s)',
                              (username,))
        user = rows[0] if rows else None
        if not user or not verify_password(password, user['password_hash']):
            raise HTTPException(401, 'Wrong username or password')
        return {'token': issue_token(user['id']), 'username': user['username']}

    @app.post('/api/logout')
    def logout(authorization: str | None = Header(None)):
        user_for(authorization)
        database.execute('DELETE FROM tokens WHERE token_hash = %s',
                         (token_hash((authorization or '')[len('Bearer '):]),))
        return {'ok': True}

    @app.delete('/api/account')
    def delete_account(user: dict = Depends(current_user)):
        database.execute('DELETE FROM users WHERE id = %s', (user['id'],))
        return {'ok': True}
```

Imports at the top of `api.py`:

```python
from fastapi import Body, Depends, FastAPI, Header, HTTPException

from .auth import check_password, check_username, hash_password, new_token, token_hash, verify_password
```

- [ ] **Step 8: Run the endpoint tests**

Run: `uv run --extra server pytest tests/server -q`
Expected: PASS (all green)

- [ ] **Step 9: Commit**

```bash
git add src/anvilbook/server tests/server
git commit -m "feat(server): accounts with username and password

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Push endpoints

**Files:**
- Create: `src/anvilbook/server/push_api.py`
- Modify: `src/anvilbook/server/api.py`
- Test: `tests/server/test_push.py`

**Interfaces:**
- Consumes: `Database`, `current_user` (Tasks 1 and 2).
- Produces: `add_push_routes(app, database, current_user)`, `realm_id(database, name) -> int`, and `within_size(request) -> None`.
  `reagents` arrives as a JSON array of `{'id': int, 'count': int}` and is stored as a JSONB array; Task 7's client normalizes the game's Lua table into that shape.
  Endpoints: `POST /api/push/scan`, `POST /api/push/character`, `DELETE /api/push/character/{realm}/{name}`.

- [ ] **Step 1: Write the failing tests**

`tests/server/test_push.py`:

```python
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
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run --extra server pytest tests/server/test_push.py -q`
Expected: FAIL with 404 on every push.

- [ ] **Step 3: Write `push_api.py`**

```python
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import Body, Depends, HTTPException, Request

MAX_ROWS = 20000
MAX_BYTES = 5 * 1024 * 1024
MIN_PRICE, MAX_PRICE = 1, 1_000_000_00
AGE_LIMIT = timedelta(days=2)
PUSHES_PER_HOUR = 20


def within_size(request: Request) -> None:
    if int(request.headers.get('content-length') or 0) > MAX_BYTES:
        raise HTTPException(400, 'That upload is larger than the 5 MB limit')


def realm_id(database, name: str) -> int:
    name = (name or '').strip()
    if not (1 <= len(name) <= 64):
        raise HTTPException(400, 'Give the realm name')
    database.execute('INSERT INTO realms (name) VALUES (%s) ON CONFLICT (name) DO NOTHING', (name,))
    return database.query('SELECT id FROM realms WHERE name = %s', (name,))[0]['id']


def _when(value) -> datetime:
    try:
        taken_at = datetime.fromisoformat(str(value))
    except ValueError:
        raise HTTPException(400, 'taken_at must be a date and time')
    taken_at = taken_at if taken_at.tzinfo else taken_at.replace(tzinfo=timezone.utc)
    if abs(datetime.now(timezone.utc) - taken_at) > AGE_LIMIT:
        raise HTTPException(400, 'taken_at must be within 2 days of now')
    return taken_at


def _rows(prices) -> list[tuple]:
    if not isinstance(prices, list) or not prices:
        raise HTTPException(400, 'The scan has no prices')
    if len(prices) > MAX_ROWS:
        raise HTTPException(400, f'A scan may hold at most {MAX_ROWS} rows')
    rows = []
    for price in prices:
        try:
            item_id, value = int(price['item_id']), int(price['min_price'])
            available, high = int(price.get('available') or 0), price.get('day_high')
        except (KeyError, TypeError, ValueError):
            raise HTTPException(400, 'Each price needs item_id and min_price')
        if not MIN_PRICE <= value <= MAX_PRICE:
            raise HTTPException(400, f'A price must be between {MIN_PRICE} and {MAX_PRICE} copper')
        if item_id <= 0 or available < 0:
            raise HTTPException(400, 'item_id and available must be positive')
        rows.append((item_id, str(price.get('name') or '')[:120] or None, value, available,
                     int(high) if high else None))
    return rows


def add_push_routes(app, database, current_user) -> None:
    recent: dict[int, list[float]] = defaultdict(list)

    def within_rate_limit(user_id: int) -> None:
        cutoff = time.monotonic() - 3600
        recent[user_id] = [t for t in recent[user_id] if t > cutoff]
        if len(recent[user_id]) >= PUSHES_PER_HOUR:
            raise HTTPException(429, f'At most {PUSHES_PER_HOUR} pushes an hour. Try later.')
        recent[user_id].append(time.monotonic())

    @app.post('/api/push/scan')
    def push_scan(body: dict = Body(...), user: dict = Depends(current_user),
                  _size: None = Depends(within_size)):
        within_rate_limit(user['id'])
        realm = realm_id(database, body.get('realm'))
        taken_at = _when(body.get('taken_at'))
        rows = _rows(body.get('prices'))
        database.execute('DELETE FROM scans WHERE user_id = %s AND realm_id = %s AND taken_at = %s',
                         (user['id'], realm, taken_at))
        scan = database.execute(
            'INSERT INTO scans (user_id, realm_id, taken_at, item_count) VALUES (%s, %s, %s, %s) RETURNING id',
            (user['id'], realm, taken_at, len(rows)))
        with database.connect() as conn:
            with conn.cursor() as cursor:
                cursor.executemany(
                    'INSERT INTO prices (scan_id, item_id, name, min_price, available, day_high)'
                    ' VALUES (%s, %s, %s, %s, %s, %s)',
                    [(scan['id'], *row) for row in rows])
        return {'stored': len(rows), 'scan_id': scan['id']}

    @app.post('/api/push/character')
    def push_character(body: dict = Body(...), user: dict = Depends(current_user),
                       _size: None = Depends(within_size)):
        within_rate_limit(user['id'])
        realm = realm_id(database, body.get('realm'))
        name = str(body.get('name') or '').strip()
        if not (1 <= len(name) <= 48):
            raise HTTPException(400, 'Give the character name')
        character = database.execute("""
            INSERT INTO characters (user_id, realm_id, name, published, updated_at)
            VALUES (%s, %s, %s, %s, now())
            ON CONFLICT (user_id, realm_id, name)
            DO UPDATE SET published = EXCLUDED.published, updated_at = now()
            RETURNING id""", (user['id'], realm, name, bool(body.get('published'))))
        database.execute('DELETE FROM character_skills WHERE character_id = %s', (character['id'],))
        database.execute('DELETE FROM character_recipes WHERE character_id = %s', (character['id'],))
        for profession, skill in (body.get('professions') or {}).items():
            database.execute(
                'INSERT INTO character_skills (character_id, profession, rank, max_rank) VALUES (%s, %s, %s, %s)',
                (character['id'], str(profession)[:40], int(skill.get('rank') or 0),
                 int(skill.get('maxRank') or 0)))
        for item_id, recipe in (body.get('recipes') or {}).items():
            database.execute("""
                INSERT INTO character_recipes
                    (character_id, item_id, name, min_made, max_made, difficulty, profession, reagents)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (character['id'], int(item_id), str(recipe.get('name') or '')[:120],
                 int(recipe.get('minMade') or 1), int(recipe.get('maxMade') or 1),
                 recipe.get('difficulty'), str(recipe.get('profession') or '')[:40],
                 Jsonb(recipe.get('reagents') or [])))
        return {'ok': True, 'published': bool(body.get('published'))}

    @app.delete('/api/push/character/{realm}/{name}')
    def remove_character(realm: str, name: str, user: dict = Depends(current_user)):
        database.execute("""
            DELETE FROM characters WHERE user_id = %s AND name = %s
              AND realm_id = (SELECT id FROM realms WHERE name = %s)""", (user['id'], name, realm))
        return {'ok': True}
```

Add at the top of `push_api.py`: `from psycopg.types.json import Jsonb`.

In `api.py`, after the account endpoints:

```python
    add_push_routes(app, database, current_user)
```

with `from .push_api import add_push_routes` at the top.

- [ ] **Step 4: Run the tests**

Run: `uv run --extra server pytest tests/server -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/anvilbook/server tests/server
git commit -m "feat(server): price and character push with limits

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Public read endpoints

**Files:**
- Create: `src/anvilbook/server/read_api.py`
- Modify: `src/anvilbook/server/api.py`
- Test: `tests/server/test_reads.py`

**Interfaces:**
- Consumes: `Database` (Task 1), pushed data (Task 3).
- Produces: `add_read_routes(app, database)`, and `latest_prices(database, realm) -> dict[int, dict]` used by Task 5. The spec calls this a view; one `DISTINCT ON` query in Python does the same work with nothing extra to migrate, and every read uses it.
  Endpoints: `GET /api/realms`, `GET /api/items/search`, `GET /api/items/{item_id}`, `GET /api/items/{item_id}/history`, `GET /api/characters`.

- [ ] **Step 1: Write the failing tests**

`tests/server/test_reads.py`:

```python
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
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run --extra server pytest tests/server/test_reads.py -q`
Expected: FAIL with 404 on every read.

- [ ] **Step 3: Write `read_api.py`**

```python
from fastapi import HTTPException, Query

LATEST = """
    SELECT DISTINCT ON (p.item_id) p.item_id, p.name, p.min_price, p.available, p.day_high, s.taken_at
    FROM prices p JOIN scans s ON s.id = p.scan_id
    JOIN realms r ON r.id = s.realm_id
    WHERE r.name = %s
    ORDER BY p.item_id, s.taken_at DESC
"""


def latest_prices(database, realm: str) -> dict[int, dict]:
    return {row['item_id']: row for row in database.query(LATEST, (realm,))}


def add_read_routes(app, database) -> None:
    @app.get('/api/realms')
    def realms():
        return database.query("""
            SELECT r.name, count(DISTINCT s.id) AS scans, max(s.taken_at) AS last_scan
            FROM realms r LEFT JOIN scans s ON s.realm_id = r.id
            GROUP BY r.name ORDER BY r.name""")

    @app.get('/api/items/search')
    def search(q: str, realm: str, limit: int = Query(30, le=100)):
        return database.query(LATEST.replace('WHERE r.name = %s',
                                             'WHERE r.name = %s AND p.name ILIKE %s')
                              + ' LIMIT %s', (realm, f'%{q}%', limit))

    @app.get('/api/items/{item_id}')
    def item(item_id: int, realm: str):
        rows = database.query(LATEST.replace('WHERE r.name = %s', 'WHERE r.name = %s AND p.item_id = %s'),
                              (realm, item_id))
        if not rows:
            raise HTTPException(404, 'No price for that item on that realm')
        return rows[0]

    @app.get('/api/items/{item_id}/history')
    def history(item_id: int, realm: str):
        points = database.query("""
            SELECT s.taken_at, p.min_price, p.available
            FROM prices p JOIN scans s ON s.id = p.scan_id JOIN realms r ON r.id = s.realm_id
            WHERE r.name = %s AND p.item_id = %s
            ORDER BY s.taken_at""", (realm, item_id))
        return {'item_id': item_id, 'realm': realm, 'points': points}

    @app.get('/api/characters')
    def characters(realm: str):
        rows = database.query("""
            SELECT c.name, c.updated_at, s.profession, s.rank
            FROM characters c JOIN realms r ON r.id = c.realm_id
            LEFT JOIN character_skills s ON s.character_id = c.id
            WHERE r.name = %s AND c.published
            ORDER BY c.name""", (realm,))
        out: dict[str, dict] = {}
        for row in rows:
            entry = out.setdefault(row['name'], {'name': row['name'], 'updated_at': row['updated_at'],
                                                 'professions': {}})
            if row['profession']:
                entry['professions'][row['profession']] = row['rank']
        return list(out.values())
```

In `api.py`: `from .read_api import add_read_routes` and `add_read_routes(app, database)`.

- [ ] **Step 4: Run the tests**

Run: `uv run --extra server pytest tests/server -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/anvilbook/server tests/server
git commit -m "feat(server): public price and character reads

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Crafting profits on the server

**Files:**
- Create: `src/anvilbook/server/crafts_api.py`
- Modify: `src/anvilbook/server/api.py`
- Test: `tests/server/test_server_crafts.py`

**Interfaces:**
- Consumes: `latest_prices` (Task 4), `Calculator`, `CraftSettings` (`craft.py`), `load_items` (`items.py`), `merge`, `GameExport` (`recipes.py`).
- Produces: `add_crafts_route(app, database, items_loader)`, endpoint `GET /api/crafts?realm=&character=`.

- [ ] **Step 1: Write the failing test**

`tests/server/test_server_crafts.py`:

```python
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
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run --extra server pytest tests/server/test_server_crafts.py -q`
Expected: FAIL: `create_server() got an unexpected keyword argument 'data_dir'`

- [ ] **Step 3: Write `crafts_api.py`**

```python
from dataclasses import asdict

from fastapi import HTTPException, Query

from ..craft import Calculator, CraftSettings
from ..recipes import GameExport, merge
from .read_api import latest_prices

SETTINGS = {'skills': {}, 'skill_overrides': {}, 'max_use_level': 20, 'min_listed': 1,
            'cast_seconds': 3, 'ah_cut': 0.05}
PUBLIC_SKILLS = {'Blacksmithing': 300, 'Mining': 300, 'Leatherworking': 300, 'Tailoring': 300,
                 'Alchemy': 300, 'Engineering': 300, 'Cooking': 300, 'First Aid': 300,
                 'Enchanting': 300, 'Jewelcrafting': 300, 'Inscription': 300}


def character_export(database, realm: str, name: str) -> GameExport:
    rows = database.query("""
        SELECT c.id, c.name, s.profession, s.rank, s.max_rank
        FROM characters c JOIN realms r ON r.id = c.realm_id
        LEFT JOIN character_skills s ON s.character_id = c.id
        WHERE r.name = %s AND c.name = %s AND c.published""", (realm, name))
    if not rows:
        raise HTTPException(404, 'No published character with that name on that realm')
    professions: dict[str, dict] = {}
    for row in rows:
        if row['profession']:
            professions[row['profession']] = {'rank': row['rank'], 'maxRank': row['max_rank'],
                                              'recipes': {}}
    for recipe in database.query("""
            SELECT item_id, name, min_made, max_made, difficulty, profession, reagents
            FROM character_recipes WHERE character_id = %s""", (rows[0]['id'],)):
        profession = professions.setdefault(recipe['profession'],
                                            {'rank': 0, 'maxRank': 0, 'recipes': {}})
        profession['recipes'][recipe['item_id']] = {
            'name': recipe['name'], 'minMade': recipe['min_made'], 'maxMade': recipe['max_made'],
            'difficulty': recipe['difficulty'],
            'reagents': {i: dict(r) for i, r in enumerate(recipe['reagents'] or [], start=1)}}
    return GameExport(name, 0, professions)


def add_crafts_route(app, database, items_loader) -> None:
    @app.get('/api/crafts')
    def crafts(realm: str, character: str | None = None, limit: int = Query(200, le=500)):
        prices = latest_prices(database, realm)
        if not prices:
            raise HTTPException(404, 'No prices for that realm yet')
        items = items_loader()
        settings = CraftSettings.from_dict(SETTINGS)
        if character:
            export = character_export(database, realm, character)
            items = merge(items, export)
            settings.skills = {p: int(d.get('rank') or 0) for p, d in export.professions.items()}
        else:
            settings.skills = dict(PUBLIC_SKILLS)
        rows = Calculator(items, prices, {}, settings).rows()
        return [asdict(row) for row in rows[:limit]]
```

- [ ] **Step 4: Let the server load the item database**

In `api.py`, change the factory signature and add the loader:

```python
def create_server(database: Database | None = None, data_dir: Path | None = None) -> FastAPI:
    database = database or Database()
    data_dir = Path(data_dir or os.environ.get('ANVILBOOK_DATA') or '/data')
    cache: dict[str, dict] = {}

    def items_loader() -> dict:
        # Created here, not at startup: the tests that never ask for crafts must not need /data.
        if 'items' not in cache:
            data_dir.mkdir(parents=True, exist_ok=True)
            cache['items'] = load_items(data_dir / 'items.json')
        return cache['items']
```

and after the read routes: `add_crafts_route(app, database, items_loader)`.
Imports: `from pathlib import Path`, `from ..items import load_items`, `from .crafts_api import add_crafts_route`.

- [ ] **Step 5: Run the tests**

Run: `uv run --extra server pytest tests/server -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/anvilbook/server tests/server
git commit -m "feat(server): crafting profits from shared code

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: The website

**Files:**
- Create: `src/anvilbook/server/static/index.html`
- Modify: `src/anvilbook/server/api.py`
- Test: `tests/server/test_site.py`

**Interfaces:**
- Consumes: every public endpoint from Tasks 4 and 5.
- Produces: `GET /` serving the page, and everything under `/` served from `server/static`.

- [ ] **Step 1: Write the failing test**

`tests/server/test_site.py`:

```python
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
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run --extra server pytest tests/server/test_site.py -q`
Expected: FAIL with 404 on `/`.

- [ ] **Step 3: Write the page**

Copy `src/anvilbook/static/logo.svg` to `src/anvilbook/server/static/logo.svg`. Write
`src/anvilbook/server/static/index.html` with the same palette and table helpers as the app page,
holding: a realm picker filled from `/api/realms`, an item search box calling
`/api/items/search`, an item panel showing price, quantity and a uPlot chart from
`/api/items/{id}/history`, and a crafts table from `/api/crafts` with a character picker filled
from `/api/characters`. Reuse the `money()`, `renderTable()` and chart code from
`src/anvilbook/static/index.html`; the columns for crafts are Item, Profession, Skill-up, Cost,
Net sale, Profit, Casts and Listed.

Add an **About** panel, reachable from the header, holding 3 short paragraphs: what anvilbook is
(a local app that reads Auctionator's saved prices and works out what is worth crafting); where
these prices come from (players who run the app and turned sharing on, so a realm is only as
fresh as its last contributor); and how to get it, with links to the releases page, the PyPI
package and the CurseForge addon. Close with the line "Prices come from players running
anvilbook. Nothing here is official Blizzard data."

- [ ] **Step 4: Serve it**

At the end of `create_server`, before `return app`:

```python
    @app.get('/')
    def index():
        return FileResponse(STATIC / 'index.html')

    # Mounted last: a mount swallows every path registered after it.
    app.mount('/', StaticFiles(directory=STATIC), name='site')
```

with `STATIC = Path(__file__).parent / 'static'` at module level and the FastAPI imports for
`FileResponse` and `StaticFiles`.

- [ ] **Step 5: Run the tests**

Run: `uv run --extra server pytest tests/server -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/anvilbook/server tests/server
git commit -m "feat(server): public price and crafting site

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Client push and the Share tab

**Files:**
- Create: `src/anvilbook/push.py`
- Modify: `src/anvilbook/store.py`, `src/anvilbook/app.py`, `src/anvilbook/static/index.html`
- Test: `tests/test_push.py`, `tests/test_app.py`

**Interfaces:**
- Consumes: `Store` settings, `Snapshot` and `ItemPrice` (`importer.py`), `GameExport` (`recipes.py`).
- Produces: `class PushClient(base_url: str, token: str | None = None)` with `register(username, password) -> str`, `login(username, password) -> str`, `logout() -> None`, `push_scan(realm: str, taken_at: str, prices: list[dict]) -> dict`, `push_character(realm: str, name: str, professions: dict, published: bool) -> dict`, `unpublish_character(realm: str, name: str) -> dict`, `delete_account() -> None`; and `PushError(Exception)`.
  New settings: `server_url` (''), `server_token` (''), `server_username` (''), `push_prices` (False), `published_characters` ({}).
  New endpoints: `GET /api/share`, `POST /api/share/login`, `POST /api/share/register`, `POST /api/share/logout`, `PUT /api/share/settings`, `POST /api/share/push`, `DELETE /api/share/account`.

- [ ] **Step 1: Write the failing client tests**

`tests/test_push.py`:

```python
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from anvilbook.push import PushClient, PushError


class Handler(BaseHTTPRequestHandler):
    calls: list = []
    status = 200
    body = {'token': 'abc', 'username': 'thordak'}

    def do_POST(self):
        length = int(self.headers.get('Content-Length') or 0)
        payload = json.loads(self.rfile.read(length) or b'{}')
        Handler.calls.append((self.path, payload, self.headers.get('Authorization')))
        self.send_response(Handler.status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(Handler.body).encode())

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    Handler.calls, Handler.status, Handler.body = [], 200, {'token': 'abc', 'username': 'thordak'}
    httpd = HTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{httpd.server_port}', Handler
    httpd.shutdown()


def test_login_returns_a_token(server):
    url, handler = server
    assert PushClient(url).login('thordak', 'a long password') == 'abc'
    path, payload, _ = handler.calls[0]
    assert path == '/api/login'
    assert payload == {'username': 'thordak', 'password': 'a long password'}


def test_push_scan_sends_prices_with_the_token(server):
    url, handler = server
    handler.body = {'stored': 2}
    client = PushClient(url, token='abc')
    result = client.push_scan('Realm', '2026-09-26T10:00:00+00:00',
                              [{'item_id': 2770, 'min_price': 57, 'available': 4, 'name': 'Copper Ore'}])
    assert result == {'stored': 2}
    path, payload, auth = handler.calls[0]
    assert path == '/api/push/scan'
    assert auth == 'Bearer abc'
    assert payload['realm'] == 'Realm'
    assert payload['prices'][0]['item_id'] == 2770


def test_character_reagents_are_sent_as_a_list(server):
    url, handler = server
    professions = {'Blacksmithing': {'rank': 148, 'maxRank': 150, 'recipes': {
        3490: {'name': 'Deadly Bronze Poniard', 'minMade': 1, 'maxMade': 1, 'difficulty': 'easy',
               'reagents': {1: {'id': 2841, 'count': 4}, 2: {'id': 3466, 'count': 1}}}}}}
    PushClient(url, token='abc').push_character('Realm', 'Thordak', professions, True)
    _, payload, _ = handler.calls[0]
    assert payload['professions'] == {'Blacksmithing': {'rank': 148, 'maxRank': 150}}
    recipe = payload['recipes']['3490']
    assert recipe['profession'] == 'Blacksmithing'
    assert recipe['reagents'] == [{'id': 2841, 'count': 4}, {'id': 3466, 'count': 1}]


def test_server_errors_become_push_errors(server):
    url, handler = server
    handler.status, handler.body = 429, {'detail': 'At most 20 pushes an hour. Try later.'}
    with pytest.raises(PushError, match='20 pushes'):
        PushClient(url, token='abc').push_scan('Realm', '2026-09-26T10:00:00+00:00',
                                               [{'item_id': 1, 'min_price': 1}])


def test_an_unreachable_server_raises_push_error():
    with pytest.raises(PushError):
        PushClient('http://127.0.0.1:1', token='abc').push_scan('Realm', '2026-09-26T10:00:00+00:00',
                                                                [{'item_id': 1, 'min_price': 1}])


def test_plain_http_is_refused_for_anything_but_localhost():
    with pytest.raises(PushError, match='https'):
        PushClient('http://example.com')
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/test_push.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'anvilbook.push'`

- [ ] **Step 3: Write `push.py`**

```python
import json
import urllib.error
import urllib.request
from urllib.parse import quote, urlparse

TIMEOUT = 20


class PushError(Exception):
    pass


def _reagents(value) -> list[dict]:
    # The game writes reagents as a Lua table, which reads back as a dict keyed 1, 2, 3.
    rows = [value[k] for k in sorted(value)] if isinstance(value, dict) else list(value or [])
    return [{'id': int(r['id']), 'count': int(r['count'])} for r in rows]


class PushClient:
    def __init__(self, base_url: str, token: str | None = None):
        self.base_url = (base_url or '').rstrip('/')
        parsed = urlparse(self.base_url)
        if parsed.scheme not in ('http', 'https'):
            raise PushError('The server address must start with https://')
        # Passwords and tokens cross this wire.
        if parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1'):
            raise PushError('Use https, or the password would travel in the open')
        self.token = token

    def _call(self, method: str, path: str, body: dict | None = None, retries: int = 1) -> dict:
        request = urllib.request.Request(f'{self.base_url}{path}', method=method,
                                         data=json.dumps(body).encode() if body is not None else None)
        request.add_header('Content-Type', 'application/json')
        if self.token:
            request.add_header('Authorization', f'Bearer {self.token}')
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return json.loads(response.read() or b'{}')
        except urllib.error.HTTPError as e:
            detail = ''
            try:
                detail = json.loads(e.read() or b'{}').get('detail', '')
            except ValueError:
                pass
            raise PushError(detail or f'The server said {e.code}')
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            # A push often lands while the game reloads and the link flaps, so try once more.
            if retries > 0:
                return self._call(method, path, body, retries - 1)
            raise PushError(f'Could not reach the server: {e}')

    def register(self, username: str, password: str) -> str:
        self.token = self._call('POST', '/api/register',
                                {'username': username, 'password': password})['token']
        return self.token

    def login(self, username: str, password: str) -> str:
        self.token = self._call('POST', '/api/login',
                                {'username': username, 'password': password})['token']
        return self.token

    def logout(self) -> None:
        self._call('POST', '/api/logout')
        self.token = None

    def push_scan(self, realm: str, taken_at: str, prices: list[dict]) -> dict:
        return self._call('POST', '/api/push/scan',
                          {'realm': realm, 'taken_at': taken_at, 'prices': prices})

    def push_character(self, realm: str, name: str, professions: dict, published: bool) -> dict:
        recipes = {}
        for profession, data in professions.items():
            for item_id, recipe in (data.get('recipes') or {}).items():
                recipes[str(item_id)] = {
                    'name': recipe.get('name'), 'minMade': recipe.get('minMade') or 1,
                    'maxMade': recipe.get('maxMade') or 1, 'difficulty': recipe.get('difficulty'),
                    'profession': profession, 'reagents': _reagents(recipe.get('reagents'))}
        return self._call('POST', '/api/push/character', {
            'realm': realm, 'name': name, 'published': published,
            'professions': {p: {'rank': d.get('rank'), 'maxRank': d.get('maxRank')}
                            for p, d in professions.items()},
            'recipes': recipes})

    def unpublish_character(self, realm: str, name: str) -> dict:
        return self._call('DELETE', f'/api/push/character/{quote(realm)}/{quote(name)}')

    def delete_account(self) -> None:
        self._call('DELETE', '/api/account')
```

- [ ] **Step 4: Run the client tests**

Run: `uv run pytest tests/test_push.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Write the failing app tests**

Add to `tests/test_app.py`:

```python
def test_sharing_is_off_until_asked(env):
    client, _ = env
    share = client.get('/api/share').json()
    assert share == {'server_url': '', 'username': '', 'signed_in': False,
                     'push_prices': False, 'published_characters': {}}


def test_a_failed_push_does_not_break_the_import(env, monkeypatch):
    client, sv = env
    client.put('/api/settings', json={'server_url': 'https://example.com',
                                      'server_token': 'abc', 'push_prices': True})

    class Failing:
        def __init__(self, *args, **kw):
            pass

        def push_scan(self, *args, **kw):
            raise PushError('Could not reach the server')

    monkeypatch.setattr('anvilbook.app.PushClient', Failing)
    sv.write_bytes(savedvariables({'2770': entry(57, 2460, 100)}))

    assert client.post('/api/import').json()['scan_id'] is not None
    assert 'Could not reach the server' in client.get('/api/status').json()['push_error']
```

Add `from anvilbook.push import PushError` to the test imports.

- [ ] **Step 6: Run them and watch them fail**

Run: `uv run pytest tests/test_app.py -q`
Expected: FAIL with 404 on `/api/share`.

- [ ] **Step 7: Wire the client**

In `store.py` `DEFAULT_SETTINGS`, add:

```python
    'server_url': '',
    'server_username': '',
    'server_token': '',
    'push_prices': False,
    'published_characters': {},
```

In `app.py`, after the import succeeds inside `Importer.run`, push when asked. Give `Importer` a
`on_scan` callback set by `create_app`:

```python
    def push_scan(scan_id: int) -> None:
        settings = store.settings()
        if not (settings['push_prices'] and settings['server_url'] and settings['server_token']):
            return
        scan = next((s for s in store.scans() if s['id'] == scan_id), None)
        if not scan:
            return
        rows = [{'item_id': i, 'min_price': p['min_price'], 'available': p['available'],
                 'day_high': p['day_high'], 'name': (items().get(i) or {}).get('name')}
                for i, p in store.prices(scan_id).items()]
        realm, taken_at = scan['realm'] or 'unknown', scan['file_mtime']
        try:
            PushClient(settings['server_url'], settings['server_token']).push_scan(realm, taken_at, rows)
            importer.status['push_error'] = None
        except PushError as e:
            # A failed upload must never cost the local scan.
            importer.status['push_error'] = str(e)
            log.warning('push failed: %s', e)

    importer.on_scan = push_scan
```

`Importer.__init__` gains `self.on_scan = None` and `self.status['push_error'] = None`; after a
successful `add_scan` it calls `self.on_scan(scan_id)` inside a `try` that logs and swallows
anything.

Add the share endpoints in `app.py`:

```python
    @app.get('/api/share')
    def share():
        s = store.settings()
        return {'server_url': s['server_url'], 'username': s['server_username'],
                'signed_in': bool(s['server_token']), 'push_prices': bool(s['push_prices']),
                'published_characters': s['published_characters']}

    @app.post('/api/share/login')
    def share_login(body: dict = Body(...)):
        return _sign_in(body, register=False)

    @app.post('/api/share/register')
    def share_register(body: dict = Body(...)):
        return _sign_in(body, register=True)

    def _sign_in(body: dict, register: bool) -> dict:
        url, username = str(body.get('server_url') or ''), str(body.get('username') or '')
        try:
            client = PushClient(url)
            token = (client.register if register else client.login)(username, str(body.get('password') or ''))
        except PushError as e:
            raise HTTPException(400, str(e))
        store.save_settings({'server_url': url, 'server_username': username, 'server_token': token})
        return {'signed_in': True, 'username': username}

    @app.post('/api/share/logout')
    def share_logout():
        s = store.settings()
        if s['server_token']:
            try:
                PushClient(s['server_url'], s['server_token']).logout()
            except PushError as e:
                log.warning('logout failed: %s', e)
        store.save_settings({'server_token': '', 'push_prices': False})
        return {'signed_in': False}

    @app.put('/api/share/settings')
    def share_settings(body: dict = Body(...)):
        settings = store.settings()
        allowed = {k: v for k, v in body.items() if k in ('push_prices', 'published_characters')}
        if 'published_characters' in allowed:
            for character in settings['published_characters']:
                # Turning a switch off must also remove what the site already holds.
                if settings['published_characters'][character] and not allowed['published_characters'].get(character):
                    name, separator, realm = character.rpartition(' - ')
                    if not separator:
                        name, realm = character, settings['realm']
                    try:
                        PushClient(settings['server_url'],
                                   settings['server_token']).unpublish_character(realm, name)
                    except PushError as e:
                        log.warning('unpublish failed: %s', e)
        return store.save_settings(allowed)

    @app.post('/api/share/push')
    def share_push():
        settings = store.settings()
        if not (settings['server_url'] and settings['server_token']):
            raise HTTPException(400, 'Sign in on the Share tab first')
        scan_id = store.latest_scan_id()
        if scan_id:
            push_scan(scan_id)
        published = settings['published_characters']
        client = PushClient(settings['server_url'], settings['server_token'])
        for export in load_exports(Path(settings['export_path']).expanduser()):
            if not published.get(export.character):
                continue
            # The addon keys characters "Name - Realm"; a realm name may hold a space.
            name, separator, realm = export.character.rpartition(' - ')
            if not separator:
                name, realm = export.character, settings['realm']
            try:
                client.push_character(realm, name, export.professions, True)
            except PushError as e:
                importer.status['push_error'] = str(e)
        return {'ok': True, **importer.status}

    @app.delete('/api/share/account')
    def share_delete_account():
        settings = store.settings()
        if settings['server_token']:
            try:
                PushClient(settings['server_url'], settings['server_token']).delete_account()
            except PushError as e:
                raise HTTPException(400, str(e))
        store.save_settings({'server_token': '', 'server_username': '', 'push_prices': False,
                             'published_characters': {}})
        return {'signed_in': False}
```

Add `from .push import PushClient, PushError` to the imports in `app.py`. `Path`, `Body`,
`HTTPException`, `load_exports` and `log` are already there.

`/api/status` already spreads `importer.status`, so `push_error` appears there once
`Importer.__init__` sets it.

- [ ] **Step 8: Add the Share tab to the page**

In `src/anvilbook/static/index.html`, add a `Share` nav button and section. The section shows, in
this order: a short paragraph saying nothing is shared until the switches below are on; the server
address box; sign in and register buttons with username and password; once signed in, a switch
"Send my price scans after each import" bound to `PUT /api/share/settings`; a list of characters
from `/api/characters` each with a "Publish what this character can craft" switch, written back
with `PUT /api/share/settings`; a "Push now" button calling `POST /api/share/push`; a "Sign out"
button calling `POST /api/share/logout`; and a "Delete my account and everything I sent" button
that asks for confirmation first, then calls `DELETE /api/share/account`. Show `push_error` from
the status in the status bar when present.

- [ ] **Step 9: Run every test**

Run: `uv run pytest -q`
Expected: PASS (all, including the original 102)

- [ ] **Step 10: Commit**

```bash
git add src/anvilbook tests
git commit -m "feat: opt-in sharing of prices and character crafting

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: CI, image and documentation

**Files:**
- Modify: `.github/workflows/test.yml`, `.github/workflows/release.yml`, `README.md`
- Create: `docs/server.md`

**Interfaces:**
- Consumes: everything above.
- Produces: a Postgres service in CI, `ghcr.io/traagel/anvilbook-server` built on each tag, and operator documentation.

- [ ] **Step 1: Run the server tests in CI**

In `.github/workflows/test.yml`, inside the `test` job:

```yaml
    services:
      postgres:
        image: postgres:17
        env: {POSTGRES_PASSWORD: dev}
        ports: ['5432:5432']
        options: >-
          --health-cmd pg_isready --health-interval 5s --health-timeout 5s --health-retries 10
```

and change the pytest step to:

```yaml
      - run: uv run --extra server pytest -q
        env:
          ANVILBOOK_TEST_DATABASE_URL: postgresql://postgres:dev@localhost:5432/postgres
```

- [ ] **Step 2: Build and push the image on a tag**

Add to `.github/workflows/release.yml`:

```yaml
  image:
    runs-on: ubuntu-latest
    permissions:
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          context: .
          file: deploy/Dockerfile
          push: true
          tags: |
            ghcr.io/traagel/anvilbook-server:latest
            ghcr.io/traagel/anvilbook-server:${{ github.ref_name }}
```

- [ ] **Step 3: Write the operator guide**

`docs/server.md` covering: what the server stores; `DATABASE_URL` and `PORT`; `kubectl create secret
generic anvilbook --from-literal=database-url=...`; `kubectl apply -f deploy/k8s.yaml`; pointing an
Ingress at the `anvilbook` Service on port 80; that TLS is required because passwords cross the
wire; that the Ingress should cap the request body at 5 MB, because the application can only
refuse a large upload after it is received; that rate limiting assumes a single replica; and how
to delete one contributor's data with `DELETE FROM users WHERE username = '...'`.

- [ ] **Step 4: Update the README**

Add a **Sharing** section: sharing is off by default, the 2 switches, what each sends, that the
public site is optional, and a link to `docs/server.md` for people who want to run their own.

- [ ] **Step 5: Run everything**

Run: `uv run --extra server pytest -q` and both addon harnesses.
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add .github docs README.md
git commit -m "ci: server tests and image build; docs: running the server

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

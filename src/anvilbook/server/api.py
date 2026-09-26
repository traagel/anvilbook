import logging
import os
import threading
import time
from pathlib import Path

import psycopg
from fastapi import Body, Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..items import load_items
from .auth import check_password, check_username, hash_password, new_token, token_hash, verify_password
from .crafts_api import add_crafts_route
from .db import Database
from .push_api import add_push_routes
from .read_api import add_read_routes

log = logging.getLogger(__name__)
PREFIX = 'Bearer '
STATIC = Path(__file__).parent / 'static'
MAX_BYTES = 5 * 1024 * 1024
SIGNUPS_PER_HOUR = 10
SIGNINS_PER_HOUR = 60
TOO_LARGE = {'detail': 'That upload is larger than the 5 MB limit'}


class BodyLimit:
    """Stops reading an upload once it passes the limit.

    A chunked request carries no Content-Length, so the header alone cannot hold the line.
    Cutting the stream short makes the body unparseable, which the framework reports as a
    plain 400; only a client that ignores Content-Length ends up with that vaguer message.
    """

    def __init__(self, app, limit: int = MAX_BYTES):
        self.app = app
        self.limit = limit

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        declared = int(dict(scope.get('headers') or []).get(b'content-length', b'0') or 0)
        if declared > self.limit:
            return await JSONResponse(TOO_LARGE, 400)(scope, receive, send)
        received = 0

        async def counted():
            nonlocal received
            message = await receive()
            if message['type'] == 'http.request':
                received += len(message.get('body') or b'')
                if received > self.limit:
                    return {'type': 'http.disconnect'}
            return message

        await self.app(scope, counted, send)


def create_server(database: Database | None = None, data_dir: Path | None = None) -> FastAPI:
    db: Database = database or Database()
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS users_username_lower ON users (lower(username))')
    items_dir = Path(data_dir or os.environ.get('ANVILBOOK_DATA') or '/data')
    cache: dict[str, dict] = {}
    items_lock = threading.Lock()
    attempts: dict[str, list[float]] = {'register': [], 'login': []}
    app = FastAPI(title='anvilbook server')

    app.add_middleware(BodyLimit)

    def ration(kind: str, per_hour: int) -> None:
        cutoff = time.monotonic() - 3600
        attempts[kind] = [t for t in attempts[kind] if t > cutoff]
        if len(attempts[kind]) >= per_hour:
            raise HTTPException(429, 'Too many attempts. Try again later.')
        attempts[kind].append(time.monotonic())

    def items_loader() -> dict:
        # The lock stops 2 first requests downloading over each other's part file.
        with items_lock:
            if 'items' not in cache:
                items_dir.mkdir(parents=True, exist_ok=True)
                cache['items'] = load_items(items_dir / 'items.json')
            return cache['items']

    @app.get('/healthz')
    def healthz():
        db.query('SELECT 1')
        return {'ok': True}

    def user_for(authorization: str | None) -> dict:
        if not authorization or not authorization.startswith(PREFIX):
            raise HTTPException(401, 'Sign in first')
        row = db.execute("""
            UPDATE tokens SET last_used_at = now() WHERE token_hash = %s
            RETURNING (SELECT username FROM users WHERE users.id = tokens.user_id) AS username, user_id AS id
            """, (token_hash(authorization[len(PREFIX):]),))
        if not row:
            raise HTTPException(401, 'Sign in again')
        return row

    def current_user(authorization: str | None = Header(None)) -> dict:
        return user_for(authorization)

    def issue_token(user_id: int) -> str:
        token, stored = new_token()
        db.execute('INSERT INTO tokens (token_hash, user_id) VALUES (%s, %s)', (stored, user_id))
        return token

    @app.post('/api/register')
    def register(body: dict = Body(...)):
        # Hashing a password costs 32 MiB and 50 ms, so the flood limit comes first.
        ration('register', SIGNUPS_PER_HOUR)
        username, password = str(body.get('username') or ''), str(body.get('password') or '')
        try:
            check_username(username)
            check_password(password)
        except ValueError as e:
            raise HTTPException(400, str(e))
        if db.query('SELECT id FROM users WHERE lower(username) = lower(%s)', (username,)):
            raise HTTPException(409, 'That username is taken')
        try:
            user = db.execute('INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id',
                              (username, hash_password(password)))
        except psycopg.errors.UniqueViolation:
            raise HTTPException(409, 'That username is taken')
        return {'token': issue_token(user['id']), 'username': username}

    @app.post('/api/login')
    def login(body: dict = Body(...)):
        ration('login', SIGNINS_PER_HOUR)
        username, password = str(body.get('username') or ''), str(body.get('password') or '')
        rows = db.query('SELECT id, username, password_hash FROM users WHERE lower(username) = lower(%s)',
                        (username,))
        user = rows[0] if rows else None
        if not user or not verify_password(password, user['password_hash']):
            raise HTTPException(401, 'Wrong username or password')
        return {'token': issue_token(user['id']), 'username': user['username']}

    @app.post('/api/logout')
    def logout(authorization: str | None = Header(None)):
        user_for(authorization)
        db.execute('DELETE FROM tokens WHERE token_hash = %s',
                   (token_hash((authorization or '')[len(PREFIX):]),))
        return {'ok': True}

    @app.delete('/api/account')
    def delete_account(user: dict = Depends(current_user)):
        db.execute('DELETE FROM users WHERE id = %s', (user['id'],))
        return {'ok': True}

    add_push_routes(app, db, current_user)
    add_read_routes(app, db)
    add_crafts_route(app, db, items_loader)

    @app.get('/')
    def index():
        return FileResponse(STATIC / 'index.html')

    # Mounted last: a mount swallows every path registered after it.
    app.mount('/', StaticFiles(directory=STATIC), name='site')

    return app


def run() -> None:
    import uvicorn
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    uvicorn.run(create_server(), host='0.0.0.0', port=int(os.environ.get('PORT', 8000)))

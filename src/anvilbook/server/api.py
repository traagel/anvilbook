import logging
import os

from fastapi import Body, Depends, FastAPI, Header, HTTPException

from .auth import check_password, check_username, hash_password, new_token, token_hash, verify_password
from .db import Database

log = logging.getLogger(__name__)
PREFIX = 'Bearer '


def create_server(database: Database | None = None) -> FastAPI:
    db: Database = database or Database()
    app = FastAPI(title='anvilbook server')

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
        username, password = str(body.get('username') or ''), str(body.get('password') or '')
        try:
            check_username(username)
            check_password(password)
        except ValueError as e:
            raise HTTPException(400, str(e))
        if db.query('SELECT id FROM users WHERE lower(username) = lower(%s)', (username,)):
            raise HTTPException(409, 'That username is taken')
        user = db.execute('INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id',
                          (username, hash_password(password)))
        return {'token': issue_token(user['id']), 'username': username}

    @app.post('/api/login')
    def login(body: dict = Body(...)):
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

    return app


def run() -> None:
    import uvicorn
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    uvicorn.run(create_server(), host='0.0.0.0', port=int(os.environ.get('PORT', 8000)))

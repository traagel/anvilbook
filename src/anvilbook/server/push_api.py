import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import Body, Depends, HTTPException, Request
from psycopg.types.json import Jsonb

MAX_ROWS = 20000
MAX_BYTES = 5 * 1024 * 1024
MIN_PRICE, MAX_PRICE = 1, 1_000_000_00
AGE_LIMIT = timedelta(days=2)
PUSHES_PER_HOUR = 20


def within_size(request: Request) -> None:
    if int(request.headers.get('content-length') or 0) > MAX_BYTES:
        raise HTTPException(400, 'That upload is larger than the 5 MB limit')


def realm_id(database, name: str | None) -> int:
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

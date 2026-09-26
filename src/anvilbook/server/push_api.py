import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import Body, Depends, HTTPException
from psycopg.types.json import Jsonb

MAX_ROWS = 20000
MAX_RECIPES = 3000
MAX_PROFESSIONS = 40
MIN_PRICE, MAX_PRICE = 1, 10_000_000 * 10_000
AGE_LIMIT = timedelta(days=2)
# A scan cannot come from the future; this only absorbs clock skew between the 2 machines.
FUTURE_LIMIT = timedelta(hours=1)
PUSHES_PER_HOUR = 20
INT32, INT64 = 2 ** 31 - 1, 2 ** 63 - 1


def _int(value, name: str, low: int, high: int, default: int | None = None) -> int:
    if value is None and default is not None:
        return default
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise HTTPException(400, f'{name} must be a whole number')
    if not low <= number <= high:
        raise HTTPException(400, f'{name} must be between {low} and {high}')
    return number


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
    now = datetime.now(timezone.utc)
    if taken_at - now > FUTURE_LIMIT:
        raise HTTPException(400, 'taken_at cannot be in the future')
    if now - taken_at > AGE_LIMIT:
        raise HTTPException(400, 'taken_at must be within 2 days of now')
    return taken_at


def _rows(prices) -> list[tuple]:
    if not isinstance(prices, list) or not prices:
        raise HTTPException(400, 'The scan has no prices')
    if len(prices) > MAX_ROWS:
        raise HTTPException(400, f'A scan may hold at most {MAX_ROWS} rows')
    rows: dict[int, tuple] = {}
    for price in prices:
        if not isinstance(price, dict):
            raise HTTPException(400, 'Each price needs item_id and min_price')
        item_id = _int(price.get('item_id'), 'item_id', 1, INT64)
        value = _int(price.get('min_price'), 'A price', MIN_PRICE, MAX_PRICE)
        available = _int(price.get('available'), 'available', 0, INT32, default=0)
        high = price.get('day_high')
        # The last row wins: a scan holding the same item twice is malformed, not a reason to fail.
        rows[item_id] = (item_id, str(price.get('name') or '')[:120] or None, value, available,
                         _int(high, 'day_high', 0, INT64) if high else None)
    return list(rows.values())


def _reagents(value) -> list[dict]:
    rows = value.values() if isinstance(value, dict) else value
    if not isinstance(rows, (list, tuple, type({}.values()))):
        raise HTTPException(400, 'reagents must be a list')
    out = []
    for reagent in rows:
        if not isinstance(reagent, dict):
            raise HTTPException(400, 'Each reagent needs an id and a count')
        out.append({'id': _int(reagent.get('id'), 'reagent id', 1, INT64),
                    'count': _int(reagent.get('count'), 'reagent count', 1, INT32)})
    return out


def _skills(professions) -> list[tuple]:
    if not isinstance(professions, dict):
        raise HTTPException(400, 'professions must be an object')
    if len(professions) > MAX_PROFESSIONS:
        raise HTTPException(400, f'At most {MAX_PROFESSIONS} professions')
    out = []
    for profession, skill in professions.items():
        if not isinstance(skill, dict):
            raise HTTPException(400, 'Each profession needs a rank and a maxRank')
        out.append((str(profession)[:40], _int(skill.get('rank'), 'rank', 0, 1000, default=0),
                    _int(skill.get('maxRank'), 'maxRank', 0, 1000, default=0)))
    return out


def _recipes(recipes) -> list[tuple]:
    if not isinstance(recipes, dict):
        raise HTTPException(400, 'recipes must be an object')
    if len(recipes) > MAX_RECIPES:
        raise HTTPException(400, f'At most {MAX_RECIPES} recipes')
    out = []
    for item_id, recipe in recipes.items():
        if not isinstance(recipe, dict):
            raise HTTPException(400, 'Each recipe must be an object')
        out.append((_int(item_id, 'recipe item id', 1, INT64),
                    str(recipe.get('name') or '')[:120],
                    _int(recipe.get('minMade'), 'minMade', 1, INT32, default=1),
                    _int(recipe.get('maxMade'), 'maxMade', 1, INT32, default=1),
                    str(recipe.get('difficulty'))[:20] if recipe.get('difficulty') else None,
                    str(recipe.get('profession') or '')[:40],
                    Jsonb(_reagents(recipe.get('reagents')))))
    return out


def add_push_routes(app, database, current_user) -> None:
    recent: dict[int, list[float]] = defaultdict(list)

    def within_rate_limit(user_id: int) -> None:
        cutoff = time.monotonic() - 3600
        recent[user_id] = [t for t in recent[user_id] if t > cutoff]
        if len(recent[user_id]) >= PUSHES_PER_HOUR:
            raise HTTPException(429, f'At most {PUSHES_PER_HOUR} pushes an hour. Try later.')
        recent[user_id].append(time.monotonic())

    @app.post('/api/push/scan')
    def push_scan(body: dict = Body(...), user: dict = Depends(current_user)):
        within_rate_limit(user['id'])
        realm = realm_id(database, body.get('realm'))
        taken_at = _when(body.get('taken_at'))
        rows = _rows(body.get('prices'))
        # One transaction: a replace that fails half way would destroy the stored scan.
        with database.connect() as conn:
            with conn.transaction():
                conn.execute('DELETE FROM scans WHERE user_id = %s AND realm_id = %s AND taken_at = %s',
                             (user['id'], realm, taken_at))
                scan = conn.execute(
                    'INSERT INTO scans (user_id, realm_id, taken_at, item_count)'
                    ' VALUES (%s, %s, %s, %s) RETURNING id',
                    (user['id'], realm, taken_at, len(rows))).fetchone()
                conn.cursor().executemany(
                    'INSERT INTO prices (scan_id, item_id, name, min_price, available, day_high)'
                    ' VALUES (%s, %s, %s, %s, %s, %s)',
                    [(scan['id'], *row) for row in rows])
        return {'stored': len(rows), 'scan_id': scan['id']}

    @app.post('/api/push/character')
    def push_character(body: dict = Body(...), user: dict = Depends(current_user)):
        within_rate_limit(user['id'])
        realm = realm_id(database, body.get('realm'))
        name = str(body.get('name') or '').strip()
        if not (1 <= len(name) <= 48):
            raise HTTPException(400, 'Give the character name')
        published = bool(body.get('published'))
        skills = _skills(body.get('professions') or {})
        recipes = _recipes(body.get('recipes') or {})
        with database.connect() as conn:
            with conn.transaction():
                character = conn.execute("""
                    INSERT INTO characters (user_id, realm_id, name, published, updated_at)
                    VALUES (%s, %s, %s, %s, now())
                    ON CONFLICT (user_id, realm_id, name)
                    DO UPDATE SET published = EXCLUDED.published, updated_at = now()
                    RETURNING id""", (user['id'], realm, name, published)).fetchone()
                conn.execute('DELETE FROM character_skills WHERE character_id = %s', (character['id'],))
                conn.execute('DELETE FROM character_recipes WHERE character_id = %s', (character['id'],))
                conn.cursor().executemany(
                    'INSERT INTO character_skills (character_id, profession, rank, max_rank)'
                    ' VALUES (%s, %s, %s, %s)',
                    [(character['id'], *skill) for skill in skills])
                conn.cursor().executemany("""
                    INSERT INTO character_recipes
                        (character_id, item_id, name, min_made, max_made, difficulty, profession, reagents)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    [(character['id'], *recipe) for recipe in recipes])
        return {'ok': True, 'published': published}

    @app.delete('/api/push/character/{realm}/{name}')
    def remove_character(realm: str, name: str, user: dict = Depends(current_user)):
        database.execute("""
            DELETE FROM characters WHERE user_id = %s AND name = %s
              AND realm_id = (SELECT id FROM realms WHERE name = %s)""", (user['id'], name, realm))
        return {'ok': True}

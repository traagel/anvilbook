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
    def search(q: str, realm: str, limit: int = Query(30, ge=1, le=100)):
        # Items the item database has never heard of reach us with no name, so the id is
        # the only way a visitor can find them.
        return database.query(
            LATEST.replace('WHERE r.name = %s',
                           "WHERE r.name = %s AND (p.name ILIKE %s OR p.item_id::text = %s)")
            + ' LIMIT %s', (realm, f'%{q}%', q.strip(), limit))

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

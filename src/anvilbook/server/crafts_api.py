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

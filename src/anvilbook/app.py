import asyncio
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

import uvicorn
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from .craft import Calculator, CraftSettings
from .disenchant import effective_table, observed, parse_records
from .items import load_items
from .luatable import LuaParseError, parse_savedvariables
from .plan import for_budget, plan_for
from .recipes import GameExport, export_skills, load_export, load_exports, merge
from .store import Store
from .watcher import Importer

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / 'static'
POLL_SECONDS = 5


def create_app(data_dir: Path | None = None, watch: bool = True) -> FastAPI:
    data_dir = Path(data_dir or os.environ.get('ANVILBOOK_DATA') or Path.home() / '.local/share/anvilbook')
    data_dir.mkdir(parents=True, exist_ok=True)
    store = Store(data_dir / 'anvilbook.db')
    importer = Importer(store)
    cache: dict[str, dict[int, dict]] = {}

    def items() -> dict[int, dict]:
        if 'items' not in cache:
            cache['items'] = load_items(data_dir / 'items.json')
        return cache['items']

    def game_export() -> GameExport | None:
        settings = store.settings()
        path = Path(settings['export_path']).expanduser()
        try:
            return load_export(path, settings['character'])
        except LuaParseError as e:
            log.warning('recipe export unreadable: %s', e)
            return None

    def disenchant_records() -> list[dict]:
        path = Path(store.settings()['export_path']).expanduser()
        try:
            db = parse_savedvariables(path.read_bytes()).get('AnvilbookExportDB')
        except (FileNotFoundError, LuaParseError):
            return []
        return parse_records(db if isinstance(db, dict) else {})

    async def watch_loop() -> None:
        while True:
            try:
                await asyncio.to_thread(importer.run)
            except Exception:
                log.exception('watcher step failed')
            await asyncio.sleep(POLL_SECONDS)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await asyncio.to_thread(items)
        task = asyncio.create_task(watch_loop()) if watch else None
        yield
        if task:
            task.cancel()

    app = FastAPI(title='anvilbook', lifespan=lifespan)

    @app.get('/')
    def index():
        return FileResponse(STATIC / 'index.html')

    @app.get('/api/status')
    def status():
        exp = game_export()
        summary = exp and {'character': exp.character, 'updated': exp.updated, 'professions': export_skills(exp)}
        return {**importer.status, 'scans': len(store.scans()), 'export': summary,
                'pinned': store.settings()['character']}

    @app.post('/api/import')
    def do_import():
        return {'scan_id': importer.run(force=True), **importer.status}

    @app.get('/api/scans')
    def scans():
        return store.scans()

    @app.get('/api/characters')
    def characters():
        path = Path(store.settings()['export_path']).expanduser()
        try:
            found = load_exports(path)
        except LuaParseError as e:
            log.warning('recipe export unreadable: %s', e)
            return []
        return [{'character': e.character, 'updated': e.updated, 'professions': export_skills(e),
                 'maxRanks': {p: int(d.get('maxRank') or 0) for p, d in e.professions.items()}} for e in found]

    def calculator() -> tuple[Calculator | None, GameExport | None]:
        scan_id = store.latest_scan_id()
        exp = game_export()
        if scan_id is None:
            return None, exp
        stored = store.settings()
        settings = CraftSettings.from_dict(stored)
        known = items()
        if exp:
            known = merge(known, exp)
            # The character can only craft what the game reported for them.
            settings.skills = export_skills(exp)
        settings.disenchanter = bool(stored['assume_enchanter']) or 'Enchanting' in settings.skills
        settings.disenchant_table = effective_table(settings.disenchant_table, disenchant_records(),
                                                    int(stored['min_disenchant_samples']))
        return Calculator(known, store.prices(scan_id), store.vendor_prices(), settings), exp

    @app.get('/api/crafts')
    def crafts():
        calc, _ = calculator()
        return [asdict(r) for r in calc.rows()] if calc else []

    @app.get('/api/plan')
    def plan(item_id: int, budget: int, count: int | None = None, use_bags: bool = True):
        calc, exp = calculator()
        if calc is None:
            raise HTTPException(409, 'No price scan yet')
        owned = dict(exp.bags) if exp and use_bags else {}
        result = plan_for(calc, item_id, count, owned) if count else for_budget(calc, item_id, budget, owned)
        return {**asdict(result), 'budget': budget}

    @app.get('/api/items/search')
    def search(q: str, limit: int = 20):
        q = q.lower()
        known = items()
        hits = [{'item_id': i, 'name': known[i]['name'], 'icon': known[i]['icon']}
                for i in store.item_ids() if i in known and q in known[i]['name'].lower()]
        return sorted(hits, key=lambda h: h['name'])[:limit]

    @app.get('/api/items/{item_id}/history')
    def history(item_id: int):
        item = items().get(item_id)
        if not item:
            raise HTTPException(404, 'unknown item')
        return {'item_id': item_id, 'name': item['name'], 'points': store.history(item_id)}

    @app.get('/api/sellthrough')
    def sellthrough(from_id: int | None = Query(None, alias='from'), to_id: int | None = Query(None, alias='to')):
        ids = [s['id'] for s in store.scans()]
        if from_id is None or to_id is None:
            if len(ids) < 2:
                return {'from': None, 'to': None, 'rows': []}
            from_id, to_id = ids[-2], ids[-1]
        known = items()
        rows = store.sellthrough(from_id, to_id)
        for r in rows:
            r['name'] = (known.get(r['item_id']) or {}).get('name') or str(r['item_id'])
        return {'from': from_id, 'to': to_id, 'rows': rows}

    @app.get('/api/disenchants')
    def disenchants():
        stored = store.settings()
        known = items()
        minimum = int(stored['min_disenchant_samples'])
        out = []
        for (quality, max_level, kind), data in observed(stored['disenchant_table'], disenchant_records()).items():
            out.append({
                'quality': quality, 'maxLevel': max_level, 'kind': kind, 'samples': data['samples'],
                'used': data['samples'] >= minimum,
                'yields': [{'item_id': i, 'name': (known.get(i) or {}).get('name') or str(i),
                            'chance': chance, 'quantity': qty} for i, chance, qty in data['yields']],
            })
        return sorted(out, key=lambda r: (r['quality'], r['maxLevel'], r['kind']))

    @app.get('/api/settings')
    def get_settings():
        return store.settings()

    @app.put('/api/settings')
    def put_settings(values: dict = Body(...)):
        try:
            CraftSettings.from_dict({**store.settings(), **values})
            return store.save_settings(values)
        except (KeyError, ValueError, TypeError, AttributeError) as e:
            raise HTTPException(400, str(e))

    return app


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(create_app(), host='127.0.0.1', port=int(os.environ.get('ANVILBOOK_PORT', 8765)))

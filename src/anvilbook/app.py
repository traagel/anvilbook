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
from .items import load_items
from .luatable import LuaParseError
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

    @app.get('/api/crafts')
    def crafts():
        scan_id = store.latest_scan_id()
        if scan_id is None:
            return []
        settings = CraftSettings.from_dict(store.settings())
        known = items()
        exp = game_export()
        if exp:
            known = merge(known, exp)
            # The character can only craft what the game reported for them.
            settings.skills = export_skills(exp)
        calc = Calculator(known, store.prices(scan_id), store.vendor_prices(), settings)
        return [asdict(r) for r in calc.rows()]

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

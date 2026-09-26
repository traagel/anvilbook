import asyncio
import logging
import os
import signal
import threading
import webbrowser
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

import uvicorn
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import config_path, load_config, write_config
from .craft import Calculator, CraftSettings
from .disenchant import effective_table, observed, parse_records
from .discover import find_installs, looks_like_addon_code, search_roots
from .installer import install_addon, is_installed
from .items import load_items
from .luatable import LuaParseError, parse_savedvariables
from .plan import for_budget, plan_for
from .push import PushClient, PushError
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

    def seed_savedvariables() -> None:
        """Take the path from the config file. Searching the disk needs a person to ask."""
        if store.settings()['savedvariables_path']:
            return
        configured = load_config().savedvariables_path
        if configured and configured.is_file():
            log.info('using %s', configured)
            use_savedvariables(configured)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await asyncio.to_thread(items)
        await asyncio.to_thread(seed_savedvariables)
        task = asyncio.create_task(watch_loop()) if watch else None
        yield
        if task:
            task.cancel()

    app = FastAPI(title='anvilbook', lifespan=lifespan)

    @app.get('/')
    def index():
        return FileResponse(STATIC / 'index.html')


    def use_savedvariables(path: Path) -> dict:
        settings = store.save_settings({'savedvariables_path': str(path),
                                        'export_path': str(path.with_name('AnvilbookExport.lua'))})
        write_config(savedvariables_path=str(path))
        importer.run(force=True)
        return settings

    @app.get('/api/setup')
    def setup():
        settings = store.settings()
        chosen = Path(settings['savedvariables_path']) if settings['savedvariables_path'] else None
        return {'configured': bool(chosen), 'installs': [],
                'savedvariables_path': settings['savedvariables_path'],
                'addon_installed': bool(chosen and is_installed(chosen)),
                'config_path': str(config_path()), 'data_dir': str(data_dir)}

    @app.post('/api/setup/scan')
    async def scan():
        """Looks through the usual game folders. Only ever runs when the person asks for it."""
        found = await asyncio.to_thread(find_installs, search_roots())
        installs = [{'path': str(i.auctionator), 'folder': str(i.savedvariables), 'account': i.account,
                     'flavor': i.flavor, 'has_prices': i.has_prices,
                     'addon_installed': is_installed(i.auctionator)} for i in found]
        return {'installs': installs}

    @app.post('/api/setup')
    def choose(body: dict = Body(...)):
        path = Path(str(body.get('savedvariables_path') or '')).expanduser()
        if path.is_dir():
            path = path / 'Auctionator.lua'
        if looks_like_addon_code(path):
            raise HTTPException(400, 'That is Auctionator\'s own code. The file we need is the saved data, '
                                     'under WTF\\Account\\<your id>\\SavedVariables')
        if not path.parent.is_dir():
            raise HTTPException(400, f'{path.parent} does not exist')
        if path.parent.name != 'SavedVariables':
            raise HTTPException(400, 'Pick the Auctionator.lua inside a SavedVariables folder')
        use_savedvariables(path)
        return {'configured': True, 'waiting_for_prices': not path.is_file(), **importer.status}

    @app.post('/api/install-addon')
    def add_addon():
        path = Path(store.settings()['savedvariables_path'] or '')
        if not path.is_file():
            raise HTTPException(400, 'Choose your World of Warcraft folder first')
        try:
            return {'installed': str(install_addon(path))}
        except (FileExistsError, OSError) as e:
            raise HTTPException(400, str(e))

    @app.post('/api/quit')
    async def quit_app():
        async def stop():
            await asyncio.sleep(0.2)
            os.kill(os.getpid(), signal.SIGINT)

        asyncio.create_task(stop())
        return {'stopping': True}

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
        named = lambda counts: [{'item_id': i, 'name': (calc.items.get(i) or {}).get('name') or str(i),
                                 'quantity': n} for i, n in sorted(counts.items())]
        return {**asdict(result), 'budget': budget,
                'owned_used': named(result.owned_used), 'leftovers': named(result.leftovers)}

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

    def character_parts(key: str, settings: dict) -> tuple[str, str]:
        # The addon keys characters "Name - Realm"; a realm name may hold a space.
        name, separator, realm = key.rpartition(' - ')
        return (name, realm) if separator else (key, settings['realm'] or 'unknown')

    @app.get('/api/share')
    def share():
        s = store.settings()
        return {'server_url': s['server_url'], 'username': s['server_username'],
                'signed_in': bool(s['server_token']), 'push_prices': bool(s['push_prices']),
                'published_characters': s['published_characters']}

    def _sign_in(body: dict, register: bool) -> dict:
        # The address is a setting, so a person who never opens Settings shares with the
        # server the app ships with.
        url, username = str(store.settings()['server_url'] or ''), str(body.get('username') or '')
        try:
            client = PushClient(url)
            token = (client.register if register else client.login)(username, str(body.get('password') or ''))
        except PushError as e:
            raise HTTPException(400, str(e))
        store.save_settings({'server_username': username, 'server_token': token})
        return {'signed_in': True, 'username': username}

    @app.post('/api/share/login')
    def share_login(body: dict = Body(...)):
        return _sign_in(body, register=False)

    @app.post('/api/share/register')
    def share_register(body: dict = Body(...)):
        return _sign_in(body, register=True)

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
        for character, was in (settings['published_characters'] if 'published_characters' in allowed else {}).items():
            if was and not allowed['published_characters'].get(character):
                name, realm = character_parts(character, settings)
                try:
                    PushClient(settings['server_url'],
                               settings['server_token']).unpublish_character(realm, name)
                except PushError as e:
                    # Saving the switch as off while the site still holds the character
                    # would tell the person a lie they cannot see through.
                    log.warning('unpublish failed: %s', e)
                    raise HTTPException(400, f'{character} is still published: {e}')
        return store.save_settings(allowed)

    @app.post('/api/share/push')
    def share_push():
        settings = store.settings()
        if not (settings['server_url'] and settings['server_token']):
            raise HTTPException(400, 'Sign in on the Share tab first')
        scan_id = store.latest_scan_id()
        if scan_id:
            push_scan(scan_id)
        client = PushClient(settings['server_url'], settings['server_token'])
        for export in load_exports(Path(settings['export_path']).expanduser()):
            if not settings['published_characters'].get(export.character):
                continue
            name, realm = character_parts(export.character, settings)
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

    # Mounted last: a mount swallows every path registered after it.
    app.mount('/', StaticFiles(directory=STATIC), name='static')
    return app


def run() -> None:
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    config = load_config()
    port = int(os.environ.get('ANVILBOOK_PORT') or config.port)
    url = f'http://{config.host}:{port}/'
    if config.open_browser and os.environ.get('ANVILBOOK_NO_BROWSER') != '1':
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f'anvilbook is running. Open {url} in your browser. Press Ctrl+C to stop.')
    uvicorn.run(create_app(config.data_dir), host=config.host, port=port, log_level='warning')

"""The in-game UI, on a data file the app wrote, and on live Auctionator prices alone."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from anvilbook.app import create_app
from anvilbook.bridge import FILE_NAME
from anvilbook.installer import install_addon, target_dir
from anvilbook.luatable import parse_savedvariables
from lua_fixture import entry, savedvariables
from test_app import GAME_EXPORT, ITEMS, PRICES, game_install

ADDON = Path(__file__).parent.parent / 'src/anvilbook/addon/AnvilbookExport'
HARNESS = Path(__file__).parent / 'addon_harness_ui.lua'

pytestmark = pytest.mark.skipif(not shutil.which('luajit'), reason='needs luajit')


def harness(*args) -> None:
    out = subprocess.run(['luajit', str(HARNESS), str(ADDON), *map(str, args)], capture_output=True, text=True)
    assert out.returncode == 0 and out.stdout.strip() == 'OK', out.stdout + out.stderr


@pytest.fixture
def written(tmp_path, monkeypatch):
    monkeypatch.setenv('ANVILBOOK_CONFIG', str(tmp_path / 'config.toml'))
    monkeypatch.setattr('anvilbook.app.search_roots', lambda: [])
    data = tmp_path / 'data'
    data.mkdir()
    (data / 'items.json').write_text(json.dumps(ITEMS))
    sv = game_install(tmp_path)
    install_addon(sv)
    sv.with_name('AnvilbookExport.lua').write_bytes(GAME_EXPORT)
    with TestClient(create_app(data, watch=False)) as client:
        client.put('/api/settings', json={'min_scan_items': 1})
        assert client.post('/api/setup', json={'savedvariables_path': str(sv)}).status_code == 200
        later = {str(i): entry(p + 10, 2454, 80) for i, p in PRICES.items()}
        sv.write_bytes(savedvariables(later))
        assert client.post('/api/import').json()['scan_id'] == 2
        client.app.state.sync_game()
    return target_dir(sv) / FILE_NAME


def test_the_app_writes_the_data_file(written):
    data = parse_savedvariables(written.read_bytes())['AnvilbookData']
    assert data['version'] == 1 and len(data['scans']) == 2
    assert data['items'][3490].endswith('|Deadly Bronze Poniard')
    assert data['history'][3490] == '17500,100;17510,80'
    assert '3490:17510:80:' in data['prices']


def test_the_ui_runs_on_app_data(written):
    harness(written)


def test_the_ui_runs_on_live_prices_alone():
    harness()

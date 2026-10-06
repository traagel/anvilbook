import json
import time

import pytest
from fastapi.testclient import TestClient

from anvilbook import bridge
from anvilbook.app import create_app
from anvilbook.installer import install_addon, target_dir
from anvilbook.luatable import parse_savedvariables
from anvilbook.push import PushError
from anvilbook.store import Store
from test_app import GAME_EXPORT, ITEMS, game_install


def test_lua_text_reads_back_with_the_apps_parser():
    value = {'name': 'Quote " and \\ and\nnewline', 'n': 3, 'f': 0.05, 'yes': True, 'skip': None,
             'list': [1, 2.5, 'x'], 'nested': {7: {'deep': []}}}
    parsed = parse_savedvariables(('V = ' + bridge.to_lua(value)).encode())['V']
    assert parsed == {'name': value['name'], 'n': 3, 'f': 0.05, 'yes': True, 'list': {1: 1, 2: 2.5, 3: 'x'},
                      'nested': {7: {'deep': {}}}}


def test_lua_text_refuses_what_lua_cannot_hold():
    with pytest.raises(ValueError):
        bridge.to_lua(float('inf'))


def test_only_newer_valid_game_edits_are_taken():
    edits = {'ah_cut': (0.06, 200), 'min_listed': (5, 100), 'cast_seconds': ('soon', 300),
             'max_use_level': (25.0, 300), 'published_characters': ({'A - R': 1}, 300)}
    taken = bridge.accepted(edits, {'ah_cut': 150, 'min_listed': 150})
    assert taken == {'ah_cut': 0.06, 'max_use_level': 25, 'published_characters': {'A - R': True}}


def test_an_out_of_range_edit_is_ignored():
    assert bridge.accepted({'ah_cut': (1.5, 10)}, {}) == {}


def test_saving_stamps_only_the_keys_that_changed(tmp_path):
    store = Store(tmp_path / 'db')
    store.save_settings({'ah_cut': 0.05, 'min_listed': 4})
    stamped = store.settings()['changed_at']
    assert set(stamped) == {'min_listed'}
    assert abs(stamped['min_listed'] - time.time()) < 5


EDITED = GAME_EXPORT.replace(b'AnvilbookExportDB = {', b'''AnvilbookExportDB = {
["edits"] = {
["ah_cut"] = { ["value"] = 0.07, ["time"] = 4102444800, },
["push_prices"] = { ["value"] = true, ["time"] = 4102444800, },
["published_characters"] = { ["value"] = { ["Thordak - Classic Beta PvP"] = true, }, ["time"] = 4102444800, },
["skills"] = { ["value"] = { ["Mining"] = 300, }, ["time"] = 4102444800, },
},
["pushRequested"] = 4102444800,''')


@pytest.fixture
def app_env(tmp_path, monkeypatch):
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
        client.post('/api/setup', json={'savedvariables_path': str(sv)})
        yield client, sv


def test_the_data_file_is_rewritten_only_when_something_changed(app_env):
    client, sv = app_env
    path = target_dir(sv) / bridge.FILE_NAME
    client.app.state.sync_game()
    first = path.stat().st_mtime_ns
    client.app.state.sync_game()
    assert path.stat().st_mtime_ns == first
    client.put('/api/settings', json={'min_listed': 7})
    client.app.state.sync_game()
    assert 'min_listed' in path.read_text() and path.stat().st_mtime_ns != first


def test_an_unreadable_export_does_not_stop_the_data_file(app_env):
    client, sv = app_env
    sv.with_name('AnvilbookExport.lua').write_bytes(b'AnvilbookExportDB = { ["characters"] = ')
    client.app.state.sync_game()
    data = parse_savedvariables((target_dir(sv) / bridge.FILE_NAME).read_bytes())['AnvilbookData']
    assert data['version'] == bridge.FORMAT


def test_the_install_button_gets_the_data_file_back(app_env):
    client, sv = app_env
    client.app.state.sync_game()
    assert client.post('/api/install-addon').status_code == 200
    data = parse_savedvariables((target_dir(sv) / bridge.FILE_NAME).read_bytes())
    assert data['AnvilbookData']['version'] == bridge.FORMAT


def test_game_edits_and_push_requests_reach_the_app(app_env, monkeypatch):
    client, sv = app_env
    calls = []

    class Client:
        def __init__(self, url, token=None):
            pass

        def push_scan(self, *args):
            calls.append('scan')

        def push_character(self, realm, name, *args):
            calls.append(name)

    monkeypatch.setattr('anvilbook.app.PushClient', Client)
    client.put('/api/settings', json={'server_token': 'secret'})
    sv.with_name('AnvilbookExport.lua').write_bytes(EDITED)
    client.app.state.sync_game()
    settings = client.get('/api/settings').json()
    assert settings['ah_cut'] == 0.07
    assert settings['published_characters'] == {'Thordak - Classic Beta PvP': True}
    assert settings['skills'] != {'Mining': 300}, 'the game may not change every setting'
    assert settings['game_push_handled'] == 4102444800
    assert calls == ['scan', 'Thordak']

    calls.clear()
    client.app.state.sync_game()
    assert calls == [], 'a push request is handled once'


def test_a_failed_unpublish_keeps_the_other_game_edits(app_env, monkeypatch):
    client, sv = app_env

    class Client:
        def __init__(self, url, token=None):
            pass

        def unpublish_character(self, realm, name):
            raise PushError('server down')

    monkeypatch.setattr('anvilbook.app.PushClient', Client)
    client.put('/api/settings', json={'published_characters': {'Thordak - Classic Beta PvP': True}})
    sv.with_name('AnvilbookExport.lua').write_bytes(EDITED.replace(b'= true, }, ["time"]', b'= false, }, ["time"]'))
    client.app.state.sync_game()
    settings = client.get('/api/settings').json()
    assert settings['push_prices'] is True
    assert settings['published_characters'] == {'Thordak - Classic Beta PvP': True}
    assert 'still published' in client.get('/api/status').json()['push_error']

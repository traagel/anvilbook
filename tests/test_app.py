import json

import pytest
from fastapi.testclient import TestClient

from anvilbook.app import create_app
from anvilbook.push import PushError
from lua_fixture import entry, savedvariables


def recipe(skill, reagents, amount=(1, 1)):
    return {'amount': list(amount), 'requiredSkill': skill, 'category': 'Mining',
            'reagents': [{'itemId': i, 'amount': n} for i, n in reagents]}


ITEMS = [
    {'itemId': 3490, 'name': 'Deadly Bronze Poniard', 'requiredLevel': 20, 'quality': 'Uncommon',
     'itemLevel': 25, 'class': 'Weapon',
     'createdBy': [{'amount': [1, 1], 'requiredSkill': 100, 'category': 'Blacksmithing',
                    'reagents': [{'itemId': 2841, 'amount': 4}]}]},
    {'itemId': 2770, 'name': 'Copper Ore'},
    {'itemId': 2771, 'name': 'Tin Ore'},
    {'itemId': 2840, 'name': 'Copper Bar', 'createdBy': [recipe(1, [(2770, 1)])]},
    {'itemId': 3576, 'name': 'Tin Bar', 'createdBy': [recipe(65, [(2771, 1)])]},
    {'itemId': 2841, 'name': 'Bronze Bar', 'createdBy': [recipe(65, [(2840, 1), (3576, 1)], (2, 2))]},
]
PRICES = {2770: 57, 2771: 200, 2840: 73, 3576: 248, 2841: 220, 3490: 17500}


def game_install(tmp_path, account='1#1'):
    game = tmp_path / f'wow-{account}' / '_classic_beta_' / 'WTF' / 'Account' / account / 'SavedVariables'
    game.mkdir(parents=True)
    sv = game / 'Auctionator.lua'
    sv.write_bytes(savedvariables({str(i): entry(p, 2453, 100) for i, p in PRICES.items()}))
    return sv


def setup_env(tmp_path, monkeypatch):
    data = tmp_path / 'data'
    data.mkdir()
    (data / 'items.json').write_text(json.dumps(ITEMS))
    monkeypatch.setenv('ANVILBOOK_CONFIG', str(tmp_path / 'config.toml'))
    monkeypatch.setattr('anvilbook.app.search_roots', lambda: [tmp_path])
    return data


def test_nothing_is_searched_until_asked(tmp_path, monkeypatch):
    data = setup_env(tmp_path, monkeypatch)
    sv = game_install(tmp_path)
    scans = []
    monkeypatch.setattr('anvilbook.app.search_roots', lambda: scans.append('searched') or [tmp_path])

    with TestClient(create_app(data, watch=False)) as client:
        setup = client.get('/api/setup').json()
        assert setup == {'configured': False, 'installs': [], 'savedvariables_path': '',
                         'addon_installed': False,
                         'config_path': str(tmp_path / 'config.toml'), 'data_dir': str(data)}
        assert scans == []

        found = client.post('/api/setup/scan').json()
        assert scans == ['searched']
        assert [i['path'] for i in found['installs']] == [str(sv)]
        assert found['installs'][0]['addon_installed'] is False
        assert found['installs'][0]['has_prices'] is True
        assert client.get('/api/settings').json()['savedvariables_path'] == ''


def test_choosing_a_folder_configures_the_app(tmp_path, monkeypatch):
    data = setup_env(tmp_path, monkeypatch)
    first, second = game_install(tmp_path, '1#1'), game_install(tmp_path, '2#1')
    monkeypatch.setattr('anvilbook.app.search_roots', lambda: [tmp_path])

    with TestClient(create_app(data, watch=False)) as client:
        assert sorted(i['path'] for i in client.post('/api/setup/scan').json()['installs']) == \
            sorted([str(first), str(second)])

        assert client.post('/api/setup', json={'savedvariables_path': str(second)}).json()['configured'] is True
        assert client.get('/api/settings').json()['savedvariables_path'] == str(second)
        assert client.get('/api/settings').json()['export_path'] == str(second.with_name('AnvilbookExport.lua'))
        assert client.get('/api/status').json()['found'] is True

        installed = client.post('/api/install-addon').json()
        assert installed['installed'].endswith('AddOns/AnvilbookExport')
        after = {i['path']: i['addon_installed'] for i in client.post('/api/setup/scan').json()['installs']}
        assert after == {str(first): False, str(second): True}

        missing = client.post('/api/setup', json={'savedvariables_path': str(tmp_path / 'nope.lua')})
        assert missing.status_code == 400


def test_setup_accepts_the_folder_and_warns_about_addon_code(tmp_path, monkeypatch):
    data = setup_env(tmp_path, monkeypatch)
    sv = game_install(tmp_path)

    with TestClient(create_app(data, watch=False)) as client:
        folder = client.post('/api/setup', json={'savedvariables_path': str(sv.parent)})
        assert folder.status_code == 200
        assert client.get('/api/settings').json()['savedvariables_path'] == str(sv)

        code = tmp_path / 'wow-1#1' / '_classic_beta_' / 'Interface' / 'AddOns' / 'Auctionator' / 'Source'
        code.mkdir(parents=True)
        (code / 'Auctionator.lua').write_text('-- addon code')
        wrong = client.post('/api/setup', json={'savedvariables_path': str(code / 'Auctionator.lua')})
        assert wrong.status_code == 400
        assert 'SavedVariables' in wrong.json()['detail']


def test_a_configured_path_is_reused_without_searching(tmp_path, monkeypatch):
    data = setup_env(tmp_path, monkeypatch)
    sv = game_install(tmp_path)
    (tmp_path / 'config.toml').write_text(f'savedvariables_path = "{sv}"\n')
    monkeypatch.setattr('anvilbook.app.search_roots', lambda: pytest.fail('should not search'))

    with TestClient(create_app(data, watch=False)) as client:
        assert client.get('/api/setup').json()['configured'] is True
        assert client.get('/api/settings').json()['savedvariables_path'] == str(sv)


@pytest.fixture
def env(tmp_path, monkeypatch):
    # Without this the tests would find, and import, the real game on this machine.
    monkeypatch.setattr('anvilbook.app.search_roots', lambda: [])
    monkeypatch.setenv('ANVILBOOK_CONFIG', str(tmp_path / 'config.toml'))
    data = tmp_path / 'data'
    data.mkdir()
    (data / 'items.json').write_text(json.dumps(ITEMS))
    sv = tmp_path / 'Auctionator.lua'
    sv.write_bytes(savedvariables({str(i): entry(p, 2453, 100) for i, p in PRICES.items()}))
    with TestClient(create_app(data, watch=False)) as client:
        res = client.put('/api/settings', json={'savedvariables_path': str(sv), 'min_scan_items': 1,
                                                'export_path': str(tmp_path / 'AnvilbookExport.lua')})
        assert res.status_code == 200
        yield client, sv


def test_import_and_crafts(env):
    client, _ = env
    assert client.post('/api/import').json()['scan_id'] == 1
    assert client.post('/api/import').json()['scan_id'] is None
    names = [r['name'] for r in client.get('/api/crafts').json()]
    assert 'Bronze Bar' in names
    status = client.get('/api/status').json()
    assert (status['scans'], status['export']) == (1, None)


GAME_EXPORT = b'''
AnvilbookExportDB = {
["characters"] = {
["Thordak - Classic Beta PvP"] = {
["updated"] = 200,
["professions"] = {
["Smelting"] = {
["rank"] = 99,
["maxRank"] = 150,
["recipes"] = {
[2840] = { ["name"] = "Copper Bar", ["minMade"] = 1, ["maxMade"] = 1, ["difficulty"] = "trivial",
  ["reagents"] = { { ["id"] = 2770, ["count"] = 1, }, }, },
[3576] = { ["name"] = "Tin Bar", ["minMade"] = 1, ["maxMade"] = 1, ["difficulty"] = "easy",
  ["reagents"] = { { ["id"] = 2771, ["count"] = 1, }, }, },
[2841] = { ["name"] = "Bronze Bar", ["minMade"] = 2, ["maxMade"] = 2, ["difficulty"] = "easy",
  ["reagents"] = { { ["id"] = 2840, ["count"] = 2, }, { ["id"] = 3576, ["count"] = 1, }, }, },
},
},
},
},
},
}
'''


SECOND_CHARACTER = b'''
AnvilbookExportDB = {
["characters"] = {
["Thordak - Classic Beta PvP"] = {
["updated"] = 200,
["professions"] = {
["Smelting"] = {
["rank"] = 99,
["maxRank"] = 150,
["recipes"] = {
[2840] = { ["name"] = "Copper Bar", ["minMade"] = 1, ["maxMade"] = 1, ["difficulty"] = "trivial",
  ["reagents"] = { { ["id"] = 2770, ["count"] = 1, }, }, },
},
},
},
},
["Eilistaree - Classic Beta PvP"] = {
["updated"] = 100,
["professions"] = {
["Mining"] = {
["rank"] = 40,
["maxRank"] = 150,
["recipes"] = {
[3576] = { ["name"] = "Tin Bar", ["minMade"] = 1, ["maxMade"] = 1, ["difficulty"] = "optimal",
  ["reagents"] = { { ["id"] = 2771, ["count"] = 1, }, }, },
},
},
},
},
},
}
'''


def test_character_can_be_selected(env, tmp_path):
    client, _ = env
    (tmp_path / 'AnvilbookExport.lua').write_bytes(SECOND_CHARACTER)
    client.post('/api/import')
    chars = client.get('/api/characters').json()
    assert [c['character'] for c in chars] == ['Thordak - Classic Beta PvP', 'Eilistaree - Classic Beta PvP']
    assert chars[1]['maxRanks'] == {'Mining': 150}
    status = client.get('/api/status').json()
    assert (status['export']['character'], status['pinned']) == ('Thordak - Classic Beta PvP', None)
    assert [r['name'] for r in client.get('/api/crafts').json()] == ['Copper Bar']

    client.put('/api/settings', json={'character': 'Eilistaree - Classic Beta PvP'})

    status = client.get('/api/status').json()
    assert status['export']['character'] == 'Eilistaree - Classic Beta PvP'
    assert status['pinned'] == 'Eilistaree - Classic Beta PvP'
    assert status['export']['professions'] == {'Mining': 40}
    # The database still knows a Blacksmithing recipe, but this character has no Blacksmithing.
    assert [r['name'] for r in client.get('/api/crafts').json()] == ['Tin Bar']


def test_disenchant_needs_enchanting_or_the_assume_switch(env):
    client, _ = env
    client.post('/api/import')
    poniard = lambda: next(r for r in client.get('/api/crafts').json() if r['item_id'] == 3490)
    assert (poniard()['exit'], poniard()['de_value']) == ('sell', 0)

    client.put('/api/settings', json={
        'assume_enchanter': True,
        'disenchant_table': [{'quality': 'Uncommon', 'maxLevel': 25, 'weapon': [[2841, 1.0, 100]], 'armor': []}]})

    assert poniard()['exit'] == 'disenchant'
    assert poniard()['de_value'] == pytest.approx(100 * 220 * 0.95)


MEASURED = b'''
AnvilbookExportDB = {
["disenchants"] = {
{ ["time"] = 1, ["item"] = { ["id"] = 3490, ["quality"] = 2, ["itemLevel"] = 25, ["kind"] = "Weapon", },
  ["mats"] = { { ["id"] = 2841, ["count"] = 4, }, }, }, -- [1]
{ ["time"] = 2, ["item"] = { ["id"] = 3490, ["quality"] = 2, ["itemLevel"] = 25, ["kind"] = "Weapon", },
  ["mats"] = { { ["id"] = 2841, ["count"] = 6, }, }, }, -- [2]
},
}
'''


def test_measured_disenchants_replace_the_table(env, tmp_path):
    client, _ = env
    (tmp_path / 'AnvilbookExport.lua').write_bytes(MEASURED)
    client.post('/api/import')
    client.put('/api/settings', json={
        'assume_enchanter': True, 'min_disenchant_samples': 2,
        'disenchant_table': [{'quality': 'Uncommon', 'maxLevel': 25, 'weapon': [[2841, 1.0, 1]], 'armor': []}]})

    measured = client.get('/api/disenchants').json()
    assert measured == [{'quality': 'Uncommon', 'maxLevel': 25, 'kind': 'weapon', 'samples': 2,
                         'yields': [{'item_id': 2841, 'name': 'Bronze Bar', 'chance': 1.0, 'quantity': 5.0}],
                         'used': True}]

    poniard = next(r for r in client.get('/api/crafts').json() if r['item_id'] == 3490)
    assert poniard['de_value'] == pytest.approx(5 * 220 * 0.95)


BAGS = b'''
AnvilbookExportDB = {
["characters"] = {
["Thordak - Classic Beta PvP"] = {
["updated"] = 200,
["bags"] = { [2840] = 2, },
["professions"] = {
["Smelting"] = {
["rank"] = 99, ["maxRank"] = 150,
["recipes"] = {
[2841] = { ["name"] = "Bronze Bar", ["minMade"] = 2, ["maxMade"] = 2, ["difficulty"] = "easy",
  ["reagents"] = { { ["id"] = 2840, ["count"] = 1, }, { ["id"] = 3576, ["count"] = 1, }, }, },
},
},
},
},
},
}
'''


def test_plan_for_a_budget(env, tmp_path):
    client, _ = env
    (tmp_path / 'AnvilbookExport.lua').write_bytes(BAGS)
    client.post('/api/import')

    plan = client.get('/api/plan', params={'item_id': 2841, 'budget': 600}).json()

    assert plan['name'] == 'Bronze Bar'
    assert plan['count'] == 4
    # 2 copper bars are already in the bags, so only tin is bought.
    assert {p['name']: p['quantity'] for p in plan['purchases']} == {'Tin Bar': 2}
    assert [s['name'] for s in plan['steps']] == ['Bronze Bar']
    assert plan['owned_used'] == [{'item_id': 2840, 'name': 'Copper Bar', 'quantity': 2}]
    assert plan['cost'] == 496

    broke = client.get('/api/plan', params={'item_id': 2841, 'budget': 10}).json()
    assert broke['count'] == 0 and broke['short_by'] > 0


def test_crafts_use_game_recipes(env, tmp_path):
    client, _ = env
    (tmp_path / 'AnvilbookExport.lua').write_bytes(GAME_EXPORT)
    client.post('/api/import')
    bronze = next(r for r in client.get('/api/crafts').json() if r['item_id'] == 2841)
    # Game recipe needs 2 Copper Bars: best per cast is 2 bought bars + smelted tin (146 + 200, 2 casts).
    assert (bronze['cost'], bronze['casts'], bronze['difficulty']) == (346, 2, 'easy')
    export = client.get('/api/status').json()['export']
    assert export['character'] == 'Thordak - Classic Beta PvP'
    assert export['professions'] == {'Mining': 99}


def test_search_and_history(env):
    client, _ = env
    client.post('/api/import')
    hits = client.get('/api/items/search', params={'q': 'bronze'}).json()
    assert [h['item_id'] for h in hits] == [2841, 3490]
    points = client.get('/api/items/2841/history').json()['points']
    assert [(p['min_price'], p['available']) for p in points] == [(220, 100)]
    assert client.get('/api/items/999999/history').status_code == 404


def test_sellthrough_between_two_scans(env):
    client, sv = env
    client.post('/api/import')
    assert client.get('/api/sellthrough').json()['rows'] == []
    sv.write_bytes(savedvariables({'2841': entry(220, 2454, 40)}))
    client.post('/api/import')
    res = client.get('/api/sellthrough').json()
    assert (res['from'], res['to']) == (1, 2)
    bronze = next(r for r in res['rows'] if r['item_id'] == 2841)
    assert (bronze['change'], bronze['name']) == (-60, 'Bronze Bar')


def test_empty_database_is_not_stored(env):
    client, sv = env
    sv.write_bytes(savedvariables({'version': 2}))
    res = client.post('/api/import').json()
    assert res['scan_id'] is None
    assert 'no price data' in res['last_error']
    assert client.get('/api/scans').json() == []


def test_partial_or_wiped_save_is_not_stored(env):
    client, sv = env
    client.put('/api/settings', json={'min_scan_items': 3})
    sv.write_bytes(savedvariables({'2862': entry(4, 2456, 1), '2841': entry(220, 2455, 40)}))
    res = client.post('/api/import').json()
    assert res['scan_id'] is None
    assert 'full AH scan' in res['last_error']
    assert client.get('/api/scans').json() == []


def test_missing_file_reports_status(env):
    client, sv = env
    sv.unlink()
    res = client.post('/api/import').json()
    assert res['found'] is False


def test_bad_settings_are_rejected(env):
    client, _ = env
    assert client.put('/api/settings', json={'bogus': 1}).status_code == 400
    assert client.put('/api/settings', json={'min_listed': 'x'}).status_code == 400


def test_sharing_is_off_until_asked(env):
    client, _ = env
    share = client.get('/api/share').json()
    # A server address is filled in, which shares nothing on its own.
    assert share == {'server_url': 'https://anvilbook.traagel.dev', 'username': '', 'signed_in': False,
                     'push_prices': False, 'published_characters': {}}


def test_the_server_address_comes_from_the_settings(env):
    client, _ = env
    client.put('/api/settings', json={'server_url': 'https://exa mple.com'})
    response = client.post('/api/share/login', json={'username': 'thordak', 'password': 'a long password'})
    assert response.status_code == 400
    assert response.json()['detail']


def test_a_failed_push_does_not_break_the_import(env, monkeypatch):
    client, sv = env
    client.put('/api/settings', json={'server_url': 'https://example.com',
                                      'server_token': 'abc', 'push_prices': True})

    class Failing:
        def __init__(self, *args, **kw):
            pass

        def push_scan(self, *args, **kw):
            raise PushError('Could not reach the server')

    monkeypatch.setattr('anvilbook.app.PushClient', Failing)
    sv.write_bytes(savedvariables({'2770': entry(57, 2460, 100)}))

    assert client.post('/api/import').json()['scan_id'] is not None
    assert 'Could not reach the server' in client.get('/api/status').json()['push_error']


def test_a_failed_unpublish_keeps_the_switch_on(env, monkeypatch):
    client, _ = env
    client.put('/api/settings', json={'server_url': 'https://example.com', 'server_token': 'abc',
                                      'published_characters': {'Thordak - Forever': True}})

    class Failing:
        def __init__(self, *args, **kw):
            pass

        def unpublish_character(self, *args, **kw):
            raise PushError('Could not reach the server')

    monkeypatch.setattr('anvilbook.app.PushClient', Failing)
    response = client.put('/api/share/settings', json={'published_characters': {'Thordak - Forever': False}})

    assert response.status_code == 400
    # The site still holds the character, so the switch must not read as off.
    assert client.get('/api/share').json()['published_characters'] == {'Thordak - Forever': True}


def test_a_mistyped_server_address_is_explained_not_a_500(env):
    client, _ = env
    client.put('/api/settings', json={'server_url': 'https://[::1'})
    response = client.post('/api/share/login', json={'username': 'thordak', 'password': 'a long password'})
    assert response.status_code == 400
    assert response.json()['detail']


def test_status_carries_the_running_version(env):
    client, _ = env
    import anvilbook
    # Read from the source, not the installed metadata: the frozen exe has no metadata.
    assert client.get('/api/status').json()['version'] == anvilbook.__version__
    assert anvilbook.__version__[0].isdigit()


def test_index_and_its_files_are_served(env):
    client, _ = env
    assert 'anvilbook' in client.get('/').text
    logo = client.get('/logo.svg')
    assert logo.status_code == 200
    assert logo.headers['content-type'].startswith('image/svg')

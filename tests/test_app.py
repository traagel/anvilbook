import json

import pytest
from fastapi.testclient import TestClient

from anvilbook.app import create_app
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


@pytest.fixture
def env(tmp_path):
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
    assert plan['owned_used'] == {'2840': 2}
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


def test_index_is_served(env):
    client, _ = env
    assert 'anvilbook' in client.get('/').text

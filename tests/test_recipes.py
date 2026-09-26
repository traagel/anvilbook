import copy

from anvilbook.recipes import export_skills, load_export, load_exports, merge

EXPORT = b'''
AnvilbookExportDB = {
["version"] = 1,
["characters"] = {
["Old - Realm"] = {
["updated"] = 100,
["professions"] = {
["Blacksmithing"] = { ["rank"] = 50, ["maxRank"] = 75, ["updated"] = 100, ["recipes"] = {}, },
},
},
["Thordak - Classic Beta PvP"] = {
["updated"] = 200,
["professions"] = {
["Blacksmithing"] = {
["rank"] = 147,
["maxRank"] = 150,
["updated"] = 200,
["recipes"] = {
[3490] = {
["name"] = "Deadly Bronze Poniard",
["minMade"] = 1,
["maxMade"] = 1,
["difficulty"] = "optimal",
["reagents"] = {
{ ["id"] = 2841, ["count"] = 3, ["name"] = "Bronze Bar", }, -- [1]
{ ["id"] = 99999, ["count"] = 1, ["name"] = "Forever Ingot", }, -- [2]
},
},
[88888] = {
["name"] = "Forever Blade",
["minMade"] = 1,
["maxMade"] = 1,
["difficulty"] = "medium",
["reagents"] = { { ["id"] = 2841, ["count"] = 2, ["name"] = "Bronze Bar", }, },
},
},
},
["Smelting"] = {
["rank"] = 99,
["maxRank"] = 150,
["updated"] = 150,
["recipes"] = {
[2841] = {
["name"] = "Bronze Bar",
["minMade"] = 2,
["maxMade"] = 2,
["difficulty"] = "easy",
["reagents"] = {
{ ["id"] = 2840, ["count"] = 1, ["name"] = "Copper Bar", }, -- [1]
{ ["id"] = 3576, ["count"] = 1, ["name"] = "Tin Bar", }, -- [2]
},
},
},
},
},
},
},
}
'''.replace(b'\n', b'\r\n')


def db_recipe(category, skill, reagents, amount=(1, 1)):
    return {'amount': list(amount), 'requiredSkill': skill, 'category': category,
            'reagents': [{'itemId': i, 'amount': n} for i, n in reagents]}


ITEMS = {
    3490: {'name': 'Deadly Bronze Poniard', 'requiredLevel': 20,
           'createdBy': [db_recipe('Blacksmithing', 125, [(2841, 4)])]},
    2871: {'name': 'Heavy Sharpening Stone', 'createdBy': [db_recipe('Blacksmithing', 125, [(2838, 1)])]},
    2842: {'name': 'Silver Bar', 'createdBy': [db_recipe('Mining', 75, [(2775, 1)])]},
    5000: {'name': 'Some Potion', 'createdBy': [db_recipe('Alchemy', 50, [(765, 1)])]},
    2841: {'name': 'Bronze Bar', 'createdBy': [db_recipe('Mining', 65, [(2840, 1), (3576, 1)], (2, 2))]},
}


def export(tmp_path):
    path = tmp_path / 'AnvilbookExport.lua'
    path.write_bytes(EXPORT)
    return load_export(path)


def test_load_export_picks_latest_character_and_maps_smelting(tmp_path):
    exp = export(tmp_path)
    assert exp is not None
    assert (exp.character, exp.updated) == ('Thordak - Classic Beta PvP', 200)
    assert set(exp.professions) == {'Blacksmithing', 'Mining'}
    assert export_skills(exp) == {'Blacksmithing': 147, 'Mining': 99}


def test_load_exports_lists_characters_newest_first(tmp_path):
    path = tmp_path / 'AnvilbookExport.lua'
    path.write_bytes(EXPORT)
    assert [e.character for e in load_exports(path)] == ['Thordak - Classic Beta PvP', 'Old - Realm']


def test_load_export_picks_a_named_character(tmp_path):
    path = tmp_path / 'AnvilbookExport.lua'
    path.write_bytes(EXPORT)
    old = load_export(path, 'Old - Realm')
    assert old is not None and export_skills(old) == {'Blacksmithing': 50}
    unknown = load_export(path, 'Nobody')
    assert unknown is not None and unknown.character == 'Thordak - Classic Beta PvP'


def test_a_character_that_is_only_playing_counts_as_most_recent(tmp_path):
    path = tmp_path / 'AnvilbookExport.lua'
    path.write_bytes(EXPORT.replace(
        b'["Old - Realm"] = {\r\n["updated"] = 100,',
        b'["Old - Realm"] = {\r\n["updated"] = 100,\r\n["bagsUpdated"] = 300,'))
    latest = load_export(path)
    assert latest is not None and latest.character == 'Old - Realm'


def test_load_export_without_data(tmp_path):
    assert load_export(tmp_path / 'missing.lua') is None
    empty = tmp_path / 'empty.lua'
    empty.write_bytes(b'AnvilbookExportDB = nil\r\n')
    assert load_export(empty) is None


def test_merge_replaces_exported_professions(tmp_path):
    exp = export(tmp_path)
    assert exp is not None
    before = copy.deepcopy(ITEMS)

    merged = merge(ITEMS, exp)

    assert merged[3490]['createdBy'] == [{
        'amount': [1, 1], 'requiredSkill': 0, 'category': 'Blacksmithing', 'known': True,
        'difficulty': 'optimal', 'reagents': [{'itemId': 2841, 'amount': 3}, {'itemId': 99999, 'amount': 1}]}]
    assert merged[3490]['requiredLevel'] == 20
    assert merged[2871]['createdBy'] == []
    assert merged[2842]['createdBy'] == []
    assert merged[5000]['createdBy'] == ITEMS[5000]['createdBy']
    assert merged[2841]['createdBy'][0]['amount'] == [2, 2]
    assert merged[2841]['createdBy'][0]['category'] == 'Mining'
    assert merged[99999] == {'name': 'Forever Ingot'}
    assert merged[88888]['name'] == 'Forever Blade'
    assert merged[88888]['createdBy'][0]['difficulty'] == 'medium'
    assert ITEMS == before

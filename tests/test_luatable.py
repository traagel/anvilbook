import pytest

from anvilbook.luatable import LuaParseError, parse_savedvariables

NESTED = b'''
AnvilbookExportDB = {
["version"] = 1,
["characters"] = {
["Thordak - Classic Beta PvP"] = {
["updated"] = 1790000000,
["professions"] = {
["Blacksmithing"] = {
["rank"] = 147,
["recipes"] = {
[3490] = {
["name"] = "Deadly \\"Bronze\\" Poniard",
["reagents"] = {
{
["id"] = 2841,
["count"] = 4,
}, -- [1]
{
["id"] = 3466,
["count"] = 1,
}, -- [2]
},
},
},
},
},
},
},
}
OTHER = nil
'''.replace(b'\n', b'\r\n')


def test_nested_tables_and_array_items():
    out = parse_savedvariables(NESTED)
    assert out['OTHER'] is None
    db = out['AnvilbookExportDB']
    assert db['version'] == 1
    recipe = db['characters']['Thordak - Classic Beta PvP']['professions']['Blacksmithing']['recipes'][3490]
    assert recipe['name'] == 'Deadly "Bronze" Poniard'
    assert recipe['reagents'] == {1: {'id': 2841, 'count': 4}, 2: {'id': 3466, 'count': 1}}


def test_scalars():
    out = parse_savedvariables(
        b'A = -5\nB = 1.25\nC = 1e3\nD = true\nE = false\nF = "a\\nb\\065"\nG = { "x", "y", }\n'
        + 'H = "Tähti"\n'.encode())
    assert out == {'A': -5, 'B': 1.25, 'C': 1000.0, 'D': True, 'E': False, 'F': 'a\nbA',
                   'G': {1: 'x', 2: 'y'}, 'H': 'Tähti'}


@pytest.mark.parametrize('text', [b'A = { ["x"] = 1,', b'A = "open', b'A = @', b'= 1'])
def test_bad_input_raises(text):
    with pytest.raises(LuaParseError):
        parse_savedvariables(text)

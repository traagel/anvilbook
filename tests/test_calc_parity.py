"""The addon carries a Lua port of the calculator; it must give the same answers as the app."""

import math
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

import pytest

from anvilbook.bridge import to_lua
from anvilbook.craft import Calculator, CraftSettings
from anvilbook.disenchant import DEFAULT_TABLE, GREATER_MAGIC, STRANGE_DUST, effective_table
from anvilbook.luatable import parse_savedvariables
from anvilbook.plan import for_budget, plan_for
from anvilbook.recipes import GameExport, merge

ADDON = Path(__file__).parent.parent / 'src/anvilbook/addon/AnvilbookExport'
RUNNER = Path(__file__).parent / 'calc_parity.lua'

pytestmark = pytest.mark.skipif(not shutil.which('luajit'), reason='needs luajit')


def recipe(category, skill, reagents, amount=(1, 1)):
    return {'amount': list(amount), 'requiredSkill': skill, 'category': category,
            'reagents': [{'itemId': i, 'amount': n} for i, n in reagents]}


ITEMS = {
    3490: {'name': 'Deadly Bronze Poniard', 'requiredLevel': 20, 'quality': 'Uncommon', 'itemLevel': 19,
           'class': 'Weapon', 'sellPrice': 1500,
           'createdBy': [recipe('Blacksmithing', 100, [(2841, 4), (3466, 1)])]},
    2770: {'name': 'Copper Ore'},
    2771: {'name': 'Tin Ore'},
    3466: {'name': 'Strong Flux', 'vendorPrice': 2000},
    2840: {'name': 'Copper Bar', 'createdBy': [recipe('Mining', 1, [(2770, 1)])]},
    3576: {'name': 'Tin Bar', 'createdBy': [recipe('Mining', 65, [(2771, 1)])]},
    2841: {'name': 'Bronze Bar', 'createdBy': [recipe('Mining', 65, [(2840, 1), (3576, 1)], (2, 2))]},
    2851: {'name': 'Copper Chain Belt', 'requiredLevel': 5, 'quality': 'Uncommon', 'itemLevel': 8,
           'class': 'Armor', 'createdBy': [recipe('Blacksmithing', 35, [(2840, 6)]),
                                           recipe('Blacksmithing', 40, [(2841, 2)])]},
    2852: {'name': 'Copper Bracers', 'createdBy': [recipe('Blacksmithing', 1, [(2840, 2)], (1, 3))]},
    STRANGE_DUST: {'name': 'Strange Dust'},
    GREATER_MAGIC: {'name': 'Greater Magic Essence'},
}
PRICES = {2770: 57, 2771: 200, 2840: 73, 3576: 248, 2841: 220, 3490: 17500, 3466: 2500, 2851: 2400,
          2852: 300, STRANGE_DUST: 90, GREATER_MAGIC: 1100}


def prices(available: int = 10, **over: int) -> dict[int, dict]:
    merged = {**PRICES, **{int(k[1:]): v for k, v in over.items()}}
    return {i: {'min_price': p, 'available': available, 'day_high': p * 2} for i, p in merged.items()}


def settings(**over) -> CraftSettings:
    base = {'skills': {'Blacksmithing': 120, 'Mining': 99}, 'skill_overrides': {3490: 100},
            'max_use_level': 20, 'min_listed': 3, 'cast_seconds': 3, 'ah_cut': 0.05}
    out = CraftSettings.from_dict({**base, **{k: v for k, v in over.items() if k in base}})
    out.disenchanter = over.get('disenchanter', False)
    out.disenchant_table = DEFAULT_TABLE
    return out


PLANS = [
    {'item_id': 3490, 'count': 3, 'owned': {2841: 5}},
    {'item_id': 3490, 'budget': 50000, 'owned': {}},
    {'item_id': 3490, 'budget': 10, 'owned': {}},
    {'item_id': 2841, 'count': 7, 'owned': {2840: 2}},
    {'item_id': 2852, 'count': 4, 'owned': {}},
]

EXPORT = GameExport('Thordak - Realm', 0, {'Mining': {'rank': 120, 'recipes': {
    2841: {'name': 'Bronze Bar', 'minMade': 2, 'maxMade': 2, 'difficulty': 'easy',
           'reagents': {1: {'id': 2840, 'count': 1, 'name': 'Copper Bar'},
                        2: {'id': 3576, 'count': 1, 'name': 'Tin Bar'}}}}}})

CASES = {
    'plain': (ITEMS, prices(), {}, settings()),
    # A belt worth less than its dust makes the disenchant exit win.
    'disenchanter': (ITEMS, prices(i2851=50, i10938=400, i10940=400), {3466: 1800},
                     settings(disenchanter=True, max_use_level=30)),
    'thin market': (ITEMS, prices(available=2), {}, settings(min_listed=1, ah_cut=0.15, cast_seconds=2.5)),
    'known recipes': (merge(ITEMS, EXPORT), prices(), {}, settings()),
}


def disenchant(quality, level, kind, *mats):
    return {'item': {'quality': quality, 'itemLevel': level, 'kind': kind},
            'mats': [{'id': i, 'count': n} for i, n in mats]}


# Two buckets cross the sample minimum and one does not, so both paths of effective_table run.
RECORDS = ([disenchant(2, 19, 'Weapon', (GREATER_MAGIC, 1))] * 2 + [disenchant(2, 18, 'Weapon', (STRANGE_DUST, 3))]
           + [disenchant(2, 8, 'Armor', (STRANGE_DUST, 2), (10938, 1))] * 3
           + [disenchant(3, 22, 'Armor', (10978, 1))] + [disenchant(2, 40, 'Armor', (STRANGE_DUST, 1))])
MIN_SAMPLES = 3


def python_side(items, price_rows, vendor, craft_settings) -> dict:
    calc = Calculator(items, price_rows, vendor, craft_settings)
    plans = [asdict(for_budget(calc, p['item_id'], p['budget'], p['owned']) if 'budget' in p
                    else plan_for(calc, p['item_id'], p['count'], p['owned'])) for p in PLANS]
    return {'rows': [asdict(r) for r in calc.rows()], 'plans': plans,
            'effective': effective_table(craft_settings.disenchant_table, RECORDS, MIN_SAMPLES)}


def as_lists(value):
    """Lua arrays read back as dicts keyed 1..n."""
    if isinstance(value, dict):
        if value and set(value) == set(range(1, len(value) + 1)):
            return [as_lists(value[k]) for k in range(1, len(value) + 1)]
        return {k: as_lists(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_lists(v) for v in value]
    return value


def lua_side(tmp_path, items, price_rows, vendor, craft_settings) -> dict:
    case = tmp_path / 'case.lua'
    case.write_text('Case = ' + to_lua({'items': items, 'prices': price_rows, 'vendor': vendor,
                                         'settings': asdict(craft_settings), 'plans': PLANS,
                                         'records': RECORDS, 'min_samples': MIN_SAMPLES}))
    out = subprocess.run(['luajit', str(RUNNER), str(ADDON / 'Calc.lua'), str(case)],
                         capture_output=True, check=True)
    result = as_lists(parse_savedvariables(out.stdout)['Result'])
    # An empty Lua table cannot tell a list from a dict.
    for plan in result['plans']:
        for key in ('purchases', 'steps'):
            plan[key] = plan[key] or []
        for key in ('leftovers', 'owned_used'):
            plan[key] = plan[key] or {}
    return result


def same(a, b, where='') -> None:
    if isinstance(a, float) or isinstance(b, float):
        assert math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-6), f'{where}: {a} != {b}'
    elif isinstance(a, dict):
        assert set(a) == set(b), f'{where}: keys {sorted(a)} != {sorted(b)}'
        for k in a:
            same(a[k], b[k], f'{where}.{k}')
    elif isinstance(a, list):
        assert len(a) == len(b), f'{where}: {len(a)} items != {len(b)}'
        for i, (x, y) in enumerate(zip(a, b)):
            same(x, y, f'{where}[{i}]')
    else:
        assert a == b, f'{where}: {a!r} != {b!r}'


def without_none(value):
    if isinstance(value, dict):
        return {k: without_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [without_none(v) for v in value]
    return value


@pytest.mark.parametrize('name', CASES)
def test_lua_calculator_matches_python(tmp_path, name):
    items, price_rows, vendor, craft_settings = CASES[name]
    expected = python_side(items, price_rows, vendor, craft_settings)
    assert expected['rows'], 'the case must produce craft rows to compare'
    if craft_settings.disenchanter:
        assert any(r['exit'] == 'disenchant' for r in expected['rows'])
    # Lua drops nil fields, so a None in Python reads back as a missing key.
    same(as_lists(without_none(expected)), lua_side(tmp_path, items, price_rows, vendor, craft_settings), name)

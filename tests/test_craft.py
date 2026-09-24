import pytest

from anvilbook.craft import Calculator, CraftSettings


def recipe(category, skill, reagents, amount=(1, 1)):
    return {'amount': list(amount), 'requiredSkill': skill, 'category': category,
            'reagents': [{'itemId': i, 'amount': n} for i, n in reagents]}


ITEMS = {
    2770: {'name': 'Copper Ore'},
    2771: {'name': 'Tin Ore'},
    2840: {'name': 'Copper Bar', 'createdBy': [recipe('Mining', 1, [(2770, 1)])]},
    3576: {'name': 'Tin Bar', 'createdBy': [recipe('Mining', 65, [(2771, 1)])]},
    2841: {'name': 'Bronze Bar', 'createdBy': [recipe('Mining', 65, [(2840, 1), (3576, 1)], amount=(2, 2))]},
}
PRICES = {i: {'min_price': p, 'available': 100}
          for i, p in {2770: 57, 2771: 200, 2840: 73, 3576: 248, 2841: 220}.items()}


def settings(**kw):
    base = dict(skills={'Mining': 99}, skill_overrides={}, max_use_level=20, min_listed=3,
                cast_seconds=3, ah_cut=0.05)
    return CraftSettings(**{**base, **kw})


def row(rows, item_id):
    return next((r for r in rows if r.item_id == item_id), None)


def test_bronze_pareto_paths():
    calc = Calculator(ITEMS, PRICES, {}, settings())
    opts = calc.recipe_options(ITEMS[2841]['createdBy'][0], 0, 2841)
    assert [(p, c) for p, c, _, _ in opts] == [(257, 3), (273, 2), (321, 1)]


def test_bronze_row_best_per_cast_and_cheapest():
    r = row(Calculator(ITEMS, PRICES, {}, settings()).rows(), 2841)
    assert r is not None
    assert r.revenue == pytest.approx(418)
    assert (r.cost, r.casts, r.path) == (321, 1, 'craft')
    assert r.per_cast == pytest.approx(97)
    assert r.per_hour == pytest.approx(97 * 1200)
    assert r.cheapest_profit == pytest.approx(161)
    assert r.cheapest_casts == 3
    assert r.cheapest_path == 'craft[Copper Bar=craft, Tin Bar=craft]'


def test_skill_cap_blocks_recipes():
    calc = Calculator(ITEMS, PRICES, {}, settings(skills={'Mining': 50}))
    rows = calc.rows()
    assert row(rows, 2841) is None and row(rows, 3576) is None
    assert row(rows, 2840) is not None
    assert [(p, c, path) for p, c, path, _ in calc.options(3576)] == [(248, 0, 'buy')]


def test_forever_override_unlocks_recipe():
    rows = Calculator(ITEMS, PRICES, {}, settings(skills={'Mining': 50}, skill_overrides={2841: 50})).rows()
    assert row(rows, 2841) is not None


def test_profession_without_cap_is_not_craftable():
    assert Calculator(ITEMS, PRICES, {}, settings(skills={})).rows() == []


def test_filters():
    high_level = {**ITEMS, 2841: {**ITEMS[2841], 'requiredLevel': 25}}
    assert row(Calculator(high_level, PRICES, {}, settings()).rows(), 2841) is None
    assert Calculator(ITEMS, PRICES, {}, settings(min_listed=200)).rows() == []


def test_vendor_price_beats_ah():
    items = {**ITEMS, 2771: {'name': 'Tin Ore', 'vendorPrice': 150}}
    price = lambda calc: [(p, c, path) for p, c, path, _ in calc.options(2771)]
    assert price(Calculator(items, PRICES, {}, settings())) == [(150, 0, 'buy')]
    assert price(Calculator(ITEMS, PRICES, {2771: 120}, settings())) == [(120, 0, 'buy')]


def test_known_game_recipe_ignores_overrides_and_keeps_difficulty():
    game = {**recipe('Mining', 0, [(2840, 1), (3576, 1)], amount=(2, 2)), 'known': True, 'difficulty': 'easy'}
    items = {**ITEMS, 2841: {'name': 'Bronze Bar', 'createdBy': [game]}}
    r = row(Calculator(items, PRICES, {}, settings(skill_overrides={2841: 500})).rows(), 2841)
    assert r is not None
    assert (r.skill, r.difficulty) == (0, 'easy')
    db = row(Calculator(ITEMS, PRICES, {}, settings()).rows(), 2841)
    assert db is not None and db.difficulty is None


DE_TABLE = [{'quality': 'Uncommon', 'maxLevel': 25, 'weapon': [[10940, 1.0, 4]], 'armor': [[10940, 1.0, 1]]}]
DAGGER = {3490: {'name': 'Bronze Dagger', 'quality': 'Uncommon', 'itemLevel': 20, 'class': 'Weapon',
                 'createdBy': [recipe('Mining', 1, [(2841, 1)])]}}
DE_PRICES = {**PRICES, 3490: {'min_price': 400, 'available': 100}, 10940: {'min_price': 200, 'available': 100}}


def test_disenchant_beats_selling():
    items = {**ITEMS, **DAGGER}
    row_sell = row(Calculator(items, DE_PRICES, {}, settings()).rows(), 3490)
    assert row_sell is not None
    assert (row_sell.exit, row_sell.de_value) == ('sell', 0)
    assert row_sell.revenue == pytest.approx(400 * 0.95)

    with_de = settings(disenchanter=True, disenchant_table=DE_TABLE)
    row_de = row(Calculator(items, DE_PRICES, {}, with_de).rows(), 3490)
    assert row_de is not None
    # 1.0 chance * 4 dust * 200c, less the auction cut, beats the 400c sale.
    assert row_de.de_value == pytest.approx(800 * 0.95)
    assert row_de.exit == 'disenchant'
    assert row_de.revenue == pytest.approx(800 * 0.95)


def test_disenchant_does_not_apply_to_materials():
    with_de = settings(disenchanter=True, disenchant_table=DE_TABLE)
    bronze = row(Calculator(ITEMS, DE_PRICES, {}, with_de).rows(), 2841)
    assert bronze is not None and bronze.exit == 'sell' and bronze.de_value == 0


def test_self_referencing_recipe_terminates():
    items = {1: {'name': 'Loop', 'createdBy': [recipe('Mining', 1, [(1, 1)])]}}
    prices = {1: {'min_price': 100, 'available': 10}}
    assert Calculator(items, prices, {}, settings()).rows() == []


def test_settings_from_dict_converts_types():
    s = CraftSettings.from_dict({'skills': {'Mining': 99}, 'skill_overrides': {'3490': 100},
                                 'max_use_level': 20, 'min_listed': 3, 'cast_seconds': 3, 'ah_cut': 0.05,
                                 'savedvariables_path': 'x', 'realm': None})
    assert s.skill_overrides == {3490: 100}
    with pytest.raises(ValueError):
        CraftSettings.from_dict({'skills': {}, 'skill_overrides': {}, 'max_use_level': 'x',
                                 'min_listed': 3, 'cast_seconds': 3, 'ah_cut': 0.05})

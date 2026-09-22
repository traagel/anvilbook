import pytest

from anvilbook.disenchant import DEFAULT_TABLE, expected_value, yields

TABLE = [
    {'quality': 'Uncommon', 'maxLevel': 15,
     'armor': [[10940, 0.8, 2], [10938, 0.2, 1]],
     'weapon': [[10940, 0.2, 2], [10938, 0.8, 1]]},
    {'quality': 'Uncommon', 'maxLevel': 25,
     'armor': [[10940, 0.75, 3], [10939, 0.2, 1], [10978, 0.05, 1]],
     'weapon': [[10940, 0.2, 3], [10939, 0.75, 1], [10978, 0.05, 1]]},
]
PRICES = {10940: 100, 10938: 500, 10939: 900, 10978: 5000}


def test_yields_by_level_and_kind():
    assert yields(TABLE, 'Uncommon', 12, 'Armor') == [(10940, 0.8, 2), (10938, 0.2, 1)]
    assert yields(TABLE, 'Uncommon', 20, 'Weapon') == [(10940, 0.2, 3), (10939, 0.75, 1), (10978, 0.05, 1)]


@pytest.mark.parametrize('quality, level, kind', [
    ('Common', 12, 'Armor'),        # white items give nothing
    ('Uncommon', 40, 'Armor'),      # above the table
    ('Uncommon', 12, 'Trade Goods'),  # not equipment
])
def test_no_yields(quality, level, kind):
    assert yields(TABLE, quality, level, kind) == []


def test_expected_value_uses_chance_quantity_and_ah_cut():
    # 0.2 * 2 * 100 + 0.8 * 1 * 500 = 440 copper, less the 5% auction cut.
    assert expected_value(TABLE, PRICES, 'Uncommon', 12, 'Weapon', 0.05) == pytest.approx(440 * 0.95)


def test_expected_value_ignores_materials_without_a_price():
    assert expected_value(TABLE, {10938: 500}, 'Uncommon', 12, 'Weapon', 0.0) == pytest.approx(400)
    assert expected_value(TABLE, {}, 'Uncommon', 12, 'Weapon', 0.0) == 0


def test_default_table_covers_beta_levels():
    for level in (1, 15, 16, 25):
        assert yields(DEFAULT_TABLE, 'Uncommon', level, 'Weapon'), f'no yields at item level {level}'

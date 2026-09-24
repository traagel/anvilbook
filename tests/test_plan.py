import pytest

from anvilbook.craft import Calculator, CraftSettings
from anvilbook.plan import for_budget, plan_for

ITEMS = {
    2770: {'name': 'Copper Ore'},
    2771: {'name': 'Tin Ore'},
    2840: {'name': 'Copper Bar', 'createdBy': [{'amount': [1, 1], 'requiredSkill': 1, 'category': 'Mining',
                                                'reagents': [{'itemId': 2770, 'amount': 1}]}]},
    3576: {'name': 'Tin Bar', 'createdBy': [{'amount': [1, 1], 'requiredSkill': 65, 'category': 'Mining',
                                             'reagents': [{'itemId': 2771, 'amount': 1}]}]},
    2841: {'name': 'Bronze Bar', 'createdBy': [{'amount': [2, 2], 'requiredSkill': 65, 'category': 'Mining',
                                                'reagents': [{'itemId': 2840, 'amount': 1},
                                                             {'itemId': 3576, 'amount': 1}]}]},
}
PRICES = {i: {'min_price': p, 'available': 100}
          for i, p in {2770: 57, 2771: 200, 2840: 73, 3576: 248, 2841: 220}.items()}


def calculator(**kw):
    base = dict(skills={'Mining': 99}, skill_overrides={}, max_use_level=20, min_listed=3,
                cast_seconds=3, ah_cut=0.05)
    return Calculator(ITEMS, PRICES, {}, CraftSettings(**{**base, **kw}))


def test_plan_buys_ore_and_counts_every_cast():
    plan = plan_for(calculator(), 2841, 3)
    assert plan.count == 3
    assert {p.item_id: p.quantity for p in plan.purchases} == {2770: 2, 2771: 2}
    assert plan.cost == 2 * 57 + 2 * 200
    assert {s.item_id: s.casts for s in plan.steps} == {2840: 2, 3576: 2, 2841: 2}
    assert plan.casts == 6
    assert plan.leftovers == {2841: 1}


def test_plan_uses_what_you_already_have():
    plan = plan_for(calculator(), 2841, 3, owned={2840: 2, 2770: 99})
    assert {p.item_id: p.quantity for p in plan.purchases} == {2771: 2}
    assert {s.item_id: s.casts for s in plan.steps} == {3576: 2, 2841: 2}


def test_plan_crafts_the_item_even_when_buying_it_is_cheaper():
    dear = {**PRICES, **{i: {'min_price': 5000, 'available': 100} for i in (2770, 2771, 2840, 3576)}}
    calc = Calculator(ITEMS, dear, {}, CraftSettings(skills={'Mining': 99}, skill_overrides={}, max_use_level=20,
                                                     min_listed=3, cast_seconds=3, ah_cut=0.05))
    plan = plan_for(calc, 2841, 2)
    assert {p.item_id: p.quantity for p in plan.purchases} == {2840: 1, 3576: 1}
    assert [s.item_id for s in plan.steps] == [2841]


def test_plan_buys_an_item_it_cannot_craft():
    calc = calculator(skills={})
    plan = plan_for(calc, 2841, 2)
    assert {p.item_id: p.quantity for p in plan.purchases} == {2841: 2}
    assert plan.steps == []


def test_budget_picks_the_largest_affordable_count():
    plan = for_budget(calculator(), 2841, budget=600)
    assert plan.count == 4  # 2 smelts make 4 bars for 514 copper; a third smelt costs more than the budget
    assert plan.cost == 514

    nothing = for_budget(calculator(), 2841, budget=100)
    assert nothing.count == 0 and nothing.purchases == [] and nothing.short_by == 157


def test_plan_reports_revenue_and_profit():
    plan = plan_for(calculator(), 2841, 4)
    assert plan.revenue == pytest.approx(4 * 220 * 0.95)
    assert plan.profit == pytest.approx(plan.revenue - plan.cost)

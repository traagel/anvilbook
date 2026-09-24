"""Turn a craft into a shopping list: what to buy, what to smelt, what it costs."""

from dataclasses import dataclass, field
from math import ceil

from .craft import Buy, Calculator, pareto

MAX_COUNT = 500


@dataclass
class Purchase:
    item_id: int
    name: str
    quantity: int
    unit_price: int
    total: int


@dataclass
class Step:
    item_id: int
    name: str
    casts: int
    makes: int


@dataclass
class Plan:
    item_id: int
    name: str
    count: int
    cost: int
    revenue: float
    profit: float
    casts: int
    purchases: list[Purchase] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    leftovers: dict[int, int] = field(default_factory=dict)
    owned_used: dict[int, int] = field(default_factory=dict)
    short_by: int = 0


def _gather(node, units: int, owned: dict[int, int], buys: dict[int, int], casts: dict[int, int],
            makes: dict[int, int], leftovers: dict[int, int], used_owned: dict[int, int],
            spares: dict[int, int]) -> None:
    have = owned.get(node.item_id, 0)
    used = min(have, units)
    owned[node.item_id] = have - used
    if used and used > spares.get(node.item_id, 0):
        used_owned[node.item_id] = used_owned.get(node.item_id, 0) + used - spares.get(node.item_id, 0)
    need = units - used
    if need <= 0:
        return
    if isinstance(node, Buy):
        buys[node.item_id] = buys.get(node.item_id, 0) + need
        return
    # A craft makes whole batches, so the last one can leave spares.
    per_cast = min(node.recipe['amount'])
    runs = ceil(need / per_cast)
    casts[node.item_id] = casts.get(node.item_id, 0) + runs
    makes[node.item_id] = per_cast
    spare = runs * per_cast - need
    if spare:
        leftovers[node.item_id] = leftovers.get(node.item_id, 0) + spare
        owned[node.item_id] = owned.get(node.item_id, 0) + spare
        spares[node.item_id] = spares.get(node.item_id, 0) + spare
    for child, reagent in zip(node.children, node.recipe['reagents']):
        _gather(child, runs * reagent['amount'], owned, buys, casts, makes, leftovers, used_owned, spares)


def plan_for(calc: Calculator, item_id: int, count: int, owned: dict[int, int] | None = None) -> Plan:
    item = calc.items.get(item_id) or {}
    name = item.get('name') or str(item_id)
    # The plan always crafts the item asked for, even when buying it outright is cheaper.
    craftable = [option for recipe in item.get('createdBy') or [] if calc.can_craft(item_id, recipe)
                 for option in calc.recipe_options(recipe, 0, item_id)]
    options = pareto(craftable) or calc.options(item_id)
    if not options or count <= 0:
        return Plan(item_id, name, 0, 0, 0, 0, 0)

    buys: dict[int, int] = {}
    casts: dict[int, int] = {}
    makes: dict[int, int] = {}
    leftovers: dict[int, int] = {}
    used_owned: dict[int, int] = {}
    _gather(options[0][3], count, dict(owned or {}), buys, casts, makes, leftovers, used_owned, {})

    purchases = []
    for bought_id, quantity in sorted(buys.items(), key=lambda kv: -kv[1]):
        unit = calc.buy_price(bought_id) or 0
        purchases.append(Purchase(bought_id, (calc.items.get(bought_id) or {}).get('name') or str(bought_id),
                                  quantity, unit, unit * quantity))
    steps = [Step(step_id, (calc.items.get(step_id) or {}).get('name') or str(step_id), runs, makes[step_id])
             for step_id, runs in casts.items()]
    cost = sum(p.total for p in purchases)
    sale = (calc.prices.get(item_id) or {}).get('min_price') or 0
    revenue = max(sale * (1 - calc.s.ah_cut), item.get('sellPrice') or 0, calc.disenchant_value(item)) * count
    return Plan(item_id, name, count, cost, revenue, revenue - cost, sum(casts.values()),
                purchases, steps, leftovers, used_owned)


def for_budget(calc: Calculator, item_id: int, budget: int, owned: dict[int, int] | None = None) -> Plan:
    """The largest batch that fits the budget. Cost per item is not linear: batches leave spares."""
    best = None
    low, high = 1, MAX_COUNT
    while low <= high:
        middle = (low + high) // 2
        plan = plan_for(calc, item_id, middle, owned)
        if plan.cost <= budget:
            best = plan
            low = middle + 1
        else:
            high = middle - 1
    if best:
        return best
    one = plan_for(calc, item_id, 1, owned)
    one.count, one.short_by = 0, max(0, one.cost - budget)
    one.purchases, one.steps, one.leftovers = [], [], {}
    one.revenue = one.profit = 0
    return one

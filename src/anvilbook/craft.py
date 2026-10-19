from dataclasses import dataclass, field
from itertools import product
from typing import Any

from .disenchant import expected_value

# Deep enough for ore -> bar -> alloy -> item; also stops recipe cycles.
MAX_DEPTH = 3
# Calc.lua writes the same text.
NO_PRICE = 'a reagent has no price'

@dataclass(frozen=True)
class Buy:
    item_id: int


@dataclass(frozen=True)
class Craft:
    item_id: int
    recipe: dict
    children: tuple


# (price, casts, path text, how to get it)
Option = tuple[float, float, str, Buy | Craft]


@dataclass
class CraftSettings:
    skills: dict[str, int]
    skill_overrides: dict[int, int]
    max_use_level: int
    min_listed: int
    cast_seconds: float
    ah_cut: float
    disenchanter: bool = False
    disenchant_table: list[dict] = field(default_factory=list)

    @classmethod
    def from_dict(cls, s: dict) -> 'CraftSettings':
        return cls(
            skills={str(k): int(v) for k, v in s['skills'].items()},
            skill_overrides={int(k): int(v) for k, v in s['skill_overrides'].items()},
            max_use_level=int(s['max_use_level']),
            min_listed=int(s['min_listed']),
            cast_seconds=float(s['cast_seconds']),
            ah_cut=float(s['ah_cut']),
            disenchant_table=list(s.get('disenchant_table') or []),
        )


@dataclass
class CraftRow:
    item_id: int
    name: str
    profession: str
    skill: int
    cost: float | None
    revenue: float
    profit: float | None
    casts: float | None
    per_cast: float | None
    per_hour: float | None
    listed: int
    path: str
    cheapest_profit: float | None
    cheapest_casts: float | None
    cheapest_path: str
    difficulty: str | None = None
    de_value: float = 0
    exit: str = 'sell'
    learned: bool = True
    estimated: bool = False
    learned_from: str | None = None
    pattern: int | None = None


def color(rank: int, recipe: dict) -> str | None:
    """The skill-up color from Forever's thresholds; green starts halfway from yellow to grey."""
    if 'yellow' not in recipe:
        return None
    if rank < recipe['yellow']:
        return 'optimal'
    if rank < (recipe['yellow'] + recipe['grey']) / 2:
        return 'medium'
    return 'easy' if rank < recipe['grey'] else 'trivial'


def pareto(opts: list[Option]) -> list[Option]:
    front: list[Option] = []
    for o in sorted(opts, key=lambda o: (o[0], o[1])):
        if not front or o[1] < front[-1][1]:
            front.append(o)
    return front


class Calculator:
    def __init__(self, items: dict[int, dict], prices: dict[int, dict], vendor: dict[int, int],
                 settings: CraftSettings):
        self.items = items
        self.prices = prices
        self.vendor = vendor
        self.s = settings
        self._memo: dict[tuple[int, int], list[Option]] = {}

    def skill(self, item_id: int, recipe: dict) -> int:
        if recipe.get('known'):
            return 0
        return self.s.skill_overrides.get(item_id, recipe.get('requiredSkill') or 0)

    def can_craft(self, item_id: int, recipe: dict) -> bool:
        cap = self.s.skills.get(recipe.get('category') or '')
        return cap is not None and self.skill(item_id, recipe) <= cap

    def buy_price(self, item_id: int) -> int | None:
        ah = (self.prices.get(item_id) or {}).get('min_price')
        vendor = self.vendor.get(item_id) or (self.items.get(item_id) or {}).get('vendorPrice')
        found = [p for p in (ah, vendor) if p]
        return min(found) if found else None

    def disenchant_value(self, item: dict) -> float:
        if not self.s.disenchanter:
            return 0
        prices = {i: p['min_price'] for i, p in self.prices.items()}
        return expected_value(self.s.disenchant_table, prices, item.get('quality'),
                              item.get('itemLevel') or 0, item.get('class'), self.s.ah_cut)

    def options(self, item_id: int, depth: int = 0) -> list[Option]:
        key = (item_id, depth)
        if key not in self._memo:
            opts: list[Option] = []
            price = self.buy_price(item_id)
            if price:
                opts.append((price, 0, 'buy', Buy(item_id)))
            if depth < MAX_DEPTH:
                for recipe in (self.items.get(item_id) or {}).get('createdBy') or []:
                    # A step must be something the character can make today.
                    if self.can_craft(item_id, recipe) and not recipe.get('unlearned'):
                        n = sum(recipe['amount']) / 2
                        opts += [(p / n, c / n, path, node)
                                 for p, c, path, node in self.recipe_options(recipe, depth + 1, item_id)]
            self._memo[key] = pareto(opts)
        return self._memo[key]

    def recipe_options(self, recipe: dict, depth: int, item_id: int = 0) -> list[Option]:
        per_reagent = []
        for r in recipe['reagents']:
            name = (self.items.get(r['itemId']) or {}).get('name') or str(r['itemId'])
            per_reagent.append([(p * r['amount'], c * r['amount'], name, path, node)
                                for p, c, path, node in self.options(r['itemId'], depth)])
        out = []
        for combo in product(*per_reagent):
            crafted = [f'{name}={path}' for _, _, name, path, _ in combo if path != 'buy']
            out.append((sum(o[0] for o in combo), 1 + sum(o[1] for o in combo),
                        'craft' + (f"[{', '.join(crafted)}]" if crafted else ''),
                        Craft(item_id, recipe, tuple(o[4] for o in combo))))
        return pareto(out)

    def rows(self, show_all: bool = False) -> list[CraftRow]:
        """Profitable crafts. show_all also keeps losses, unpriced outputs and thin markets, because
        one listing far below the usual price can make a good craft look like a loss."""
        out = []
        for item_id in (self.items if show_all else self.prices):
            item, price = self.items.get(item_id), self.prices.get(item_id)
            if not item or (item.get('requiredLevel') or 0) > self.s.max_use_level:
                continue
            if not show_all and price['available'] < self.s.min_listed:
                continue
            for recipe in item.get('createdBy') or []:
                if not self.can_craft(item_id, recipe):
                    continue
                n = sum(recipe['amount']) / 2
                sale = max((price or {}).get('min_price', 0) * (1 - self.s.ah_cut), item.get('sellPrice') or 0)
                de_value = self.disenchant_value(item)
                revenue = max(sale, de_value) * n
                opts = self.recipe_options(recipe, 0, item_id)
                if not opts and not show_all:
                    continue
                listed = price['available'] if price else 0
                difficulty = recipe.get('difficulty')
                if not difficulty and recipe.get('unlearned'):
                    difficulty = color(self.s.skills.get(recipe.get('category') or '', 0), recipe)
                common: dict[str, Any] = dict(item_id=item_id, name=item['name'], profession=recipe.get('category'),
                              skill=self.skill(item_id, recipe), revenue=revenue, listed=listed,
                              difficulty=difficulty, de_value=de_value,
                              exit='disenchant' if de_value > sale else 'sell', learned=not recipe.get('unlearned'),
                              estimated=bool(recipe.get('estimated')), learned_from=recipe.get('source'),
                              pattern=recipe.get('pattern'))
                if not opts:
                    # A reagent with no AH or vendor price leaves the cost unknown.
                    out.append(CraftRow(cost=None, profit=None, casts=None, per_cast=None, per_hour=None,
                                        path=NO_PRICE, cheapest_profit=None, cheapest_casts=None,
                                        cheapest_path=NO_PRICE, **common))
                    continue
                cost, casts, path, _ = max(opts, key=lambda o: (revenue - o[0]) / o[1])
                cheap_cost, cheap_casts, cheap_path, _ = opts[0]
                if revenue - cost <= 0 and not show_all:
                    continue
                per_cast = (revenue - cost) / casts
                out.append(CraftRow(cost=cost, profit=revenue - cost, casts=casts, per_cast=per_cast,
                                    per_hour=per_cast * 3600 / self.s.cast_seconds, path=path,
                                    cheapest_profit=revenue - cheap_cost, cheapest_casts=cheap_casts,
                                    cheapest_path=cheap_path, **common))
        # The item id breaks ties, so the Lua port in the addon sorts the same way.
        out.sort(key=lambda r: (r.per_hour is None, -(r.per_hour or 0), r.item_id))
        return out

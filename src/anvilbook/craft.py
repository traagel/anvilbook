from dataclasses import dataclass, field
from itertools import product

from .disenchant import expected_value

# Deep enough for ore -> bar -> alloy -> item; also stops recipe cycles.
MAX_DEPTH = 3

Option = tuple[float, float, str]


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
    cost: float
    revenue: float
    profit: float
    casts: float
    per_cast: float
    per_hour: float
    listed: int
    path: str
    cheapest_profit: float
    cheapest_casts: float
    cheapest_path: str
    difficulty: str | None = None
    de_value: float = 0
    exit: str = 'sell'


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
                opts.append((price, 0, 'buy'))
            if depth < MAX_DEPTH:
                for recipe in (self.items.get(item_id) or {}).get('createdBy') or []:
                    if self.can_craft(item_id, recipe):
                        n = sum(recipe['amount']) / 2
                        opts += [(p / n, c / n, path) for p, c, path in self.recipe_options(recipe, depth + 1)]
            self._memo[key] = pareto(opts)
        return self._memo[key]

    def recipe_options(self, recipe: dict, depth: int) -> list[Option]:
        per_reagent = []
        for r in recipe['reagents']:
            name = (self.items.get(r['itemId']) or {}).get('name', str(r['itemId']))
            per_reagent.append([(p * r['amount'], c * r['amount'], name, path)
                                for p, c, path in self.options(r['itemId'], depth)])
        out = []
        for combo in product(*per_reagent):
            crafted = [f'{name}={path}' for _, _, name, path in combo if path != 'buy']
            out.append((sum(o[0] for o in combo), 1 + sum(o[1] for o in combo),
                        'craft' + (f"[{', '.join(crafted)}]" if crafted else '')))
        return pareto(out)

    def rows(self) -> list[CraftRow]:
        out = []
        for item_id, price in self.prices.items():
            item = self.items.get(item_id)
            if (not item or (item.get('requiredLevel') or 0) > self.s.max_use_level
                    or price['available'] < self.s.min_listed):
                continue
            for recipe in item.get('createdBy') or []:
                if not self.can_craft(item_id, recipe):
                    continue
                n = sum(recipe['amount']) / 2
                sale = max(price['min_price'] * (1 - self.s.ah_cut), item.get('sellPrice') or 0)
                de_value = self.disenchant_value(item)
                revenue = max(sale, de_value) * n
                opts = self.recipe_options(recipe, 0)
                if not opts:
                    continue
                cost, casts, path = max(opts, key=lambda o: (revenue - o[0]) / o[1])
                cheap_cost, cheap_casts, cheap_path = opts[0]
                if revenue - cost <= 0:
                    continue
                per_cast = (revenue - cost) / casts
                out.append(CraftRow(
                    item_id, item['name'], recipe.get('category'), self.skill(item_id, recipe),
                    cost, revenue, revenue - cost, casts, per_cast, per_cast * 3600 / self.s.cast_seconds,
                    price['available'], path, revenue - cheap_cost, cheap_casts, cheap_path,
                    recipe.get('difficulty'), de_value, 'disenchant' if de_value > sale else 'sell'))
        out.sort(key=lambda r: -r.per_hour)
        return out

"""Expected value of disenchanting an item.

The yields are estimates: Classic's real table is not published in full, and
Forever may differ. The table lives in the settings so it can be corrected, and
measured results from the game replace it once there are enough samples.
"""

KINDS = {'Armor': 'armor', 'Weapon': 'weapon'}

STRANGE_DUST, LESSER_MAGIC, GREATER_MAGIC = 10940, 10938, 10939
SOUL_DUST, LESSER_ASTRAL, GLIMMERING_SHARD = 11083, 10998, 10978

DEFAULT_TABLE = [
    {'quality': 'Uncommon', 'maxLevel': 15,
     'armor': [[STRANGE_DUST, 0.8, 1.5], [LESSER_MAGIC, 0.2, 1.5]],
     'weapon': [[STRANGE_DUST, 0.2, 1.5], [LESSER_MAGIC, 0.8, 1.5]]},
    {'quality': 'Uncommon', 'maxLevel': 20,
     'armor': [[STRANGE_DUST, 0.75, 2], [GREATER_MAGIC, 0.2, 1], [GLIMMERING_SHARD, 0.05, 1]],
     'weapon': [[STRANGE_DUST, 0.2, 2], [GREATER_MAGIC, 0.75, 1], [GLIMMERING_SHARD, 0.05, 1]]},
    {'quality': 'Uncommon', 'maxLevel': 25,
     'armor': [[STRANGE_DUST, 0.75, 3], [LESSER_ASTRAL, 0.2, 1], [GLIMMERING_SHARD, 0.05, 1]],
     'weapon': [[STRANGE_DUST, 0.2, 3], [LESSER_ASTRAL, 0.75, 1], [GLIMMERING_SHARD, 0.05, 1]]},
    {'quality': 'Uncommon', 'maxLevel': 30,
     'armor': [[SOUL_DUST, 0.75, 2], [LESSER_ASTRAL, 0.2, 1], [GLIMMERING_SHARD, 0.05, 1]],
     'weapon': [[SOUL_DUST, 0.2, 2], [LESSER_ASTRAL, 0.75, 1], [GLIMMERING_SHARD, 0.05, 1]]},
    {'quality': 'Rare', 'maxLevel': 25,
     'armor': [[GLIMMERING_SHARD, 1.0, 1]],
     'weapon': [[GLIMMERING_SHARD, 1.0, 1]]},
]


def yields(table: list[dict], quality: str, item_level: int, kind: str) -> list[tuple[int, float, float]]:
    key = KINDS.get(str(kind))
    if not key:
        return []
    for row in sorted(table, key=lambda r: r['maxLevel']):
        if row.get('quality') == quality and item_level <= row['maxLevel']:
            return [(int(i), float(chance), float(qty)) for i, chance, qty in row.get(key) or []]
    return []


def expected_value(table: list[dict], prices: dict[int, int], quality: str, item_level: int, kind: str,
                   ah_cut: float) -> float:
    total = sum(chance * qty * prices[item_id]
                for item_id, chance, qty in yields(table, quality, item_level, kind) if item_id in prices)
    return total * (1 - ah_cut)

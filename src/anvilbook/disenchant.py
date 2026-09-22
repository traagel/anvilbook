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


QUALITY_NAMES = {2: 'Uncommon', 3: 'Rare', 4: 'Epic'}


def parse_records(db: dict) -> list[dict]:
    saved = db.get('disenchants') if isinstance(db, dict) else None
    if isinstance(saved, dict):
        return [saved[k] for k in sorted(saved)]
    return list(saved or [])


def _bucket(table: list[dict], quality, item_level: int, kind: str):
    name = QUALITY_NAMES.get(quality, quality)
    key = KINDS.get(str(kind))
    if not key:
        return None
    for row in sorted(table, key=lambda r: r['maxLevel']):
        if row.get('quality') == name and item_level <= row['maxLevel']:
            return name, row['maxLevel'], key
    return None


def observed(table: list[dict], records: list[dict]) -> dict[tuple, dict]:
    """Chance and average count for each material, measured from real disenchants."""
    counts: dict[tuple, dict] = {}
    for record in records:
        item = record.get('item') or {}
        bucket = _bucket(table, item.get('quality'), int(item.get('itemLevel') or 0), item.get('kind'))
        if not bucket:
            continue
        stats = counts.setdefault(bucket, {'samples': 0, 'mats': {}})
        stats['samples'] += 1
        mats = record.get('mats') or {}
        for mat in (mats.values() if isinstance(mats, dict) else mats):
            got = stats['mats'].setdefault(int(mat['id']), [0, 0])
            got[0] += 1
            got[1] += int(mat.get('count') or 1)
    out = {}
    for bucket, stats in counts.items():
        out[bucket] = {'samples': stats['samples'],
                       'yields': [(item_id, times / stats['samples'], total / times)
                                  for item_id, (times, total) in stats['mats'].items()]}
    return out


def effective_table(table: list[dict], records: list[dict], min_samples: int) -> list[dict]:
    """The configured table, with each well-sampled bucket replaced by measured yields."""
    buckets = observed(table, records)
    out = []
    for row in table:
        row = dict(row)
        for key in KINDS.values():
            measured = buckets.get((row.get('quality'), row['maxLevel'], key))
            if measured and measured['samples'] >= min_samples:
                row[key] = [[i, chance, qty] for i, chance, qty in measured['yields']]
        out.append(row)
    return out


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

from anvilbook.disenchant import effective_table, observed, parse_records

TABLE = [
    {'quality': 'Uncommon', 'maxLevel': 15, 'armor': [[10940, 1.0, 1]], 'weapon': [[10940, 1.0, 1]]},
    {'quality': 'Uncommon', 'maxLevel': 25, 'armor': [[10940, 1.0, 1]], 'weapon': [[10940, 1.0, 1]]},
]


def record(quality, level, kind, mats):
    return {'time': 1, 'item': {'id': 3490, 'quality': quality, 'itemLevel': level, 'kind': kind},
            'mats': {i + 1: {'id': m, 'count': c} for i, (m, c) in enumerate(mats)}}


RECORDS = [
    record(2, 20, 'Weapon', [(10940, 2)]),
    record(2, 20, 'Weapon', [(10940, 3)]),
    record(2, 20, 'Weapon', [(10938, 1)]),
    record(2, 12, 'Armor', [(10940, 1)]),
]


def test_parse_records_reads_the_saved_list():
    db = {'disenchants': {1: RECORDS[0], 2: RECORDS[1]}}
    assert [r['item']['itemLevel'] for r in parse_records(db)] == [20, 20]
    assert parse_records({}) == []


def test_observed_counts_chances_and_average_quantity():
    buckets = observed(TABLE, RECORDS)
    weapon = buckets[('Uncommon', 25, 'weapon')]
    assert weapon['samples'] == 3
    assert weapon['yields'] == [(10940, 2 / 3, 2.5), (10938, 1 / 3, 1.0)]
    assert buckets[('Uncommon', 15, 'armor')]['samples'] == 1


def test_effective_table_replaces_only_well_sampled_buckets():
    table = effective_table(TABLE, RECORDS, min_samples=3)
    by_level = {row['maxLevel']: row for row in table}
    assert by_level[25]['weapon'] == [[10940, 2 / 3, 2.5], [10938, 1 / 3, 1.0]]
    assert by_level[25]['armor'] == [[10940, 1.0, 1]]
    assert by_level[15]['armor'] == [[10940, 1.0, 1]]
    assert effective_table(TABLE, [], min_samples=3) == TABLE

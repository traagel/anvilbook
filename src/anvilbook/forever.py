"""Forever's recipe list, taken from the game client's own data tables.

The classic item database lacks Forever's new recipes and has the old reagents and skill-up
thresholds for many others, so the app takes every recipe from these tables instead.
`python -m anvilbook.forever BUILD [CSV_FOLDER]` downloads the tables from wago.tools (or reads
a folder of the same CSV files) and writes TABLE_PATH, which a release ships.
"""

import csv
import io
import json
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

TABLE_PATH = Path(__file__).parent / 'data' / 'forever-recipes.json'
WAGO = 'https://wago.tools/db2/{table}/csv?build={build}'
TABLES = ('SkillLine', 'SkillLineAbility', 'TradeSkillCategory', 'SpellEffect', 'SpellReagents', 'ItemEffect',
          'ItemXItemEffect', 'ItemSparse', 'Item')
# Alchemy, Blacksmithing, Cooking, Enchanting, Engineering, First Aid, Leatherworking, Mining,
# Poisons and Tailoring: the skill lines whose recipes make items.
PROFESSIONS = {'171', '164', '185', '333', '202', '129', '165', '186', '40', '197'}
CREATE_ITEM, LEARN_SPELL, ON_LEARN, WITH_SKILL = '24', '36', '6', '1'
# Forever's client also carries Season of Discovery recipes that its realms do not offer.
UNOFFERED = {'SEASON OF DISCOVERY'}
QUALITY = {'0': 'Poor', '1': 'Common', '2': 'Uncommon', '3': 'Rare', '4': 'Epic', '5': 'Legendary'}
CLASS = {'2': 'Weapon', '4': 'Armor'}


def _int(value) -> int:
    return int(float(value or 0))


def build(tables: dict[str, list[dict]], build_id: str) -> dict:
    lines = {r['ID']: r['DisplayName_lang'] for r in tables['SkillLine']}
    categories = {r['ID']: r['Name_lang'] for r in tables['TradeSkillCategory']}
    creates, learned_by = {}, defaultdict(list)
    for e in tables['SpellEffect']:
        if e['Effect'] == CREATE_ITEM and e['EffectItemType'] not in ('', '0'):
            creates[e['SpellID']] = (int(e['EffectItemType']), max(1, round(float(e['EffectBasePointsF'] or 1))))
        elif e['Effect'] == LEARN_SPELL:
            learned_by[e['EffectTriggerSpell']].append(e['SpellID'])
    reagents = {r['SpellID']: [[int(r[f'Reagent_{i}']), _int(r[f'ReagentCount_{i}'])]
                               for i in range(8) if r[f'Reagent_{i}'] not in ('', '0')]
                for r in tables['SpellReagents']}
    effects = {r['ID']: r for r in tables['ItemEffect']}
    teaches = defaultdict(list)
    for link in tables['ItemXItemEffect']:
        effect = effects.get(link['ItemEffectID'])
        if effect and effect['TriggerType'] == ON_LEARN:
            teaches[effect['SpellID']].append(int(link['ItemID']))
    sparse = {r['ID']: r for r in tables['ItemSparse']}
    kinds = {r['ID']: r for r in tables['Item']}

    def required_skill(item_id: int) -> int | None:
        row = sparse.get(str(item_id))
        return _int(row['RequiredSkillRank']) if row else None

    recipes, used = [], set()
    for ability in tables['SkillLineAbility']:
        spell = ability['Spell']
        if (ability['SkillLine'] not in PROFESSIONS or ability['TradeSkillCategoryID'] in ('', '0')
                or categories.get(ability['TradeSkillCategoryID']) in UNOFFERED or spell not in creates):
            continue
        item, made = creates[spell]
        # A pattern teaches the recipe itself, or a spell that teaches it.
        patterns = teaches.get(spell, []) + [i for s in learned_by.get(spell, []) for i in teaches.get(s, [])]
        recipe = {'spell': int(spell), 'item': item, 'profession': lines[ability['SkillLine']], 'made': made,
                  'reagents': reagents.get(spell, []), 'yellow': _int(ability['TrivialSkillLineRankLow']),
                  'grey': _int(ability['TrivialSkillLineRankHigh'])}
        if patterns:
            known = [p for p in patterns if required_skill(p) is not None]
            pattern = min(known, key=lambda p: required_skill(p) or 0) if known else min(patterns)
            # None: the server sends this pattern's details itself, so the client tables lack them.
            recipe.update(source='pattern', pattern=pattern, learn=required_skill(pattern))
        elif ability['AcquireMethod'] == WITH_SKILL:
            recipe.update(source='start', learn=0)
        else:
            # Trainers are server data; apply() estimates the skill they need.
            recipe.update(source='trainer', learn=None)
        recipes.append(recipe)
        used.update([item, *(r[0] for r in recipe['reagents'])])
        if patterns:
            used.add(recipe['pattern'])

    items = {}
    for item_id in sorted(used):
        row, kind = sparse.get(str(item_id)), kinds.get(str(item_id))
        if not row or not row['Display_lang']:
            continue
        details = {'name': row['Display_lang'], 'quality': QUALITY.get(row['OverallQualityID']),
                   'itemLevel': _int(row['ItemLevel']), 'requiredLevel': _int(row['RequiredLevel']),
                   'sellPrice': _int(row['SellPrice'])}
        if kind and kind['ClassID'] in CLASS:
            details['class'] = CLASS[kind['ClassID']]
        items[item_id] = details
    recipes.sort(key=lambda r: (r['profession'], r['item'], r['spell']))
    return {'build': build_id, 'recipes': recipes, 'items': items}


def dumps(table: dict) -> str:
    """One recipe and one item to a line, so a new build shows as a readable diff."""
    recipes = ',\n'.join(json.dumps(r, sort_keys=True) for r in table['recipes'])
    items = ',\n'.join(f'"{i}": {json.dumps(d, sort_keys=True)}' for i, d in table['items'].items())
    return f'{{"build": {json.dumps(table["build"])},\n"recipes": [\n{recipes}\n],\n"items": {{\n{items}\n}}}}\n'


def read(path: Path) -> dict | None:
    try:
        table = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None
    table['items'] = {int(i): d for i, d in table['items'].items()}
    return table


def load() -> dict | None:
    return read(TABLE_PATH)


def apply(items: dict[int, dict], table: dict | None) -> dict[int, dict]:
    """The item database with Forever's recipes in place of the classic ones, and Forever's item
    details on top. Without a table, the classic data stays."""
    if not table:
        return items
    classic = {(r.get('category'), item_id): r.get('requiredSkill')
               for item_id, item in items.items() for r in item.get('createdBy') or []}
    out = {i: {**item, 'createdBy': []} if item.get('createdBy') else item for i, item in items.items()}
    for item_id, details in table['items'].items():
        out[item_id] = {**out.get(item_id, {}), **details}
    for r in table['recipes']:
        learn = r['learn']
        estimated = learn is None
        if estimated:
            # The classic learn skill, else the yellow threshold, which is never below it.
            learn = classic.get((r['profession'], r['item']))
            learn = r['yellow'] if learn is None else learn
        recipe = {'amount': [r['made'], r['made']], 'requiredSkill': learn, 'category': r['profession'],
                  'reagents': [{'itemId': i, 'amount': n} for i, n in r['reagents']],
                  'yellow': r['yellow'], 'grey': r['grey'], 'source': r['source'], 'estimated': estimated}
        if 'pattern' in r:
            recipe['pattern'] = r['pattern']
        item = out.get(r['item']) or {'name': None}
        out[r['item']] = {**item, 'createdBy': [*(item.get('createdBy') or []), recipe]}
    return out


def fetch(build_id: str) -> dict[str, list[dict]]:
    tables = {}
    for name in TABLES:
        request = urllib.request.Request(WAGO.format(table=name, build=build_id),
                                         headers={'User-Agent': 'anvilbook (github.com/traagel/anvilbook)'})
        with urllib.request.urlopen(request, timeout=120) as response:
            tables[name] = list(csv.DictReader(io.StringIO(response.read().decode('utf-8'))))
    return tables


def read_folder(folder: Path) -> dict[str, list[dict]]:
    return {name: list(csv.DictReader((folder / f'{name}.csv').open(encoding='utf-8'))) for name in TABLES}


def main(argv: list[str]) -> None:
    if not argv:
        sys.exit('usage: python -m anvilbook.forever BUILD [CSV_FOLDER]')
    tables = read_folder(Path(argv[1])) if len(argv) > 1 else fetch(argv[0])
    table = build(tables, argv[0])
    TABLE_PATH.parent.mkdir(exist_ok=True)
    TABLE_PATH.write_text(dumps(table), encoding='utf-8')
    counts = defaultdict(int)
    for r in table['recipes']:
        counts[r['profession']] += 1
    print(f'{len(table["recipes"])} recipes, {len(table["items"])} items: {dict(sorted(counts.items()))}')


if __name__ == '__main__':
    main(sys.argv[1:])

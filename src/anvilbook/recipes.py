from dataclasses import dataclass
from pathlib import Path

from .luatable import parse_savedvariables

# The smelting window can report the spell name instead of the Mining skill line.
ALIASES = {'Smelting': 'Mining'}


@dataclass
class GameExport:
    character: str
    updated: int
    professions: dict[str, dict]


def _array(t) -> list:
    return [t[k] for k in sorted(t)] if isinstance(t, dict) else []


def load_export(path: Path) -> GameExport | None:
    try:
        text = path.read_bytes()
    except FileNotFoundError:
        return None
    db = parse_savedvariables(text).get('AnvilbookExportDB')
    chars = db.get('characters') if isinstance(db, dict) else None
    if not chars:
        return None
    name, char = max(chars.items(), key=lambda kv: kv[1].get('updated') or 0)
    professions = {ALIASES.get(str(p), str(p)): data for p, data in (char.get('professions') or {}).items()}
    return GameExport(name, int(char.get('updated') or 0), professions)


def export_skills(export: GameExport) -> dict[str, int]:
    return {p: int(data.get('rank') or 0) for p, data in export.professions.items()}


def merge(items: dict[int, dict], export: GameExport) -> dict[int, dict]:
    exported = set(export.professions)
    out = {}
    for item_id, item in items.items():
        recipes = item.get('createdBy') or []
        kept = [r for r in recipes if r.get('category') not in exported]
        out[item_id] = {**item, 'createdBy': kept} if len(kept) != len(recipes) else item
    for prof, data in export.professions.items():
        for item_id, rec in (data.get('recipes') or {}).items():
            reagents = _array(rec.get('reagents'))
            for r in reagents:
                out.setdefault(int(r['id']), {'name': r.get('name')})
            item = out.get(int(item_id)) or {'name': rec.get('name')}
            out[int(item_id)] = {**item, 'createdBy': [*(item.get('createdBy') or []), {
                'amount': [int(rec.get('minMade') or 1), int(rec.get('maxMade') or 1)],
                'requiredSkill': 0,
                'category': prof,
                'known': True,
                'difficulty': rec.get('difficulty'),
                'reagents': [{'itemId': int(r['id']), 'amount': int(r['count'])} for r in reagents],
            }]}
    return out

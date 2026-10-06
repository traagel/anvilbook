"""The addon's view of the app: AnvilbookData.lua, which the game reads at /reload.

A WoW addon cannot read files or use the network, so this file is the only way in. The way
back is the addon's SavedVariables, where the game stores settings changed in game.
"""

import logging
import math
from datetime import datetime
from pathlib import Path

from . import __version__
from .luatable import LuaParseError, parse_savedvariables
from .recipes import GameExport

log = logging.getLogger(__name__)

FORMAT = 1
FILE_NAME = 'AnvilbookData.lua'
HISTORY_SCANS = 30
CALC_KEYS = ('ah_cut', 'cast_seconds', 'min_listed', 'max_use_level', 'min_disenchant_samples',
             'assume_enchanter', 'disenchant_table')


def _ranged(low, high):
    def check(value):
        number = type(low)(value)
        if not low <= number <= high:
            raise ValueError(f'{number} is outside {low} to {high}')
        return number
    return check


def _published(value) -> dict[str, bool]:
    return {str(k): bool(v) for k, v in (value.items() if isinstance(value, dict) else [])}


GAME_KEYS = {
    'ah_cut': _ranged(0.0, 1.0),
    'cast_seconds': _ranged(0.1, 3600.0),
    'min_listed': _ranged(0, 1_000_000),
    'max_use_level': _ranged(0, 1000),
    'min_disenchant_samples': _ranged(1, 1_000_000),
    'assume_enchanter': bool,
    'push_prices': bool,
    'published_characters': _published,
}


def _string(s: str) -> str:
    out = []
    for ch in s:
        if ch in '\\"':
            out.append('\\' + ch)
        elif ord(ch) < 32 or ord(ch) == 127:
            # Three digits, so a digit after the escape cannot join it.
            out.append(f'\\{ord(ch):03d}')
        else:
            out.append(ch)
    return '"' + ''.join(out) + '"'


def to_lua(value) -> str:
    if value is None:
        return 'nil'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f'{value} has no Lua form')
        return repr(value)
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, (list, tuple)):
        return '{' + ', '.join(to_lua(v) for v in value) + '}'
    if isinstance(value, dict):
        # The app's own parser, and the game's SavedVariables, use only bracketed keys.
        parts = [f'[{to_lua(k)}] = {to_lua(v)}' for k, v in value.items() if v is not None]
        return '{\n' + ',\n'.join(parts) + '\n}' if parts else '{}'
    raise TypeError(f'{type(value).__name__} has no Lua form')


def _array(value) -> list:
    return [value[k] for k in sorted(value)] if isinstance(value, dict) else list(value or [])


def _field(value) -> str:
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _epoch(iso: str) -> int:
    return int(datetime.fromisoformat(iso).timestamp())


def recipe_items(exports: list[GameExport]) -> dict[int, str | None]:
    """Every output and reagent of every recorded recipe, with the name the game gave it."""
    out: dict[int, str | None] = {}
    for export in exports:
        for profession in export.professions.values():
            for item_id, recipe in (profession.get('recipes') or {}).items():
                out.setdefault(int(item_id), recipe.get('name'))
                for reagent in _array(recipe.get('reagents')):
                    out.setdefault(int(reagent['id']), reagent.get('name'))
    return out


def build(store, items: dict[int, dict], exports: list[GameExport], share_error: str | None) -> dict:
    settings = store.settings()
    scans = store.scans()[-HISTORY_SCANS:]
    per_scan = [store.prices(s['id']) for s in scans]
    latest = per_scan[-1] if per_scan else {}
    listed = set().union(*per_scan) if per_scan else set()
    from_game = recipe_items(exports)

    packed = {}
    for item_id in sorted(listed | from_game.keys()):
        item = items.get(item_id) or {}
        name = item.get('name') or from_game.get(item_id) or ''
        packed[item_id] = '|'.join(_field(item.get(k)) for k in (
            'quality', 'itemLevel', 'requiredLevel', 'class', 'sellPrice', 'vendorPrice')) + '|' + name

    history = {}
    for item_id in sorted(listed):
        points = [scan.get(item_id) for scan in per_scan]
        history[item_id] = ';'.join(f"{p['min_price']},{p['available']}" if p else '' for p in points)

    changed_at = settings['changed_at']
    return {
        'version': FORMAT,
        'appVersion': __version__,
        'realm': scans[-1]['realm'] if scans else settings['realm'],
        'scans': [{'id': s['id'], 'time': _epoch(s['file_mtime']), 'items': s['items']} for s in scans],
        'items': packed,
        'prices': ';'.join(f"{i}:{p['min_price']}:{p['available']}:{p['day_high']}"
                           for i, p in sorted(latest.items())),
        'vendor': ';'.join(f'{i}:{p}' for i, p in sorted(store.vendor_prices().items())),
        'history': history,
        'settings': {**{k: settings[k] for k in CALC_KEYS},
                     'changed_at': {k: int(t) for k, t in changed_at.items() if k in GAME_KEYS}},
        'share': {'server_url': settings['server_url'], 'username': settings['server_username'],
                  'signed_in': bool(settings['server_token']), 'push_prices': bool(settings['push_prices']),
                  'published_characters': settings['published_characters'], 'error': share_error},
    }


def write(folder: Path, data: dict, generated: int) -> Path:
    path = folder / FILE_NAME
    text = ('-- Written by the anvilbook app. Edits here are lost.\n'
            f'AnvilbookData = {to_lua({**data, "generated": generated})}\n')
    # The game must never load a half-written file.
    part = path.with_suffix('.part')
    part.write_text(text, encoding='utf-8')
    part.replace(path)
    return path


def game_requests(export_path: Path) -> tuple[dict[str, tuple[object, int]], int]:
    """Settings changed in game, and the time of the last "Push now" pressed in game."""
    try:
        db = parse_savedvariables(export_path.read_bytes()).get('AnvilbookExportDB')
    except (FileNotFoundError, LuaParseError) as e:
        if not isinstance(e, FileNotFoundError):
            log.warning('recipe export unreadable: %s', e)
        return {}, 0
    if not isinstance(db, dict):
        return {}, 0
    edits = {}
    saved = db.get('edits')
    for key, edit in (saved.items() if isinstance(saved, dict) else []):
        if key in GAME_KEYS and isinstance(edit, dict) and 'value' in edit:
            edits[key] = (edit['value'], int(edit.get('time') or 0))
    return edits, int(db.get('pushRequested') or 0)


def accepted(edits: dict[str, tuple[object, int]], changed_at: dict[str, int]) -> dict:
    """The game edits newer than the app's own change of the same key, checked and converted."""
    out = {}
    for key, (value, when) in edits.items():
        if when <= int(changed_at.get(key) or 0):
            continue
        try:
            out[key] = GAME_KEYS[key](value)
        except (TypeError, ValueError) as e:
            log.warning('ignoring the game edit of %s: %s', key, e)
    return out

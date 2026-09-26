"""Find the game's SavedVariables folder without asking the user to hunt for it."""

import os
import string
from pathlib import Path

# WoW keeps one SavedVariables folder per account under each flavor (_classic_beta_, _retail_).
PATTERN = '*/WTF/Account/*/SavedVariables/Auctionator.lua'
DEEP_PATTERN = f'**/{PATTERN}'
MAX_ROOT_DEPTH = 6


def search_roots() -> list[Path]:
    home = Path.home()
    roots = [
        home / '.local/share/Steam/steamapps/compatdata',
        home / '.steam/steam/steamapps/compatdata',
        home / 'Games',
        home / '.wine/drive_c',
        Path('/Applications'),
    ]
    roots += [Path(f'{letter}:/') / 'Program Files (x86)' for letter in string.ascii_uppercase[2:]]
    roots += [Path(f'{letter}:/') / 'Program Files' for letter in string.ascii_uppercase[2:]]
    roots += [Path(f'{letter}:/') / 'World of Warcraft' for letter in string.ascii_uppercase[2:]]
    env = os.environ.get('ANVILBOOK_WOW')
    if env:
        roots.insert(0, Path(env).expanduser())
    return [r for r in roots if r.exists()]


def find_savedvariables(roots: list[Path] | None = None) -> list[Path]:
    """Auctionator.lua files, newest first. One per account and flavor."""
    found: set[Path] = set()
    for root in roots if roots is not None else search_roots():
        try:
            # ~/.steam and ~/.local/share/Steam are the same files, so compare resolved paths.
            found.update(p.resolve() for p in root.glob(PATTERN))
            # Steam and Lutris bury the game a few folders deep.
            found.update(p.resolve() for p in root.glob(DEEP_PATTERN)
                         if len(p.relative_to(root).parts) <= MAX_ROOT_DEPTH + 5)
        except (OSError, ValueError):
            continue
    return sorted(found, key=lambda p: -p.stat().st_mtime)


def flavor_dir(savedvariables: Path) -> Path:
    """`.../_classic_beta_` for `.../_classic_beta_/WTF/Account/<id>/SavedVariables/Auctionator.lua`."""
    return savedvariables.parents[4]


def addons_dir(savedvariables: Path) -> Path:
    return flavor_dir(savedvariables) / 'Interface' / 'AddOns'

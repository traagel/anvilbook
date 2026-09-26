"""Find the game's SavedVariables folder without asking the user to hunt for it."""

import os
import string
import time
from dataclasses import dataclass
from pathlib import Path

# WoW keeps one SavedVariables folder per account under each flavor (_classic_beta_, _retail_).
TAIL = '_*_/WTF/Account/*/SavedVariables'
# Bounded depth and a named game folder instead of '**': Steam buries the game about 6 folders
# deep, and walking a whole drive takes minutes.
PATTERNS = ([f'{"*/" * depth}World of Warcraft/{TAIL}' for depth in range(0, 7)]
            + [f'{"*/" * depth}{TAIL}' for depth in range(0, 3)])
SEARCH_SECONDS = 20


@dataclass(frozen=True)
class Install:
    savedvariables: Path
    account: str
    flavor: str
    has_prices: bool

    @property
    def auctionator(self) -> Path:
        return self.savedvariables / 'Auctionator.lua'


def search_roots() -> list[Path]:
    home = Path.home()
    roots = [
        home / '.local/share/Steam/steamapps/compatdata',
        home / '.steam/steam/steamapps/compatdata',
        home / 'Games',
        home / '.wine/drive_c',
        Path('/Applications'),
    ]
    for letter in string.ascii_uppercase[2:]:
        drive = Path(f'{letter}:/')
        roots += [drive / 'Program Files (x86)', drive / 'Program Files', drive / 'World of Warcraft',
                  drive / 'Games']
    env = os.environ.get('ANVILBOOK_WOW')
    if env:
        roots.insert(0, Path(env).expanduser())
    return [r for r in roots if r.exists()]


def find_installs(roots: list[Path] | None = None, deadline: float | None = None) -> list[Install]:
    """Game folders, newest first. Stops at the deadline so a slow disk cannot hang the app."""
    deadline = deadline if deadline is not None else time.monotonic() + SEARCH_SECONDS
    found: dict[Path, Install] = {}
    for root in roots if roots is not None else search_roots():
        for pattern in PATTERNS:
            if time.monotonic() > deadline:
                return _sorted(found)
            try:
                for saved in root.glob(pattern):
                    if not saved.is_dir():
                        continue
                    saved = saved.resolve()
                    found[saved] = Install(saved, saved.parent.name, saved.parents[3].name,
                                           (saved / 'Auctionator.lua').is_file())
            except (OSError, ValueError):
                continue
    return _sorted(found)


def _sorted(found: dict[Path, Install]) -> list[Install]:
    def freshness(install: Install) -> float:
        target = install.auctionator if install.has_prices else install.savedvariables
        try:
            return -target.stat().st_mtime
        except OSError:
            return 0

    return sorted(found.values(), key=freshness)


def find_savedvariables(roots: list[Path] | None = None) -> list[Path]:
    return [i.auctionator for i in find_installs(roots) if i.has_prices]


def looks_like_addon_code(path: Path) -> bool:
    """Auctionator's own source also holds a file called Auctionator.lua; that is not the data."""
    return 'addons' in [part.lower() for part in path.parts]


def flavor_dir(savedvariables: Path) -> Path:
    """`.../_classic_beta_` for `.../_classic_beta_/WTF/Account/<id>/SavedVariables/Auctionator.lua`."""
    return savedvariables.parents[4]


def addons_dir(savedvariables: Path) -> Path:
    return flavor_dir(savedvariables) / 'Interface' / 'AddOns'

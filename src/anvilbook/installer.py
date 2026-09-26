"""Copy the bundled addon into the game so nobody has to move files by hand."""

import shutil
from pathlib import Path

from .discover import addons_dir

ADDON_NAME = 'AnvilbookExport'


def addon_source() -> Path:
    return Path(__file__).parent / 'addon' / ADDON_NAME


def target_dir(savedvariables: Path) -> Path:
    return addons_dir(savedvariables) / ADDON_NAME


def is_installed(savedvariables: Path) -> bool:
    return (target_dir(savedvariables) / f'{ADDON_NAME}.toc').exists()


def install_addon(savedvariables: Path) -> Path:
    target = target_dir(savedvariables)
    # A symlink is a developer setup; replacing it would delete their working copy.
    if target.is_symlink():
        raise FileExistsError(f'{target} is a symlink, leaving it alone')
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(addon_source(), target)
    return target

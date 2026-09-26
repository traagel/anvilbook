"""Settings a person may want before the app starts, kept in a small TOML file."""

import logging
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


def config_path() -> Path:
    override = os.environ.get('ANVILBOOK_CONFIG')
    if override:
        return Path(override).expanduser()
    base = os.environ.get('APPDATA') or os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config'
    return Path(base) / 'anvilbook' / 'config.toml'


@dataclass
class Config:
    data_dir: Path | None = None
    savedvariables_path: Path | None = None
    host: str = '127.0.0.1'
    port: int = 8765
    open_browser: bool = True


def load_config(path: Path | None = None) -> Config:
    path = path or config_path()
    try:
        values = tomllib.loads(path.read_text())
    except FileNotFoundError:
        values = {}
    except (tomllib.TOMLDecodeError, OSError) as e:
        log.warning('ignoring %s: %s', path, e)
        values = {}
    as_path = lambda key: Path(values[key]).expanduser() if values.get(key) else None
    return Config(
        data_dir=as_path('data_dir'),
        savedvariables_path=as_path('savedvariables_path'),
        host=str(values.get('host') or '127.0.0.1'),
        port=int(values.get('port') or 8765),
        open_browser=bool(values.get('open_browser', True)),
    )


def write_config(path: Path | None = None, **values) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    current = load_config(path)
    merged = {**{k: v for k, v in vars(current).items()}, **values}
    lines = []
    for key, value in merged.items():
        if value is None:
            continue
        if isinstance(value, bool):
            lines.append(f'{key} = {str(value).lower()}')
        elif isinstance(value, int):
            lines.append(f'{key} = {value}')
        else:
            lines.append(f'{key} = "{str(value)}"')
    path.write_text('\n'.join(lines) + '\n')

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

from .importer import DecodeError, read_snapshot
from .store import Store

log = logging.getLogger(__name__)


class Importer:
    def __init__(self, store: Store):
        self.store = store
        self.status = {'path': None, 'found': False, 'last_import': None, 'last_error': None}
        self._mtime: float | None = None

    def _error(self, message: str) -> None:
        if message != self.status['last_error']:
            log.warning(message)
        self.status['last_error'] = message

    def run(self, force: bool = False) -> int | None:
        s = self.store.settings()
        path = Path(s['savedvariables_path']).expanduser()
        self.status['path'] = str(path)
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            self.status['found'] = False
            self._error('SavedVariables file not found')
            return None
        self.status['found'] = True
        if mtime == self._mtime and not force:
            return None
        text = path.read_bytes()
        file_hash = hashlib.sha256(text).hexdigest()
        if self.store.has_hash(file_hash):
            self._mtime = mtime
            return None
        try:
            snap = read_snapshot(text, s['realm'])
        except DecodeError as e:
            # WoW can be in the middle of a write; keep _mtime unset so the next poll retries.
            self._error(f'decode failed: {e}')
            return None
        self._mtime = mtime
        if not snap.prices:
            self._error('The file has no price data. Scan the AH, then /reload.')
            return None
        scan_id = self.store.add_scan(snap, datetime.fromtimestamp(mtime, timezone.utc), file_hash)
        self.status['last_import'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        self.status['last_error'] = None
        log.info('imported scan %s with %d items', scan_id, len(snap.prices))
        return scan_id

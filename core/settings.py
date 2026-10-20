"""Remember user choices; merely opening a window never writes game files."""

import json
import logging
import os
from pathlib import Path
import tempfile

from PySide6.QtCore import QLockFile

from core.paths import settings_file


class Settings:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else settings_file()
        self.backup_path = self.path.with_name(self.path.name + '.bak')
        self._values = {}
        for candidate in (self.path, self.backup_path):
            try:
                self._values = self._read(candidate)
                if candidate == self.backup_path:
                    logging.getLogger(__name__).warning("Recovered settings from backup: %s", candidate)
                break
            except FileNotFoundError:
                continue
            except (OSError, ValueError):
                logging.getLogger(__name__).warning("Cannot load settings: %s", candidate, exc_info=True)

    @staticmethod
    def _read(path):
        values = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(values, dict):
            raise ValueError('Settings must be a JSON object')
        return values

    def _latest(self):
        """Do not overwrite an unreadable file with a potentially stale snapshot."""
        for candidate in (self.path, self.backup_path):
            try:
                return self._read(candidate)
            except FileNotFoundError:
                continue
            except ValueError:
                logging.getLogger(__name__).warning("Ignoring malformed settings: %s", candidate)
        return dict(self._values)

    @staticmethod
    def _write_atomic(path, values):
        descriptor, filename = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(values, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(filename, path)
        finally:
            Path(filename).unlink(missing_ok=True)

    def get(self, key: str, default=None):
        value = self._values.get(key, default)
        if default is not None and not isinstance(value, type(default)):
            return default
        return value

    def update(self, **values):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = QLockFile(str(self.path.with_name(self.path.name + '.write.lock')))
        lock.setStaleLockTime(0)
        if not lock.tryLock(1500):
            raise OSError('Cannot lock settings for saving')
        try:
            previous = self._latest()
            updated = {**previous, **values}
            # Preserve the last valid version before replacing the main file.
            # A failed backup leaves the main file and in-memory values intact.
            self._write_atomic(self.backup_path, previous)
            self._write_atomic(self.path, updated)
            self._values = updated
        finally:
            lock.unlock()

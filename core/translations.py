"""One language state shared by every open window."""

import json
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from core.paths import resource_path


class Translations(QObject):
    changed = Signal(str)

    def __init__(self, language: str = "kr", path: Path | None = None):
        super().__init__()
        source = Path(path) if path is not None else resource_path("languages.json")
        self._languages = json.loads(source.read_text(encoding="utf-8"))
        self.language = language if language in self._languages else "kr"

    def text(self, section: str, key: str) -> str:
        value = self._languages[self.language][section]
        for part in key.split("."):
            value = value[part]
        return value

    def set_language(self, language: str):
        if language not in self._languages:
            raise ValueError(f"Unsupported language: {language}")
        if self.language != language:
            self.language = language
            self.changed.emit(language)

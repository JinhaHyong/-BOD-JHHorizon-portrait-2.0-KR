"""Keep user-owned fonts from older versions available without network access."""
import json
from pathlib import Path
from core.paths import settings_file


def font_storage() -> Path:
    return settings_file().parent / 'fonts'


def downloaded_font_label(path: Path) -> str:
    if path.parent == font_storage():
        try:
            info = json.loads(path.with_suffix(path.suffix + '.json').read_text(encoding='utf-8'))
            return f"{info['name']} · {info['variant']}"
        except (OSError, ValueError, TypeError, KeyError):
            pass
    return path.name

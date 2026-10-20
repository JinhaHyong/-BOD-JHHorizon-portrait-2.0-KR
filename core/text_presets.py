"""Persist photo drafts, the latest template, and distinct reusable settings."""

from dataclasses import asdict, fields
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
from uuid import uuid4

from core.portrait_edit import TextOverlay


TEMPLATE_KEY = "portrait_text_template"
DRAFTS_KEY = "portrait_text_drafts"
HISTORY_KEY = "portrait_text_history"


def decode_layers(values) -> list[TextOverlay]:
    if not isinstance(values, list):
        return []
    result, ids = [], set()
    allowed = {field.name for field in fields(TextOverlay)}
    for value in values:
        if not isinstance(value, dict):
            continue
        try:
            layer = TextOverlay(**{key: item for key, item in value.items() if key in allowed})
            if not all(isinstance(item, str) for item in (layer.text, layer.font_family, layer.id)):
                continue
            if layer.font_file is not None and not isinstance(layer.font_file, str):
                continue
            if not isinstance(layer.font_style, str) or layer.font_slant not in ("normal", "italic", "oblique"):
                continue
            if (layer.font_weight is not None
                    and (type(layer.font_weight) is not int or not 1 <= layer.font_weight <= 1000)):
                continue
            if layer.alignment not in ("left", "center", "right"):
                continue
            if not all(isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color)
                       for color in (layer.text_color, layer.background_color)):
                continue
            if not all(isinstance(flag, bool) for flag in (layer.bold, layer.italic, layer.intense, layer.shadow)):
                continue
            numbers = (layer.x, layer.y, layer.width, layer.font_size, layer.text_opacity,
                       layer.background_opacity, layer.padding, layer.radius)
            if layer.height is not None:
                numbers += (layer.height,)
            if not all(isinstance(number, (int, float)) and math.isfinite(number) for number in numbers):
                continue
            layer.x, layer.y = max(0, layer.x), max(0, layer.y)
            layer.width = max(1, min(624, round(layer.width)))
            layer.height = max(1, min(804, layer.height)) if layer.height is not None else None
            layer.font_size = max(8, min(200, round(layer.font_size)))
            layer.text_opacity = max(0, min(100, round(layer.text_opacity)))
            layer.background_opacity = max(0, min(100, round(layer.background_opacity)))
            layer.padding = max(0, min(60, round(layer.padding)))
            layer.radius = max(0, min(60, round(layer.radius)))
            if not layer.id or layer.id in ids:
                layer.id = uuid4().hex
            ids.add(layer.id)
            result.append(layer)
        except (TypeError, ValueError, OverflowError):
            continue
    return result


class TextPresetStore:
    def __init__(self, settings):
        self.settings = settings

    @staticmethod
    def photo_key(path: Path) -> str:
        return os.path.normcase(os.path.abspath(path))

    def load_draft(self, path: Path, stamp: tuple) -> list[TextOverlay] | None:
        entry = self.settings.get(DRAFTS_KEY, {}).get(self.photo_key(path))
        if not isinstance(entry, dict) or entry.get("source_stamp") != list(stamp):
            return None
        if not isinstance(entry.get("layers"), list):
            return None
        return decode_layers(entry["layers"])

    def has_template(self) -> bool:
        return bool(decode_layers(self.settings.get(TEMPLATE_KEY, {}).get("layers")))

    def template_for(self, width: int, height: int) -> list[TextOverlay]:
        return self.layers_for(self.settings.get(TEMPLATE_KEY, {}), width, height)

    @staticmethod
    def layers_for(entry: dict, width: int, height: int) -> list[TextOverlay]:
        old_width, old_height = entry.get("width"), entry.get("height")
        if not all(isinstance(value, (int, float)) and math.isfinite(value) and value > 0
                   for value in (old_width, old_height)):
            return []
        layers = decode_layers(entry.get("layers"))
        for layer in layers:
            layer.id = uuid4().hex
            layer.text = ""
            layer.width = max(1, min(width, round(layer.width * width / old_width)))
            layer.x = max(0, min(width - layer.width, layer.x * width / old_width))
            if layer.height is not None:
                layer.height = max(1, min(height, layer.height * height / old_height))
            layer.y = max(0, min(height - (layer.height or 1), layer.y * height / old_height))
        return layers

    @staticmethod
    def setting_signature(entry: dict) -> str:
        """Text and generated IDs do not create another reusable setting."""
        width, height = entry['width'], entry['height']
        layers = []
        for layer in decode_layers(entry.get('layers')):
            values = asdict(layer)
            values.pop('id')
            values.pop('text')
            for key in ('x', 'width'):
                values[key] = round(values[key] / width, 6)
            for key in ('y', 'height'):
                if values[key] is not None:
                    values[key] = round(values[key] / height, 6)
            for key in ('text_color', 'background_color', 'font_family', 'font_style'):
                values[key] = values[key].casefold()
            if values['font_file']:
                values['font_file'] = os.path.normcase(os.path.abspath(values['font_file']))
            layers.append(values)
        data = json.dumps(layers, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(data.encode('utf-8')).hexdigest()

    @classmethod
    def history_entry(cls, value, path=None):
        if not isinstance(value, dict):
            return None
        width, height = value.get('width'), value.get('height')
        if not all(isinstance(number, (int, float)) and math.isfinite(number) and number > 0
                   for number in (width, height)):
            return None
        layers = decode_layers(value.get('layers'))
        if not layers:
            return None
        entry = {**value, 'width': width, 'height': height,
                 'layers': [asdict(layer) for layer in layers]}
        source = value.get('source_path', path)
        entry['source_path'] = source if isinstance(source, str) else ''
        entry['id'] = cls.setting_signature(entry)
        return entry

    def history(self) -> list[dict]:
        stored = self.settings.get(HISTORY_KEY)
        if isinstance(stored, list):
            entries = [self.history_entry(value) for value in stored]
        else:
            # Old versions retained one draft per photo; preserve their original order.
            entries = [self.history_entry(value, path)
                       for path, value in self.settings.get(DRAFTS_KEY, {}).items()]
            entries.append(self.history_entry(self.settings.get(TEMPLATE_KEY, {})))
        unique = {}
        for entry in entries:
            if entry is not None:
                unique.setdefault(entry['id'], entry)
        return list(unique.values())

    def has_history(self) -> bool:
        return bool(self.history())

    def preview_path(self, entry: dict) -> Path:
        # Settings may live in a portable/custom location as well as AppData.
        folder = self.settings.path.parent / 'portrait-preset-previews'
        signature = self.setting_signature(entry)
        return folder / (signature + '.png')

    def updates_for_apply(self, path: Path, stamp: tuple, width: int, height: int,
                          layers: list[TextOverlay]) -> dict:
        payload = {"width": width, "height": height, "layers": [asdict(layer) for layer in layers],
                   "source_path": str(Path(path).absolute()), "source_stamp": list(stamp)}
        drafts = dict(self.settings.get(DRAFTS_KEY, {}))
        drafts[self.photo_key(path)] = {**payload, "source_stamp": list(stamp)}
        history = self.history()
        entry = self.history_entry(payload)
        if entry is not None:
            now = datetime.now(timezone.utc).isoformat()
            existing = next((value for value in history if value['id'] == entry['id']), None)
            if existing is not None:
                # The first photo/text remains the representative of this setting.
                existing['last_used_at'] = now
            else:
                history.append({**entry, 'created_at': now, 'last_used_at': now})
        return {TEMPLATE_KEY: payload, DRAFTS_KEY: drafts, HISTORY_KEY: history}

    @classmethod
    def batch_layers_for(cls, source: dict, width: int, height: int,
                         existing: list[TextOverlay]) -> list[TextOverlay]:
        layers = cls.layers_for(source, width, height)
        # A different box count replaces the structure with empty contents.
        # Equal counts retain each destination's own text in its saved box order.
        if len(layers) == len(existing):
            for layer, previous in zip(layers, existing):
                layer.id = previous.id
                layer.text = previous.text
        return layers

    def updates_for_batch(self, records: list[dict], source: dict) -> dict:
        """Build one settings transaction, retaining unrelated photo drafts."""
        if not records:
            return {}
        first = records[0]
        updates = self.updates_for_apply(first['path'], first['stamp'],
                                         first['width'], first['height'], first['layers'])
        for record in records[1:]:
            updates[DRAFTS_KEY][self.photo_key(record['path'])] = {
                'source_path': str(Path(record['path']).absolute()),
                'source_stamp': list(record['stamp']), 'width': record['width'],
                'height': record['height'], 'layers': [asdict(layer) for layer in record['layers']]}
        updates[TEMPLATE_KEY] = {**source, 'layers': [asdict(layer) for layer in decode_layers(source['layers'])]}
        return updates

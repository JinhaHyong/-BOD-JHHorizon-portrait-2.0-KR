"""Prepare multi-portrait settings without touching source images or settings files."""

from copy import deepcopy
import logging
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QRunnable, Signal

from core.text_presets import TextPresetStore, decode_layers
from services.portrait_loader import stamp_for, to_qimage
from services.portrait_service import PortraitService


class BatchSignals(QObject):
    progress = Signal(int, int)
    finished = Signal(object)


class PortraitBatchTask(QRunnable):
    def __init__(self, paths, source, drafts, source_changed_message):
        super().__init__()
        self.paths = list(paths)
        self.source = deepcopy(source)
        self.drafts = deepcopy(drafts)
        self.source_changed_message = source_changed_message
        self.cancelled = Event()
        self.signals = BatchSignals()

    def run(self):
        records, skipped = [], []
        source_key = TextPresetStore.photo_key(self.source['source_path'])
        try:
            if stamp_for(self.source['source_path']) != tuple(self.source['source_stamp']):
                raise ValueError(self.source_changed_message)
            for number, path in enumerate(self.paths, 1):
                if self.cancelled.is_set():
                    self.signals.finished.emit({'cancelled': True})
                    return
                try:
                    stamp = stamp_for(path)
                    image = PortraitService().read_image(path)
                    if stamp_for(path) != stamp:
                        raise ValueError('Source changed while preparing settings')
                    key = TextPresetStore.photo_key(path)
                    raw = self.source if key == source_key else self.drafts.get(key)
                    existing = (decode_layers(raw.get('layers')) if isinstance(raw, dict)
                                and raw.get('source_stamp') == list(stamp) else [])
                    layers = TextPresetStore.batch_layers_for(self.source, image.width, image.height, existing)
                    records.append({'path': Path(path), 'stamp': stamp,
                                    'width': image.width, 'height': image.height, 'layers': layers,
                                    'previous_count': len(existing),
                                    'base': to_qimage(image) if not records else None})
                except (OSError, ValueError) as error:
                    skipped.append((str(path), str(error)))
                self.signals.progress.emit(number, len(self.paths))
            self.signals.finished.emit({'records': records, 'skipped': skipped,
                                        'cancelled': self.cancelled.is_set()})
        except Exception as error:
            logging.warning('Could not prepare portrait settings', exc_info=True)
            self.signals.finished.emit({'error': str(error)})

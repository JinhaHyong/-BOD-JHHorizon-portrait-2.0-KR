"""Confirm TTF availability using small metadata requests, never font downloads."""

from collections import deque
import json
import time

from PySide6.QtCore import QObject, QTimer, Signal

from core.font_previews import bundled_assets
from core.online_fonts import FontAsset, archive_url
from core.paths import settings_file
from services.online_font_service import OnlineFontService, atomic_write


class TtfCatalogService(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.service = OnlineFontService(self)
        self.path = settings_file().parent / 'online-font-ttf-assets.json'
        try:
            records = json.loads(self.path.read_text(encoding='utf-8'))
            self.records = records if isinstance(records, dict) else {}
        except (OSError, ValueError):
            self.records = {}
        self.assets = {}
        self.queue = deque()
        self.active = set()
        self.generation = 0
        self.enabled = False
        self.closed = False
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.save)

    def set_fonts(self, fonts):
        self.generation += 1
        self.service.cancel_preview()
        self.service.ttf_resolved.clear()
        self.active.clear()
        self.queue.clear()
        self.assets.clear()
        for font in fonts:
            record = self.records.get(font.repo)
            try:
                fresh = (record['css'] == font.css
                         and 0 <= time.time() - record['checked'] < 7 * 24 * 3600)
                if fresh:
                    assets = [FontAsset(font.repo, row['url'], row['label'])
                              for row in record['assets']
                              if archive_url(row['url'], font.repo)
                              and row['url'].lower().endswith('.ttf')]
                    if assets or not record['assets']:
                        self.assets[font.repo] = assets
                        continue
            except (TypeError, KeyError, ValueError, AttributeError):
                pass
            assets = [a for a in bundled_assets(font.repo)
                      if a.saved_path.suffix.lower() == '.ttf']
            if not assets:
                assets = [a for a in self.service.resolved.get(font.repo, [])
                          if a.saved_path.suffix.lower() == '.ttf']
            if assets:
                self.assets[font.repo] = assets
            else:
                self.queue.append(font)
        self.changed.emit()
        QTimer.singleShot(0, self.pump)

    def assets_for(self, repo):
        return self.assets.get(repo, [])

    @property
    def pending_count(self):
        return len(self.queue) + len(self.active)

    def set_enabled(self, enabled):
        self.enabled = enabled
        if enabled:
            QTimer.singleShot(0, self.pump)

    def pump(self):
        if self.closed or not self.enabled:
            return
        while self.queue and len(self.active) < 2:
            font = self.queue.popleft()
            generation = self.generation
            self.active.add(font.repo)

            def ready(assets, font=font, generation=generation):
                if self.closed or generation != self.generation:
                    return
                self.assets[font.repo] = assets
                self.records[font.repo] = {
                    'css': font.css, 'checked': time.time(),
                    'assets': [{'url': a.url, 'label': a.label} for a in assets],
                }
                self.save_timer.start(250)
                self._finish(font.repo, generation)

            def failed(_message, repo=font.repo, generation=generation):
                # A network failure is unknown, never a cached "no TTF" result.
                self._finish(repo, generation)

            try:
                self.service.resolve(font, ready, failed, ttf_only=True)
            except (OSError, TypeError, ValueError, KeyError):
                failed('Invalid font metadata')

    def _finish(self, repo, generation):
        if self.closed or generation != self.generation:
            return
        self.active.discard(repo)
        self.changed.emit()
        QTimer.singleShot(0, self.pump)

    def save(self):
        try:
            atomic_write(self.path, json.dumps(self.records, ensure_ascii=False).encode('utf-8'))
        except OSError:
            pass

    def stop(self):
        self.closed = True
        self.save_timer.stop()
        self.save()
        self.service.stop()
        self.queue.clear()
        self.active.clear()

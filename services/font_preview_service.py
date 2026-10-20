"""Create missing PNG previews on request, without retaining font binaries."""

import hashlib
import logging
import math

from PySide6.QtCore import QByteArray, QObject, QRunnable, QSaveFile, QIODevice, QThreadPool, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QRawFont

from core.online_fonts import FONT_LIMIT, is_font
from core.font_previews import (PREVIEW_TEXT, preview_image_path, preview_record,
                                save_generated_preview)
from services.online_font_service import OnlineFontService


class RenderSignals(QObject):
    ready = Signal(int, object)
    failed = Signal(int, str)


class RenderPreview(QRunnable):
    def __init__(self, generation, asset, data):
        super().__init__()
        self.generation, self.asset, self.data = generation, asset, data
        self.signals = RenderSignals()

    @staticmethod
    def draw_text(text, primary, fallback):
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.WindingFill)
        x = 0.0
        for character in text:
            font = primary if primary.supportsCharacter(ord(character)) else fallback
            indexes = font.glyphIndexesForString(character)
            if not indexes:
                continue
            glyph = font.pathForGlyph(indexes[0])
            path.addPath(glyph.translated(x, 0))
            advances = font.advancesForGlyphIndexes(indexes)
            if advances:
                x += advances[0].x()
        bounds = path.boundingRect()
        if bounds.isEmpty():
            raise ValueError('미리보기로 표시할 수 있는 글자가 없습니다.')
        width, height = math.ceil(bounds.width()) + 8, math.ceil(bounds.height()) + 8
        if width > 12000 or height > 4000:
            raise ValueError('폰트의 글자 크기 정보를 읽을 수 없습니다.')
        image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.fillPath(path.translated(4 - bounds.left(), 4 - bounds.top()), QColor('white'))
        finally:
            painter.end()
        return image

    @staticmethod
    def save_image(filename, image):
        path = preview_image_path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        target = QSaveFile(str(path))
        if not target.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError(target.errorString())
        if not image.save(target, 'PNG'):
            target.cancelWriting()
            raise OSError('미리보기 이미지를 저장하지 못했습니다.')
        if not target.commit():
            raise OSError(target.errorString())

    def run(self):
        try:
            # Raw font objects are created and used entirely in this worker thread.
            primary = QRawFont(QByteArray(self.data), 96, QFont.HintingPreference.PreferNoHinting)
            if not primary.isValid():
                raise ValueError('폰트 파일을 읽을 수 없습니다.')
            fallback_font = QFont('맑은 고딕')
            fallback_font.setPixelSize(96)
            fallback = QRawFont.fromFont(fallback_font)
            if not fallback.isValid():
                raise ValueError('기본 글꼴을 읽을 수 없습니다.')
            image = self.draw_text(PREVIEW_TEXT, primary, fallback)
            key = hashlib.sha256((self.asset.repo + '|' + self.asset.url).encode()).hexdigest()[:24]
            filename = 'user-' + key + '.png'
            missing = ''.join(dict.fromkeys(ch for ch in PREVIEW_TEXT
                                            if not ch.isspace() and not primary.supportsCharacter(ord(ch))))
            record = {'repo': self.asset.repo, 'url': self.asset.url, 'label': self.asset.label,
                      'image': filename, 'font_size': 96, 'width': image.width(),
                      'height': image.height(), 'missing': missing}
            if not any(primary.supportsCharacter(ord(ch)) for ch in PREVIEW_TEXT if '\uac00' <= ch <= '\ud7a3'):
                example = ''.join(ch for ch in 'ABC abc 123'
                                  if ch.isspace() or primary.supportsCharacter(ord(ch))).strip()
                if any(ch.isalnum() for ch in example):
                    record['example_image'] = 'user-' + key + '-example.png'
                    self.save_image(record['example_image'], self.draw_text(example, primary, fallback))
            self.save_image(filename, image)
            self.signals.ready.emit(self.generation, record)
        except Exception as error:
            logging.exception('Could not create preview for %s', self.asset.repo)
            self.signals.failed.emit(self.generation, str(error))
        finally:
            self.data = b''


class FontPreviewService(QObject):
    progress = Signal(int, int, str)
    preview_ready = Signal(str)
    finished = Signal(int, int, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = False
        self.generation = 0
        self.jobs = {}
        self.network = None
        self.fonts = []

    def start(self, fonts):
        if self.running or not fonts:
            return
        self.generation += 1
        self.running = True
        self.fonts = list(fonts)
        self.position = self.completed = self.failed_fonts = 0
        self.assets = []
        self.asset_index = 0
        self.family_failed = False
        if self.network is not None:
            self.network.deleteLater()
        self.network = OnlineFontService(self)
        self.next_family()

    def cancel(self):
        if not self.running:
            return
        self.running = False
        self.generation += 1
        self.network.stop()
        self.finished.emit(self.completed, self.failed_fonts, True)

    def schedule(self, callback):
        generation = self.generation
        QTimer.singleShot(0, lambda: callback() if self.running and generation == self.generation else None)

    def next_family(self):
        if not self.running:
            return
        if self.position >= len(self.fonts):
            self.running = False
            self.network.stop()
            self.finished.emit(self.completed, self.failed_fonts, False)
            return
        self.font = self.fonts[self.position]
        self.family_failed = False
        self.progress.emit(self.position, len(self.fonts), self.font.name)
        if not self.running:
            return
        generation = self.generation

        def ready(assets):
            if not self.running or generation != self.generation:
                return
            self.assets = assets
            self.asset_index = 0
            self.next_asset()

        def failed(message):
            if self.running and generation == self.generation:
                logging.info('Could not resolve preview font %s: %s', self.font.repo, message)
                self.family_failed = True
                self.finish_family()
        try:
            self.network.resolve(self.font, ready, failed)
        except Exception as error:
            failed(str(error))

    def next_asset(self):
        if not self.running:
            return
        if self.asset_index >= len(self.assets):
            self.finish_family()
            return
        asset = self.assets[self.asset_index]
        self.progress.emit(self.position, len(self.fonts),
                           f'{self.font.name} · {asset.label} ({self.asset_index + 1}/{len(self.assets)})')
        if not self.running:
            return
        if preview_record(asset.repo, asset.url) is not None:
            self.asset_index += 1
            self.schedule(self.next_asset)
            return
        generation = self.generation

        def ready(data):
            if not self.running or generation != self.generation:
                return
            job = RenderPreview(generation, asset, data)
            job.signals.ready.connect(self.rendered)
            job.signals.failed.connect(self.render_failed)
            self.jobs[generation] = job
            QThreadPool.globalInstance().start(job)

        def failed(message):
            if self.running and generation == self.generation:
                self.render_failed(generation, message)
        try:
            # A permanent font downloaded earlier can also supply the drawing data.
            if asset.saved_path.is_file():
                with asset.saved_path.open('rb') as stream:
                    data = stream.read(FONT_LIMIT + 1)
                if len(data) <= FONT_LIMIT and is_font(data):
                    ready(data)
                    return
            self.network.fetch_asset_data(asset, ready, failed)
        except Exception as error:
            failed(str(error))

    @Slot(int, object)
    def rendered(self, generation, record):
        self.jobs.pop(generation, None)
        if not self.running or generation != self.generation:
            return
        try:
            save_generated_preview(self.font, record, complete=False)
            self.preview_ready.emit(self.font.repo)
        except Exception as error:
            self.render_failed(generation, str(error))
            return
        self.asset_index += 1
        self.schedule(self.next_asset)

    @Slot(int, str)
    def render_failed(self, generation, message):
        self.jobs.pop(generation, None)
        if not self.running or generation != self.generation:
            return
        logging.warning('Preview generation failed for %s: %s', self.font.repo, message)
        self.family_failed = True
        self.asset_index += 1
        self.schedule(self.next_asset)

    def finish_family(self):
        if not self.family_failed:
            try:
                save_generated_preview(self.font, complete=True)
            except OSError:
                logging.warning('Could not save preview completion for %s', self.font.repo, exc_info=True)
                self.family_failed = True
        if self.family_failed:
            self.failed_fonts += 1
        else:
            self.completed += 1
        self.position += 1
        self.schedule(self.next_family)

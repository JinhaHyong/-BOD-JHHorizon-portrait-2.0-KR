"""Choose distinct recent text settings by their first portrait thumbnail."""

from collections import deque
from pathlib import Path
import logging

from PySide6.QtCore import QIODevice, QSaveFile, QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QImage, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QListView, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout)

from core.text_presets import decode_layers
from ui.font_registry import set_layer_font_file
from ui.styles import BUTTON_STYLE
from ui.text_canvas import render_portrait


def source_matches(entry, path):
    try:
        stat = Path(path).stat()
        return entry.get('source_stamp') == [stat.st_size, stat.st_mtime_ns]
    except OSError:
        return False


def save_history_preview(store, entry, base, *, layers=None):
    """Freeze the representative photo, rather than replacing it on later uses."""
    path = store.preview_path(entry)
    if path.is_file():
        return
    if layers is None:
        layers = decode_layers(entry.get('layers'))
        for layer in layers:
            if layer.font_file and Path(layer.font_file).is_file():
                try:
                    set_layer_font_file(layer, layer.font_file)
                except ValueError:
                    pass
    image = render_portrait(base, layers).scaled(
        360, 464, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    path.parent.mkdir(parents=True, exist_ok=True)
    target = QSaveFile(str(path))
    if not target.open(QIODevice.OpenModeFlag.WriteOnly):
        raise OSError(target.errorString())
    if not image.save(target, 'PNG'):
        target.cancelWriting()
        raise OSError('Could not save the preset thumbnail')
    if not target.commit():
        raise OSError(target.errorString())


class PresetHistoryDialog(QDialog):
    def __init__(self, context, store, parent=None):
        super().__init__(parent)
        self.context, self.store = context, store
        self.selected_entry = None
        self.closing = False
        self.setWindowTitle(self.word('preset_history_title'))
        self.resize(720, 620)
        self.setMinimumSize(460, 390)
        layout = QVBoxLayout(self)
        hint = QLabel(self.word('preset_history_hint'))
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)
        self.list = QListWidget()
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setMovement(QListView.Movement.Static)
        self.list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list.setIconSize(QSize(150, 194))
        self.list.setGridSize(QSize(180, 232))
        self.list.setSpacing(8)
        self.list.setWordWrap(False)
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setStyleSheet('''
            QListWidget { background:palette(base); color:palette(text); border:1px solid palette(mid); }
            QListWidget::item { border:2px solid transparent; border-radius:6px; padding:4px; }
            QListWidget::item:hover { background:palette(alternate-base); }
            QListWidget::item:selected { background:palette(highlight); border-color:palette(link); color:palette(highlighted-text); }
        ''')
        self.list.itemDoubleClicked.connect(lambda _item: self.load_selected())
        layout.addWidget(self.list, 1)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.load_button = QPushButton(self.word('preset_history_load'))
        self.load_button.setStyleSheet(BUTTON_STYLE)
        self.load_button.clicked.connect(self.load_selected)
        buttons.addWidget(self.load_button)
        cancel = QPushButton(self.word('cancel'))
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)
        placeholder = self.placeholder()
        entries = self.store.history()
        entries = [value for _index, value in sorted(enumerate(entries),
                   key=lambda pair: (pair[1].get('last_used_at', ''), pair[0]), reverse=True)]
        self.pending = deque()
        for entry in entries:
            title = Path(entry['source_path']).name if entry['source_path'] else self.word('load_preset')
            item = QListWidgetItem(QIcon(placeholder), title)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            item.setToolTip(title + '\n' + self.word('preset_history_boxes').format(count=len(entry['layers'])))
            self.list.addItem(item)
            self.pending.append((item, entry))
        self.load_button.setEnabled(bool(entries))
        if entries:
            self.list.setCurrentRow(0)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.load_next_preview)
        self.timer.start(0)

    def word(self, key):
        return self.context.translations.text('text_editor', key)

    def placeholder(self):
        image = QPixmap(150, 194)
        image.fill(self.palette().color(QPalette.ColorRole.AlternateBase))
        painter = QPainter(image)
        painter.setPen(self.palette().color(QPalette.ColorRole.PlaceholderText))
        painter.drawText(image.rect(), Qt.AlignmentFlag.AlignCenter, self.word('preset_history_no_preview'))
        painter.end()
        return image

    def load_next_preview(self):
        if self.closing or not self.pending:
            return
        item, entry = self.pending.popleft()
        try:
            image = QImage(str(self.store.preview_path(entry)))
            path = entry['source_path']
            if image.isNull() and path and source_matches(entry, path):
                source = self.context.portraits.read_image(path)
                raw = source.tobytes()
                base = QImage(raw, source.width, source.height, source.width * 3,
                              QImage.Format.Format_RGB888).copy()
                save_history_preview(self.store, entry, base)
                image = QImage(str(self.store.preview_path(entry)))
            if not image.isNull():
                item.setIcon(QIcon(QPixmap.fromImage(image)))
        except (OSError, ValueError):
            logging.info('Could not prepare preset thumbnail', exc_info=True)
        if self.pending:
            self.timer.start(0)

    def load_selected(self):
        item = self.list.currentItem()
        if item is not None:
            self.selected_entry = item.data(Qt.ItemDataRole.UserRole)
            self.accept()

    def done(self, result):
        self.closing = True
        self.timer.stop()
        self.pending.clear()
        super().done(result)

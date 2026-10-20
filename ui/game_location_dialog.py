"""Choose a client folder or resolve its desktop shortcut on a worker thread."""

import logging
from threading import Event

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel,
                               QProgressBar, QPushButton, QVBoxLayout)

from services.game_location import GameLocationError, find_game_roots
from ui.common import WindowSupport
from ui.desktop_shortcut_dialog import DesktopShortcutDialog
from ui.styles import BUTTON_STYLE


class LocationSignals(QObject):
    finished = Signal(object)


class FindGameLocation(QRunnable):
    def __init__(self, selected):
        super().__init__()
        self.selected = selected
        self.cancelled = Event()
        self.signals = LocationSignals()

    def run(self):
        try:
            result = {'roots': find_game_roots(self.selected)}
        except GameLocationError as error:
            result = {'error': error.code}
        except Exception:
            logging.warning('Could not read the selected game location', exc_info=True)
            result = {'error': 'not_found'}
        self.signals.finished.emit(result)


class GameLocationDialog(WindowSupport, QDialog):
    def __init__(self, context, parent=None, *, missing=True):
        super().__init__(parent)
        self.context = context
        self.game_root = None
        self.task = None
        self.setWindowTitle(self.word('select_game'))
        self.setMinimumWidth(400)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        hint = QLabel(self.word('location_hint' if missing else 'location_change_hint'))
        hint.setTextFormat(Qt.TextFormat.PlainText)
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)
        self.shortcut_button = QPushButton(self.word('location_shortcut'))
        self.shortcut_button.setStyleSheet(BUTTON_STYLE)
        self.shortcut_button.clicked.connect(self.choose_shortcut)
        layout.addWidget(self.shortcut_button)
        self.folder_button = QPushButton(self.word('location_folder'))
        self.folder_button.clicked.connect(self.choose_folder)
        layout.addWidget(self.folder_button)
        self.status = QLabel(self.word('location_searching'))
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.hide()
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        row = QHBoxLayout()
        row.addStretch()
        self.cancel_button = QPushButton(self.word('location_cancel'))
        self.cancel_button.clicked.connect(self.reject)
        row.addWidget(self.cancel_button)
        layout.addLayout(row)
        for button in (self.shortcut_button, self.folder_button, self.cancel_button):
            button.setAutoDefault(False)

    def word(self, key):
        return self.text('font_window', key)

    def choose_shortcut(self):
        dialog = DesktopShortcutDialog(self.context, self)
        result = dialog.exec()
        selected = dialog.selected_path
        dialog.deleteLater()
        if result == QDialog.DialogCode.Accepted and selected is not None:
            self.start_search(selected)

    def choose_folder(self):
        selected = QFileDialog.getExistingDirectory(self, self.word('select_game'))
        if selected:
            self.start_search(selected)

    def set_busy(self, busy):
        self.shortcut_button.setEnabled(not busy)
        self.folder_button.setEnabled(not busy)
        self.cancel_button.setEnabled(True)
        self.status.setVisible(busy)
        self.progress.setVisible(busy)

    def start_search(self, selected):
        if self.task is not None:
            return
        self.set_busy(True)
        self.task = FindGameLocation(selected)
        self.task.signals.finished.connect(self.location_found)
        QThreadPool.globalInstance().start(self.task)

    @Slot(object)
    def location_found(self, result):
        cancelled = self.task is not None and self.task.cancelled.is_set()
        self.task = None
        self.set_busy(False)
        if cancelled:
            super().reject()
            return
        if result.get('error'):
            self.show_warning(self.word('location_error.' + result['error']))
            return
        roots = result.get('roots', [])
        if not roots:
            self.show_warning(self.word('location_error.not_found'))
            return
        if len(roots) > 1:
            choice, accepted = QInputDialog.getItem(
                self, self.word('select_game'), self.word('location_multiple'),
                [str(path) for path in roots], 0, False)
            if not accepted:
                return
            self.game_root = next(path for path in roots if str(path) == choice)
        else:
            self.game_root = roots[0]
        self.accept()

    def reject(self):
        if self.task is not None:
            self.task.cancelled.set()
            self.cancel_button.setEnabled(False)
            return
        super().reject()

    def closeEvent(self, event):
        if self.task is not None:
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)

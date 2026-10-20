"""Choose portraits and apply the editor's settings in one saved transaction."""

from collections import Counter

from PySide6.QtCore import QItemSelection, QItemSelectionModel, QSignalBlocker, QThreadPool, Qt, Slot
from PySide6.QtGui import QColor, QPalette, QPen
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QLabel, QMessageBox,
                               QProgressBar, QPushButton, QStyle, QVBoxLayout)

from core.text_presets import DRAFTS_KEY, decode_layers
from services.portrait_batch import PortraitBatchTask
from ui.common import WindowSupport
from ui.ime_search import ImeSearchLineEdit
from ui.portrait_grid import PortraitDelegate, PortraitGrid, PortraitGridView
from ui.styles import BUTTON_STYLE


class CheckedPortraitDelegate(PortraitDelegate):
    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if not option.state & QStyle.StateFlag.State_Selected:
            return
        painter.save()
        try:
            x, y = option.rect.x() + 85, option.rect.y() + 17
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(option.palette.color(QPalette.ColorRole.Highlight))
            painter.drawEllipse(x - 10, y - 10, 20, 20)
            painter.setPen(QPen(QColor('white'), 2))
            painter.drawLine(x - 5, y, x - 1, y + 4)
            painter.drawLine(x - 1, y + 4, x + 6, y - 4)
        finally:
            painter.restore()


class PortraitBatchDialog(WindowSupport, QDialog):
    def __init__(self, context, tiles, loader, source, on_commit, parent=None):
        super().__init__(parent)
        self.context, self.loader = context, loader
        self.source, self.on_commit = source, on_commit
        self.selected_paths = set()
        self.busy = False
        self.task = None
        self.applied_count = self.skipped_count = 0
        self.setWindowTitle(self.word('batch_title'))
        self.resize(520, 650)
        self.setMinimumSize(460, 430)
        layout = QVBoxLayout(self)
        hint = QLabel(self.word('batch_hint'))
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)
        self.search = ImeSearchLineEdit()
        self.search.setPlaceholderText(self.text('portrait_window', 'search_placeholder'))
        self.search.query_changed.connect(self.filter_portraits)
        layout.addWidget(self.search)
        actions = QHBoxLayout()
        self.all_button = QPushButton(self.word('batch_select_all'))
        self.all_button.clicked.connect(self.select_visible)
        actions.addWidget(self.all_button)
        self.clear_button = QPushButton(self.word('batch_clear'))
        self.clear_button.clicked.connect(self.clear_selection)
        actions.addWidget(self.clear_button)
        actions.addStretch()
        self.count_label = QLabel()
        actions.addWidget(self.count_label)
        layout.addLayout(actions)
        self.view = PortraitGridView()
        self.grid = PortraitGrid(self.view)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.view.setItemDelegate(CheckedPortraitDelegate(self.view))
        self.grid.set_records([{'path': tile.file_path, 'stamp': tile.stamp} for tile in tiles.tiles])
        for tile in tiles.tiles:
            self.grid.by_path[tile.file_path].pixmap = tile.pixmap
        self.view.selectionModel().selectionChanged.connect(self.selection_changed)
        self.grid.priority_changed.connect(self.prioritize)
        self.loader.thumbnails_ready.connect(self.receive_thumbnails)
        self.loader.invalid.connect(self.remove_invalid)
        layout.addWidget(self.view, 1)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        footer = QHBoxLayout()
        footer.addStretch()
        self.apply_button = QPushButton(self.word('batch_apply'))
        self.apply_button.setStyleSheet(BUTTON_STYLE)
        self.apply_button.clicked.connect(self.start_apply)
        footer.addWidget(self.apply_button)
        self.cancel_button = QPushButton(self.word('cancel'))
        self.cancel_button.clicked.connect(self.reject)
        footer.addWidget(self.cancel_button)
        layout.addLayout(footer)
        for button in (self.all_button, self.clear_button, self.apply_button, self.cancel_button):
            button.setAutoDefault(False)
        self.update_count()

    def word(self, key):
        return self.text('text_editor', key)

    def prioritize(self, paths):
        self.loader.prioritize('new', paths)

    @Slot(str, object)
    def receive_thumbnails(self, side, payloads):
        if side == 'new':
            self.grid.update_images(payloads)

    @Slot(str, object)
    def remove_invalid(self, side, path):
        if side != 'new' or self.busy:
            return
        self.selected_paths.discard(path)
        with QSignalBlocker(self.view.selectionModel()):
            self.grid.remove(path)
            self.restore_selection()
        self.update_count()

    def selection_changed(self, *_args):
        self.selected_paths.difference_update(self.grid.model.rows)
        self.selected_paths.update(index.data(Qt.ItemDataRole.UserRole).file_path
                                   for index in self.view.selectionModel().selectedRows())
        self.update_count()

    def restore_selection(self):
        selection = QItemSelection()
        for path in self.selected_paths:
            row = self.grid.model.rows.get(path)
            if row is not None:
                index = self.grid.model.index(row)
                selection.select(index, index)
        self.view.selectionModel().select(selection, QItemSelectionModel.SelectionFlag.ClearAndSelect)

    def filter_portraits(self, *_args):
        with QSignalBlocker(self.view.selectionModel()):
            self.grid.filter(self.search.search_text(), None)
            self.restore_selection()
        self.view.verticalScrollBar().setValue(0)
        self.update_count()

    def select_visible(self):
        self.selected_paths.update(self.grid.model.rows)
        with QSignalBlocker(self.view.selectionModel()):
            self.restore_selection()
        self.update_count()

    def clear_selection(self):
        self.selected_paths.clear()
        with QSignalBlocker(self.view.selectionModel()):
            self.view.clearSelection()
        self.update_count()

    def update_count(self):
        self.count_label.setText(self.word('batch_selected').format(count=len(self.selected_paths)))
        self.apply_button.setEnabled(bool(self.selected_paths) and not self.busy)
        self.all_button.setEnabled(bool(self.grid.visible) and not self.busy)
        self.clear_button.setEnabled(bool(self.selected_paths) and not self.busy)

    def set_busy(self, busy):
        self.busy = busy
        self.search.setEnabled(not busy)
        self.view.setEnabled(not busy)
        self.cancel_button.setEnabled(True)
        self.progress.setVisible(busy)
        self.update_count()

    def start_apply(self):
        if self.busy or not self.selected_paths:
            return
        paths = [tile.file_path for tile in self.grid.tiles if tile.file_path in self.selected_paths]
        self.set_busy(True)
        self.progress.setRange(0, len(paths))
        self.progress.setValue(0)
        self.task = PortraitBatchTask(paths, self.source, self.context.settings.get(DRAFTS_KEY, {}),
                                      self.word('source_changed'))
        self.task.signals.progress.connect(self.update_progress)
        self.task.signals.finished.connect(self.prepared)
        QThreadPool.globalInstance().start(self.task)

    @Slot(int, int)
    def update_progress(self, done, total):
        self.progress.setRange(0, total)
        self.progress.setValue(done)

    def confirm_overwrite(self, records):
        count = len(decode_layers(self.source['layers']))
        different = [record for record in records if record['previous_count'] != count]
        if not different:
            return True
        message = QMessageBox(self)
        message.setIcon(QMessageBox.Icon.Warning)
        message.setWindowTitle(self.word('batch_overwrite_title'))
        message.setText(self.word('batch_overwrite').format(count=len(different)))
        groups = Counter(record['previous_count'] for record in different)
        message.setDetailedText('\n'.join(self.word('batch_count_detail').format(
            before=before, after=count, count=amount) for before, amount in sorted(groups.items())))
        overwrite = message.addButton(self.word('batch_overwrite_button'), QMessageBox.ButtonRole.AcceptRole)
        cancel = message.addButton(self.word('cancel'), QMessageBox.ButtonRole.RejectRole)
        message.setDefaultButton(cancel)
        message.exec()
        accepted = message.clickedButton() is overwrite
        message.deleteLater()
        return accepted

    @Slot(object)
    def prepared(self, result):
        cancelled = self.task is not None and self.task.cancelled.is_set()
        self.task = None
        if cancelled or result.get('cancelled'):
            self.busy = False
            super().reject()
            return
        self.set_busy(False)
        if result.get('error'):
            self.show_warning(self.word('batch_error') + '\n' + result['error'])
            return
        records = result.get('records', [])
        if not records:
            self.show_warning(self.word('batch_no_readable'))
            return
        if not self.confirm_overwrite(records):
            return
        try:
            self.applied_count, changed = self.on_commit(records)
            self.skipped_count = len(result.get('skipped', [])) + changed
        except (OSError, ValueError) as error:
            self.show_warning(self.word('batch_error') + '\n' + str(error))
            return
        self.accept()

    def reject(self):
        if self.busy and self.task is not None:
            self.task.cancelled.set()
            self.cancel_button.setEnabled(False)
            return
        super().reject()

    def closeEvent(self, event):
        if self.busy:
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)

"""Merge personal and public desktop shortcuts, retaining their actual link paths."""

import os
from pathlib import Path

from PySide6.QtCore import QSize, QStandardPaths, Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton, QStyle, QVBoxLayout)

from ui.common import WindowSupport
from ui.ime_search import ImeSearchLineEdit
from ui.styles import BUTTON_STYLE


def desktop_shortcuts():
    personal = QStandardPaths.standardLocations(QStandardPaths.StandardLocation.DesktopLocation)
    folders = [(Path(value), 'desktop_personal') for value in personal if value]
    public = Path(os.environ.get('PUBLIC', str(Path.home().parent / 'Public'))) / 'Desktop'
    folders.append((public, 'desktop_public'))
    records = {}
    for folder, scope in folders:
        try:
            for path in folder.iterdir():
                if path.suffix.lower() in ('.lnk', '.url') and path.is_file():
                    records[os.path.normcase(str(path.absolute()))] = (path, scope)
        except OSError:
            continue

    def order(record):
        name = record[0].stem.casefold().replace(' ', '')
        game = '검은사막' in name or 'blackdesert' in name
        return not game, name, str(record[0]).casefold()
    return sorted(records.values(), key=order)


class DesktopShortcutDialog(WindowSupport, QDialog):
    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.context = context
        self.selected_path = None
        self.setWindowTitle(self.word('location_shortcut'))
        self.resize(530, 470)
        self.setMinimumSize(420, 320)
        layout = QVBoxLayout(self)
        hint = QLabel(self.word('desktop_hint'))
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)
        self.search = ImeSearchLineEdit()
        self.search.setPlaceholderText(self.word('desktop_search'))
        layout.addWidget(self.search)
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.setIconSize(QSize(24, 24))
        self.list.setUniformItemSizes(True)
        self.list.setSpacing(3)
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileLinkIcon)
        for path, scope in desktop_shortcuts():
            item = QListWidgetItem(icon, f'{path.stem}  ·  {self.word(scope)}')
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(str(path))
            self.list.addItem(item)
        self.list.itemActivated.connect(self.select_shortcut)
        layout.addWidget(self.list, 1)
        empty = QLabel(self.word('desktop_empty'))
        empty.setWordWrap(True)
        empty.setVisible(self.list.count() == 0)
        layout.addWidget(empty)
        row = QHBoxLayout()
        self.browse_button = QPushButton(self.word('desktop_browse'))
        self.browse_button.clicked.connect(self.browse)
        row.addWidget(self.browse_button)
        row.addStretch()
        self.select_button = QPushButton(self.word('desktop_select'))
        self.select_button.setStyleSheet(BUTTON_STYLE)
        self.select_button.setEnabled(False)
        self.select_button.clicked.connect(self.select_shortcut)
        row.addWidget(self.select_button)
        cancel = QPushButton(self.word('location_cancel'))
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        layout.addLayout(row)
        for button in (self.browse_button, self.select_button, cancel):
            button.setAutoDefault(False)
        self.list.currentItemChanged.connect(self.selection_changed)
        self.search.query_changed.connect(self.filter_shortcuts)

    def word(self, key):
        return self.text('font_window', key)

    def selection_changed(self, current, _previous=None):
        self.select_button.setEnabled(current is not None and not current.isHidden())

    def filter_shortcuts(self, *_args):
        query = self.search.search_text().casefold()
        for row in range(self.list.count()):
            item = self.list.item(row)
            item.setHidden(query not in Path(item.data(Qt.ItemDataRole.UserRole)).stem.casefold())
        current = self.list.currentItem()
        if current is not None and current.isHidden():
            self.list.setCurrentItem(None)
        self.selection_changed(self.list.currentItem())

    def select_shortcut(self, *_args):
        item = self.list.currentItem()
        if item is None or item.isHidden():
            return
        self.selected_path = Path(item.data(Qt.ItemDataRole.UserRole))
        self.accept()

    def browse(self):
        desktop = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
        selected, _filter = QFileDialog.getOpenFileName(
            self, self.word('location_shortcut'), desktop, self.word('location_file_filter'),
            options=QFileDialog.Option.DontResolveSymlinks)
        if selected:
            self.selected_path = Path(selected)
            self.accept()

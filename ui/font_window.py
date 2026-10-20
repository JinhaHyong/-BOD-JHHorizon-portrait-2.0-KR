"""Font manager with local/online tabs, shared previews and a persistent apply bar."""

from pathlib import Path

from PySide6.QtCore import QSignalBlocker, QTimer, Qt
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QSizePolicy, QSplitter, QTabWidget, QPushButton, QVBoxLayout, QWidget,
)

from core.paths import default_font_folder, resource_path, system_font_folders
from core.online_fonts import downloaded_font_label, font_storage
from ui.common import WindowSupport, center_window
from ui.font_window_styles import MANAGER_STYLE, LIST_STYLE, PRIMARY_STYLE, SECONDARY_STYLE
from ui.game_location_dialog import GameLocationDialog
from ui.ime_search import ImeSearchLineEdit
from ui.local_font_preview import LocalFontPreview
from services.game_location import is_game_root
from ui.font_registry import font_from_file


class PathLabel(QLabel):
    def set_path(self, text):
        self.full_text = text
        self.setToolTip(text)
        self.refresh_text()

    def refresh_text(self):
        self.setText(self.fontMetrics().elidedText(getattr(self, 'full_text', ''),
                                                 Qt.TextElideMode.ElideMiddle, max(1, self.width())))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh_text()


class FontWindow(WindowSupport, QWidget):
    def __init__(self, context, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.context = context
        self.font_path = Path(context.settings.get('font_folder', str(default_font_folder())))
        self.current_font_path = self.local_font_path = None
        self.preview_qfont = None
        self.preview_font_id = -1
        self.online_panel = None
        self.local_dirty = False
        self.local_known_paths = set()
        extra = context.settings.get('extra_font_folders', [])
        self.custom_font_dirs = system_font_folders() + [Path(p) for p in extra if isinstance(p, str)]
        self.custom_font_files = [Path(p) for p in context.settings.get('extra_font_files', [])
                                  if isinstance(p, str)]
        if font_storage() not in self.custom_font_dirs:
            self.custom_font_dirs.append(font_storage())
        self.setWindowIcon(QIcon(str(resource_path('아이콘.ico'))))
        self.setObjectName('fontManager')
        self.setStyleSheet(MANAGER_STYLE)
        self.build_ui()
        context.translations.changed.connect(self.update_texts)
        self.update_texts()
        self.load_fonts()
        self.resize(1040, 740)
        self.setMinimumSize(860, 620)
        center_window(self)

    def word(self, key):
        return self.text('font_window', key)

    @staticmethod
    def panel():
        frame = QFrame()
        frame.setObjectName('fontPanel')
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        return frame, layout

    def build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        self.heading = QLabel()
        self.heading.setObjectName('fontHeading')
        layout.addWidget(self.heading)
        self.subtitle = QLabel()
        self.subtitle.setObjectName('fontMuted')
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.subtitle)
        self.tabs = QTabWidget()
        self.tabs.setObjectName('fontTabs')
        self.tabs.addTab(self.build_local_tab(), '')
        self.online_placeholder = QWidget()
        self.tabs.addTab(self.online_placeholder, '')
        self.tabs.currentChanged.connect(self.tab_changed)
        layout.addWidget(self.tabs, 1)
        footer, footer_layout = self.panel()
        footer_layout.setContentsMargins(14, 10, 14, 10)
        row = QHBoxLayout()
        location = QVBoxLayout()
        location.setSpacing(5)
        self.location_title = QLabel()
        self.location_title.setObjectName('fontSection')
        location.addWidget(self.location_title)
        self.location_path = PathLabel()
        self.location_path.setMinimumWidth(0)
        self.location_path.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        location.addWidget(self.location_path)
        self.location_status = QLabel()
        self.location_status.setObjectName('fontMuted')
        location.addWidget(self.location_status)
        row.addLayout(location, 1)
        self.change_location_button = QPushButton()
        self.change_location_button.setStyleSheet(SECONDARY_STYLE)
        self.change_location_button.clicked.connect(self.change_game_location)
        row.addWidget(self.change_location_button)
        row.addSpacing(14)
        apply_area = QVBoxLayout()
        apply_area.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.apply_button = QPushButton()
        self.apply_button.setMinimumSize(150, 40)
        self.apply_button.setStyleSheet(PRIMARY_STYLE)
        self.apply_button.clicked.connect(self.apply_font)
        apply_area.addWidget(self.apply_button)
        row.addLayout(apply_area)
        footer_layout.addLayout(row)
        layout.addWidget(footer)

    def build_local_tab(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 10, 0, 0)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        left, left_layout = self.panel()
        left.setMinimumWidth(260)
        header = QHBoxLayout()
        self.title = QLabel()
        self.title.setObjectName('fontSection')
        header.addWidget(self.title)
        header.addStretch()
        self.local_count = QLabel()
        self.local_count.setObjectName('fontMuted')
        header.addWidget(self.local_count)
        left_layout.addLayout(header)
        self.search_input = ImeSearchLineEdit()
        self.search_input.query_changed.connect(self.filter_fonts)
        left_layout.addWidget(self.search_input)
        self.font_list = QListWidget()
        self.font_list.setStyleSheet(LIST_STYLE)
        self.font_list.setUniformItemSizes(True)
        self.font_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.font_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.font_list.currentItemChanged.connect(self.on_font_selected)
        left_layout.addWidget(self.font_list, 1)
        buttons = QHBoxLayout()
        self.add_path_button = QPushButton()
        self.add_path_button.setStyleSheet(SECONDARY_STYLE)
        self.add_path_button.clicked.connect(self.add_font_files)
        buttons.addWidget(self.add_path_button)
        self.refresh_btn = QPushButton()
        self.refresh_btn.setStyleSheet(SECONDARY_STYLE)
        self.refresh_btn.clicked.connect(self.refresh_font_list)
        buttons.addWidget(self.refresh_btn)
        left_layout.addLayout(buttons)
        split.addWidget(left)
        right, right_layout = self.panel()
        right.setMinimumWidth(350)
        self.preview_title = QLabel()
        self.preview_title.setObjectName('fontSection')
        right_layout.addWidget(self.preview_title)
        self.font_name = QLabel()
        self.font_name.setTextFormat(Qt.TextFormat.PlainText)
        self.font_name.setWordWrap(True)
        self.font_name.setObjectName('fontName')
        right_layout.addWidget(self.font_name)
        self.font_detail = QLabel()
        self.font_detail.setObjectName('fontMuted')
        right_layout.addWidget(self.font_detail)
        self.sample_title = QLabel()
        self.sample_title.setObjectName('fontMuted')
        right_layout.addWidget(self.sample_title)
        self.preview_input = ImeSearchLineEdit()
        self.preview_input.setMaxLength(200)
        self.preview_input.setText('검은사막 너무 좋아!')
        self.preview_input.query_changed.connect(self.update_preview)
        right_layout.addWidget(self.preview_input)
        self.preview_label = LocalFontPreview(language=self.context.translations.language)
        right_layout.addWidget(self.preview_label, 1)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([310, 680])
        layout.addWidget(split)
        return container

    def load_fonts(self):
        selected = self.local_font_path
        restored = None
        try:
            paths = self.context.fonts.list_fonts(self.custom_font_dirs, files=self.custom_font_files)
            with QSignalBlocker(self.font_list):
                self.font_list.clear()
                for path in paths:
                    item = QListWidgetItem(downloaded_font_label(path))
                    item.setData(Qt.ItemDataRole.UserRole, str(path))
                    item.setToolTip(str(path))
                    self.font_list.addItem(item)
                    if path == selected:
                        restored = item
                if restored is not None:
                    self.font_list.setCurrentItem(restored)
            self.local_known_paths = {str(path) for path in paths}
            self.local_dirty = False
            self.filter_fonts()
            self.on_font_selected(self.font_list.currentItem())
        except OSError as error:
            self.show_warning(f"{self.word('error_msg.load')}\n{error}")

    def filter_fonts(self, *_args):
        query = self.search_input.search_text().casefold()
        count = 0
        for index in range(self.font_list.count()):
            item = self.font_list.item(index)
            hidden = query not in item.text().casefold()
            item.setHidden(hidden)
            count += not hidden
        current = self.font_list.currentItem()
        if current is not None and current.isHidden():
            self.font_list.setCurrentItem(None)
        self.local_count.setText(self.word('ui_count').format(count=count))

    def on_font_selected(self, current, _previous=None):
        self.local_font_path = None
        if current is not None:
            path = Path(current.data(Qt.ItemDataRole.UserRole))
            if self.preview_font(path):
                self.local_font_path = path
        else:
            self.clear_preview_font()
        if self.tabs.currentIndex() == 0:
            self.current_font_path = self.local_font_path
        self.update_local_labels()
        self.update_apply_state()

    def clear_preview_font(self):
        self.preview_qfont = None
        self.update_preview()
        if self.preview_font_id >= 0:
            QFontDatabase.removeApplicationFont(self.preview_font_id)
            self.preview_font_id = -1

    def preview_font(self, path):
        self.clear_preview_font()
        font_id = QFontDatabase.addApplicationFont(str(path))
        families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
        if not families:
            if font_id >= 0:
                QFontDatabase.removeApplicationFont(font_id)
            self.show_warning(self.word('error_msg.preview'))
            return False
        try:
            self.preview_qfont = font_from_file(path)
        except ValueError:
            QFontDatabase.removeApplicationFont(font_id)
            self.show_warning(self.word('error_msg.preview'))
            return False
        self.preview_font_id = font_id
        self.update_preview()
        return True

    def update_preview(self, *_args):
        self.preview_label.set_preview(self.preview_input.search_text() or '검은사막 너무 좋아!', self.preview_qfont)

    def update_local_labels(self):
        item = self.font_list.currentItem()
        self.font_name.setText(item.text() if item is not None and self.local_font_path else self.word('ui_choose'))
        self.font_name.setToolTip(str(self.local_font_path) if self.local_font_path else '')
        key = 'ui_downloaded' if self.local_font_path and self.local_font_path.parent == font_storage() else 'ui_local_file'
        self.font_detail.setText(self.word(key) if self.local_font_path else '')

    def refresh_font_list(self):
        self.load_fonts()

    def add_font_files(self):
        filenames, _filter = QFileDialog.getOpenFileNames(
            self, self.word('add_font'), '', self.word('font_file_filter'))
        if not filenames:
            return
        selected = [Path(name) for name in filenames]
        valid = self.context.fonts.list_fonts([], files=selected)
        if valid:
            known = {str(path.resolve()).casefold() for path in self.custom_font_files}
            for path in valid:
                key = str(path.resolve()).casefold()
                if key not in known:
                    self.custom_font_files.append(path)
                    known.add(key)
            self.remember(extra_font_files=[str(path) for path in self.custom_font_files])
            self.local_font_path = valid[0]
            self.search_input.clear()
            self.load_fonts()
            if self.font_list.currentItem() is not None:
                self.font_list.scrollToItem(self.font_list.currentItem())
        if len(valid) < len(selected):
            self.show_warning(self.word('invalid_font_files'))

    def open_online_fonts(self):
        self.tabs.setCurrentIndex(1)

    def tab_changed(self, index):
        if index == 1:
            if self.online_panel is None:
                from ui.online_font_dialog import OnlineFontPanel
                self.online_panel = OnlineFontPanel(self.context, self, embedded=True, ttf_only=True)
                self.online_panel.font_ready.connect(self.online_selection_changed)
                with QSignalBlocker(self.tabs):
                    old = self.tabs.widget(1)
                    self.tabs.removeTab(1)
                    self.tabs.insertTab(1, self.online_panel, self.word('ui_online_tab'))
                    self.tabs.setCurrentIndex(1)
                    old.deleteLater()
            self.current_font_path = self.online_panel.available_path()
        else:
            if self.local_dirty:
                self.load_fonts()
            self.current_font_path = self.local_font_path
        self.update_apply_state()

    def online_selection_changed(self, path):
        if self.online_panel is None:
            return
        if path is not None and str(path) not in self.local_known_paths:
            self.local_dirty = True
            if self.tabs.currentIndex() == 0:
                QTimer.singleShot(0, self.refresh_downloaded_fonts)
        if self.tabs.currentIndex() == 1:
            self.current_font_path = path
            self.update_apply_state()

    def refresh_downloaded_fonts(self):
        if self.isVisible() and self.tabs.currentIndex() == 0 and self.local_dirty:
            self.load_fonts()

    def update_apply_state(self):
        ready = self.current_font_path is not None
        self.apply_button.setEnabled(ready)
        self.apply_button.setToolTip(str(self.current_font_path) if ready else '')

    def update_location(self):
        root = self.font_path.parent.parent
        self.location_path.set_path(str(root))
        self.location_status.setText(self.word('ui_location_ready' if is_game_root(root) else 'ui_location_missing'))

    def choose_game_location(self, missing=True):
        dialog = GameLocationDialog(self.context, self, missing=missing)
        result = dialog.exec()
        root = dialog.game_root
        dialog.deleteLater()
        if result != QDialog.DialogCode.Accepted or root is None:
            return False
        if not is_game_root(root):
            self.show_warning(self.word('location_error.not_found'))
            return False
        self.font_path = root / 'prestringtable' / 'font'
        self.update_location()
        return True

    def change_game_location(self):
        if self.choose_game_location(missing=False):
            self.remember(font_folder=str(self.font_path))

    def apply_font(self):
        if self.current_font_path is None:
            self.show_warning(self.word('error_msg.select'))
            return
        source = self.current_font_path
        if not is_game_root(self.font_path.parent.parent) and not self.choose_game_location():
            return
        try:
            self.context.fonts.apply(source, self.font_path)
        except (OSError, ValueError) as error:
            self.show_warning(f"{self.word('error_msg.apply')}\n{error}")
            return
        self.remember(font_folder=str(self.font_path))
        self.update_location()
        self.show_info(self.word('success_msg'))

    def update_texts(self, _language=None):
        self.setWindowTitle(self.word('title'))
        for label, key in ((self.heading, 'ui_heading'), (self.subtitle, 'ui_subtitle'),
                           (self.title, 'font_list_title'), (self.preview_title, 'preview_title'),
                           (self.sample_title, 'ui_sample'), (self.location_title, 'ui_location_title')):
            label.setText(self.word(key))
        self.tabs.setTabText(0, self.word('ui_local_tab'))
        self.tabs.setTabText(1, self.word('ui_online_tab'))
        self.add_path_button.setText(self.word('ui_add_font'))
        self.refresh_btn.setText(self.word('refresh_btn'))
        self.apply_button.setText(self.word('apply_btn'))
        self.change_location_button.setText(self.word('ui_change_location'))
        self.search_input.setPlaceholderText(self.word('search_placeholder'))
        self.preview_input.setPlaceholderText(self.word('preview_input'))
        self.preview_label.language = self.context.translations.language
        self.update_preview()
        self.update_local_labels()
        self.filter_fonts()
        self.update_location()
        self.update_apply_state()

    def showEvent(self, event):
        super().showEvent(event)
        self.update_location()

    def closeEvent(self, event):
        if self.online_panel is not None:
            self.online_panel.shutdown()
            with QSignalBlocker(self.tabs):
                self.tabs.removeTab(1)
                self.online_panel.deleteLater()
                self.online_panel = None
                self.online_placeholder = QWidget()
                self.tabs.insertTab(1, self.online_placeholder, self.word('ui_online_tab'))
                self.tabs.setCurrentIndex(0)
        self.font_list.setCurrentItem(None)
        self.local_font_path = self.current_font_path = None
        self.clear_preview_font()
        self.update_local_labels()
        self.update_apply_state()
        super().closeEvent(event)

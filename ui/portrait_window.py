"""Original layout migrated to PySide6; operations live in services."""

from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont, QIcon, QImage, QPalette, QPixmap
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QMainWindow, QPushButton, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from core.paths import APP_ROOT, default_portrait_folder, resource_path
from core.text_presets import DRAFTS_KEY, HISTORY_KEY, TextPresetStore, decode_layers
from ui import styles
from ui.common import WindowSupport, center_window
from ui.text_canvas import render_portrait, to_pillow
from ui.text_editor import TextEditorDialog, restore_layer_fonts
from ui.preset_history import save_history_preview
from ui.theme import mode_icon, theme_manager
from ui.portrait_preview import EditablePreviewLabel
from ui.portrait_grid import PortraitGrid, PortraitGridView
from services.portrait_loader import PortraitLoader, to_qimage
from ui.ime_search import ImeSearchLineEdit
from ui.font_icons import font_icon


@dataclass
class PortraitDraft:
    base: QImage
    layers: list
    source_stamp: tuple


class PortraitWindow(WindowSupport, QMainWindow):
    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.context = context
        self.font_window = None
        self.theme = theme_manager(context.settings)
        self.current_photo = None
        self.new_photo = None
        self.current_selected_label = None
        self.new_selected_label = None
        self.preview_snapshots = {}
        self.pending_previews = set()
        self.text_presets = TextPresetStore(context.settings)
        self.photo_path = Path(context.settings.get("portrait_folder", str(default_portrait_folder())))
        self.new_path = Path(context.settings.get("new_portrait_folder", str(APP_ROOT / "새 초상화")))
        self.setWindowIcon(QIcon(str(resource_path("아이콘.ico"))))
        self.build_ui()
        self.current_tiles = PortraitGrid(self.current_scroll)
        self.new_tiles = PortraitGrid(self.new_scroll)
        self.loader = PortraitLoader(context.settings.path.parent / 'portrait-thumbnail-cache',
                                     render_portrait, restore_layer_fonts, self)
        self.loader.inventory_ready.connect(self.receive_inventory)
        self.loader.thumbnails_ready.connect(self.receive_thumbnails)
        self.loader.preview_ready.connect(self.receive_preview)
        self.loader.invalid.connect(self.remove_invalid)
        self.loader.failed.connect(self.load_failed)
        QApplication.instance().aboutToQuit.connect(self.loader.stop)
        for side, tiles in (('current', self.current_tiles), ('new', self.new_tiles)):
            tiles.selection_changed.connect(lambda entry, name=side: self.portrait_selection_changed(name, entry))
            tiles.clicked.connect(lambda entry, name=side: self.retry_missing_preview(name, entry))
            tiles.priority_changed.connect(lambda paths, name=side: self.loader.prioritize(name, paths))
        self.theme.changed.connect(self.update_footer_icons)
        context.translations.changed.connect(self.update_texts)
        self.update_texts()
        center_window(self)
        if self.photo_path.is_dir():
            self.load_thumbnails(self.photo_path, self.current_grid_layout)
        if self.new_path.is_dir():
            self.load_thumbnails(self.new_path, self.new_grid_layout)

    def open_font_manager(self):
        if self.font_window is None:
            from ui.font_window import FontWindow
            self.font_window = FontWindow(self.context, self)
        if self.font_window.isMinimized():
            self.font_window.showNormal()
        else:
            self.font_window.show()
        self.font_window.raise_()
        self.font_window.activateWindow()

    def closeEvent(self, event):
        if self.font_window is not None:
            self.font_window.close()
        super().closeEvent(event)

    def load_current_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, self.text("portrait_window", "current_folder_btn"), str(self.photo_path))
        if folder:
            self.photo_path = Path(folder)
            self.load_thumbnails(self.photo_path, self.current_grid_layout)
            self.remember(portrait_folder=folder)

    def select_new_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, self.text("portrait_window", "new_folder_btn"), str(self.new_path))
        if folder:
            self.new_path = Path(folder)
            self.search_input.blockSignals(True)
            self.search_input.clear()
            self.search_input.blockSignals(False)
            self.load_thumbnails(self.new_path, self.new_grid_layout)
            self.remember(new_portrait_folder=folder)

    def side_parts(self, side):
        if side == 'current':
            return self.current_tiles, self.current_preview_label, self.current_photo
        return self.new_tiles, self.new_preview_label, self.new_photo

    def update_replace_enabled(self):
        self.replace_button.setEnabled(not self.pending_previews)

    def clear_preview(self, side):
        _tiles, label, _path = self.side_parts(side)
        label.clear()
        self.preview_snapshots.pop(side, None)
        self.pending_previews.discard(side)
        self.loader.cancel_preview(side)
        if side == 'new':
            self.edit_text_button.setEnabled(False)
        self.update_replace_enabled()

    def load_thumbnails(self, folder, grid_layout, filter_text=""):
        side = 'current' if grid_layout is self.current_grid_layout else 'new'
        tiles, _label, _path = self.side_parts(side)
        self.clear_preview(side)
        tiles.clear()
        if side == 'current':
            self.current_photo = self.current_selected_label = None
        else:
            self.new_photo = self.new_selected_label = None
        drafts = self.context.settings.get(DRAFTS_KEY, {}) if side == 'new' else {}
        self.loader.start_folder(side, Path(folder), drafts)

    def receive_inventory(self, side, records):
        tiles, _label, _path = self.side_parts(side)
        tiles.set_records(records)
        self.arrange_thumbnails(side == 'current', self.search_input.search_text() if side == 'new' else '')
        if not records:
            self.show_warning(self.text('portrait_window', 'empty_folder'))

    def receive_thumbnails(self, side, payloads):
        tiles, _label, _path = self.side_parts(side)
        tiles.update_images(payloads)

    def remove_invalid(self, side, path):
        tiles, _label, _selected = self.side_parts(side)
        tiles.remove(path)

    def load_failed(self, side, kind, message):
        self.clear_preview(side)
        key = 'error_msg.folder_load' if kind == 'scan' else 'error_msg.preview'
        self.show_warning(f"{self.text('portrait_window', key)}\n{message}")

    def filter_thumbnails(self, _text=None):
        self.arrange_thumbnails(False, self.search_input.search_text())
        self.new_scroll.verticalScrollBar().setValue(0)

    def arrange_thumbnails(self, is_current, query=""):
        side = 'current' if is_current else 'new'
        tiles, _label, selected = self.side_parts(side)
        tiles.filter(query, selected)

    def thumbnail_clicked(self, widget, is_current, base=None):
        """Select a photo or explicitly reload the currently selected preview."""
        side = 'current' if is_current else 'new'
        tiles, _label, _path = self.side_parts(side)
        changed = tiles.select(widget)
        if not changed:
            self.portrait_selection_changed(side, tiles.selected, base=base, force=True)

    def portrait_selection_changed(self, side, widget, *, base=None, force=False):
        _tiles, _label, previous = self.side_parts(side)
        path = widget.file_path if widget is not None else None
        previous_widget = self.current_selected_label if side == 'current' else self.new_selected_label
        if side == 'current':
            self.current_photo = path
            self.current_selected_label = widget
        else:
            self.new_photo = path
            self.new_selected_label = widget
        if not force and path == previous and widget is previous_widget:
            return
        self.clear_preview(side)
        if widget is None:
            return
        self.pending_previews.add(side)
        self.update_replace_enabled()
        self.loader.request_preview(side, widget.file_path, base)

    def retry_missing_preview(self, side, widget):
        # A second click can retry a failed preview, while an ordinary click
        # following selectionChanged must not submit the same image twice.
        tiles, _label, path = self.side_parts(side)
        if (tiles.selected is widget and widget.file_path == path
                and side not in self.preview_snapshots and side not in self.pending_previews):
            self.portrait_selection_changed(side, widget, force=True)

    def selection_matches_preview(self, side):
        tiles, _label, path = self.side_parts(side)
        entry = tiles.selection_in_view()
        snapshot = self.preview_snapshots.get(side)
        selected_label = self.current_selected_label if side == 'current' else self.new_selected_label
        return (entry is not None and entry is tiles.selected and entry is selected_label
                and entry.file_path == path and snapshot is not None and snapshot['path'] == path)

    def receive_preview(self, side, payload):
        tiles, label, selected = self.side_parts(side)
        entry = tiles.selection_in_view()
        if selected != payload['path'] or entry is None or entry.file_path != selected:
            return
        self.preview_snapshots[side] = payload
        self.pending_previews.discard(side)
        pixmap = QPixmap.fromImage(payload['image'])
        if side == 'new':
            label.set_preview(pixmap, payload['bounds'], (342, 342))
            self.edit_text_button.setEnabled(True)
        else:
            label.setPixmap(pixmap)
        self.update_replace_enabled()

    def replace_photo(self):
        if self.current_photo is None or self.new_photo is None:
            self.show_warning(self.text('portrait_window', 'select_both'))
            return
        if self.pending_previews or 'current' not in self.preview_snapshots or 'new' not in self.preview_snapshots:
            return
        if not all(self.selection_matches_preview(side) for side in ('current', 'new')):
            # Never write to a path that disagrees with the visible selection.
            # Resynchronize first; the user can apply again after previews load.
            for side in ('current', 'new'):
                if not self.selection_matches_preview(side):
                    tiles, _label, _path = self.side_parts(side)
                    self.thumbnail_clicked(tiles.selection_in_view(), side == 'current')
            return
        try:
            draft = self.valid_draft(self.new_photo)
            image = (to_pillow(render_portrait(draft.base, draft.layers))
                     if draft and draft.layers else None)
            self.context.portraits.replace(self.current_photo, self.new_photo, image)
        except (OSError, ValueError) as error:
            self.show_warning(f"{self.text('portrait_window', 'error_msg.replace')}\n{error}")
            return
        # Only the changed file is refreshed; the folder and search stay in place.
        self.loader.refresh_path('current', self.current_photo)
        self.thumbnail_clicked(self.current_selected_label, True)
        if self.current_photo in self.new_tiles.by_path:
            self.loader.refresh_path('new', self.current_photo)
            if self.new_photo == self.current_photo:
                self.thumbnail_clicked(self.new_selected_label, False)
        self.show_info(self.text('portrait_window', 'success_msg') + '\n' +
                       self.text('portrait_window', 'backup_msg'))

    def update_texts(self, _language=None):
        self.setWindowTitle(self.text("portrait_window", "title"))
        self.current_folder_btn.setText(self.text("portrait_window", "current_folder_btn"))
        self.new_folder_btn.setText(self.text("portrait_window", "new_folder_btn"))
        self.replace_button.setText(self.text("portrait_window", "replace_btn"))
        self.search_input.setPlaceholderText(self.text("portrait_window", "search_placeholder"))
        for label, key in ((self.current_title, "current_list"), (self.new_title, "new_list"),
                           (self.current_preview_title, "current_preview"),
                           (self.new_preview_title, "new_preview")):
            label.setText(self.text("portrait_window", key))
        korean = self.context.translations.language == "kr"
        self.creator_label.setText("제작자 : 귀물(진하형)" if korean else "Creator : JinhaHyong")
        self.guild_label.setVisible(korean)
        self.separator_label.setVisible(korean)
        self.sync_language_buttons()
        self.update_footer_icons()
        self.font_button.setToolTip(self.text('start_window', 'font_btn'))
        self.font_button.setAccessibleName(self.text('start_window', 'font_btn'))
        self.edit_text_button.setToolTip(self.text("text_editor", "open"))
        self.edit_text_button.setAccessibleName(self.text("text_editor", "open"))
        self.new_preview_label.setToolTip(self.text("text_editor", "preview_hint"))

    def update_footer_icons(self, _mode=None):
        self.font_button.setIcon(font_icon(self.palette().color(QPalette.ColorRole.ButtonText)))
        dark = self.theme.mode == 'dark'
        self.theme_button.setIcon(mode_icon(self.theme.mode))
        self.theme_button.setChecked(dark)
        current = self.text('common', 'dark_mode' if dark else 'light_mode')
        target = self.text('common', 'light_mode' if dark else 'dark_mode')
        self.theme_button.setAccessibleName(current)
        self.theme_button.setToolTip(self.text('common', 'theme_toggle').format(current=current, target=target))

    def toggle_theme(self):
        mode = 'light' if self.theme.mode == 'dark' else 'dark'
        self.theme.set_mode(mode)
        self.remember(theme_mode=mode)

    @staticmethod
    def source_stamp(path):
        stat = Path(path).stat()
        return stat.st_size, stat.st_mtime_ns

    def valid_draft(self, path):
        snapshot = self.preview_snapshots.get('new')
        if snapshot is None or snapshot['path'] != path:
            return None
        if tuple(snapshot['stamp']) != self.source_stamp(path):
            raise ValueError(self.text('text_editor', 'source_changed'))
        if snapshot['layers'] is None:
            return None
        return PortraitDraft(snapshot['base'], snapshot['layers'], tuple(snapshot['stamp']))

    def open_text_editor(self):
        snapshot = self.preview_snapshots.get('new')
        if self.new_photo is None or snapshot is None or snapshot['path'] != self.new_photo:
            return
        try:
            stamp = self.source_stamp(self.new_photo)
            if stamp != tuple(snapshot['stamp']):
                self.show_warning(self.text('text_editor', 'source_changed'))
                self.thumbnail_clicked(self.new_selected_label, False)
                return
            base = snapshot['base']
            layers = (snapshot['layers'] if snapshot['layers'] is not None else
                      self.text_presets.template_for(base.width(), base.height()))
            editor = TextEditorDialog(self.context, base, layers, self,
                                      batch_handler=lambda dialog, path=self.new_photo, original=stamp:
                                      self.open_batch_apply(dialog, path, original))
            result = editor.exec()
            edited_layers = editor.layers()
            editor.deleteLater()
            if result != TextEditorDialog.DialogCode.Accepted:
                return
            if self.new_photo is None or stamp != self.source_stamp(self.new_photo):
                self.show_warning(self.text('text_editor', 'source_changed'))
                return
            updates = self.text_presets.updates_for_apply(
                self.new_photo, stamp, base.width(), base.height(), edited_layers)
            self.remember(**updates)
            for entry in updates[HISTORY_KEY]:
                if (self.text_presets.photo_key(entry['source_path']) == self.text_presets.photo_key(self.new_photo)
                        and entry.get('source_stamp') == list(stamp)):
                    # Font registration belongs to the UI thread; painting and PNG IO do not.
                    history_layers = restore_layer_fonts(decode_layers(entry.get('layers')))
                    self.loader.run_auxiliary(
                        lambda record=deepcopy(entry), image=QImage(base), prepared=history_layers:
                        save_history_preview(self.text_presets, record, image, layers=prepared))
            self.loader.refresh_path('new', self.new_photo, base=base, layers=edited_layers, stamp=stamp)
            self.thumbnail_clicked(self.new_selected_label, False, base)
        except (OSError, ValueError) as error:
            self.show_warning(f"{self.text('portrait_window', 'error_msg.preview')}\n{error}")

    def open_batch_apply(self, editor, source_path, source_stamp):
        from ui.portrait_batch_dialog import PortraitBatchDialog
        try:
            if self.source_stamp(source_path) != source_stamp:
                raise ValueError(self.text('text_editor', 'source_changed'))
            source = {'source_path': str(source_path.absolute()), 'source_stamp': list(source_stamp),
                      'width': editor.canvas.base.width(), 'height': editor.canvas.base.height(),
                      'layers': [asdict(layer) for layer in editor.layers()]}
            dialog = PortraitBatchDialog(self.context, self.new_tiles, self.loader, source,
                                          lambda records: self.commit_batch_settings(records, source), editor)
            result = dialog.exec()
            applied, skipped = dialog.applied_count, dialog.skipped_count
            dialog.deleteLater()
            self.new_scroll.schedule_visible()
            if result == TextEditorDialog.DialogCode.Accepted:
                message = self.text('text_editor', 'batch_done').format(count=applied)
                if skipped:
                    message += '\n' + self.text('text_editor', 'batch_skipped').format(count=skipped)
                editor.show_info(message)
        except (OSError, ValueError) as error:
            editor.show_warning(self.text('text_editor', 'batch_error') + '\n' + str(error))

    def commit_batch_settings(self, records, source):
        if self.source_stamp(source['source_path']) != tuple(source['source_stamp']):
            raise ValueError(self.text('text_editor', 'source_changed'))
        unchanged = []
        for record in records:
            try:
                if self.source_stamp(record['path']) == tuple(record['stamp']):
                    unchanged.append(record)
            except OSError:
                pass
        if not unchanged:
            raise ValueError(self.text('text_editor', 'batch_no_readable'))
        updates = self.text_presets.updates_for_batch(unchanged, source)
        # One atomic write: a cancelled preparation or failed save applies nothing.
        self.context.settings.update(**updates)
        self.loader.refresh_many('new', unchanged)
        by_key = {self.text_presets.photo_key(record['path']): record for record in unchanged}
        for entry in updates[HISTORY_KEY]:
            record = by_key.get(self.text_presets.photo_key(entry['source_path']))
            if record is None or entry.get('source_stamp') != list(record['stamp']):
                continue
            # Existing representative images are retained by save_history_preview.
            prepared = restore_layer_fonts(decode_layers(entry.get('layers')))
            def save_preview(target=record, history=deepcopy(entry), layers=prepared):
                if self.source_stamp(target['path']) != tuple(target['stamp']):
                    return
                base = target.get('base')
                if base is None:
                    base = to_qimage(self.context.portraits.read_image(target['path']))
                if self.source_stamp(target['path']) == tuple(target['stamp']):
                    save_history_preview(self.text_presets, history, base, layers=layers)
            self.loader.run_auxiliary(save_preview)
        if (self.new_photo is not None and self.text_presets.photo_key(self.new_photo) in by_key
                and self.new_selected_label is not None):
            self.thumbnail_clicked(self.new_selected_label, False)
        return len(unchanged), len(records) - len(unchanged)

    @staticmethod
    def section_frame():
        frame = QFrame()
        frame.setObjectName('portraitPanel')
        frame.setFrameShape(QFrame.Shape.NoFrame)
        frame.setStyleSheet(styles.PORTRAIT_PANEL_STYLE)
        frame.setFixedSize(400, 400)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        return frame, layout

    @staticmethod
    def add_section_header(layout, title, search=None, *, centered=False):
        header = QWidget()
        header.setFixedHeight(28)
        row = QHBoxLayout(header)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        title.setFont(QFont('맑은 고딕', 9, QFont.Weight.DemiBold))
        title.setStyleSheet(styles.PORTRAIT_TITLE_STYLE)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter if centered
                           else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if search is not None:
            title.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
            row.addWidget(title)
            search.setFixedHeight(28)
            search.setMinimumWidth(0)
            search.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            row.addWidget(search, 1)
        else:
            row.addWidget(title, 1)
        layout.addWidget(header)

    def build_ui(self):
        # 배경색 설정
        self.setStyleSheet(styles.WINDOW_STYLE)

        # 중앙 위젯 설정
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # 버튼 스타일
        button_style = styles.BUTTON_STYLE

        # 좌우 레이아웃 생성
        content_layout = QHBoxLayout()
        content_layout.setSpacing(10)

        left_layout = QVBoxLayout()
        left_layout.setSpacing(8)

        right_layout = QVBoxLayout()
        right_layout.setSpacing(8)

        # 좌측 영역
        self.current_folder_btn = QPushButton("현재 초상화 폴더 선택")
        self.current_folder_btn.setStyleSheet(button_style)
        self.current_folder_btn.clicked.connect(self.load_current_folder)
        self.current_folder_btn.setFixedWidth(400)
        left_layout.addWidget(self.current_folder_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # 현재 초상화 목록
        current_list_frame, current_list_layout = self.section_frame()

        self.current_title = QLabel("현재 초상화 목록")
        self.add_section_header(current_list_layout, self.current_title)

        self.current_scroll = PortraitGridView()
        current_list_layout.addWidget(self.current_scroll)
        self.current_grid_layout = self.current_scroll

        left_layout.addWidget(current_list_frame)

        # 현재 초상화 미리보기
        current_preview_container, current_preview_layout = self.section_frame()

        self.current_preview_title = QLabel("현재 초상화 미리보기")
        self.add_section_header(current_preview_layout, self.current_preview_title, centered=True)

        self.current_preview_label = QLabel()
        self.current_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.current_preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.current_preview_label.setFixedHeight(342)
        current_preview_layout.addWidget(self.current_preview_label)

        # 미리보기 중앙 정렬을 위한 컨테이너
        preview_wrapper = QWidget()
        preview_wrapper_layout = QHBoxLayout(preview_wrapper)
        preview_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        preview_wrapper_layout.addStretch()
        preview_wrapper_layout.addWidget(current_preview_container)
        preview_wrapper_layout.addStretch()
        left_layout.addWidget(preview_wrapper)

        # 우측 영역
        self.new_folder_btn = QPushButton("새 초상화 폴더 선택")
        self.new_folder_btn.setStyleSheet(button_style)
        self.new_folder_btn.clicked.connect(self.select_new_folder)
        self.new_folder_btn.setFixedWidth(400)
        right_layout.addWidget(self.new_folder_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # 새 초상화 목록
        new_list_frame, new_list_layout = self.section_frame()

        self.new_title = QLabel("새 초상화 목록")

        self.search_input = ImeSearchLineEdit()
        self.search_input.setPlaceholderText("이미지 이름 검색...")
        self.search_input.setStyleSheet(styles.PORTRAIT_SEARCH_INPUT_STYLE)
        self.search_input.query_changed.connect(self.filter_thumbnails)
        self.add_section_header(new_list_layout, self.new_title, self.search_input)

        self.new_scroll = PortraitGridView()
        new_list_layout.addWidget(self.new_scroll)
        self.new_grid_layout = self.new_scroll

        right_layout.addWidget(new_list_frame)

        # 새 초상화 미리보기
        new_preview_container, new_preview_layout = self.section_frame()

        self.new_preview_title = QLabel("새 초상화 미리보기")
        self.add_section_header(new_preview_layout, self.new_preview_title, centered=True)

        self.new_preview_label = EditablePreviewLabel()
        self.new_preview_label.double_clicked.connect(self.open_text_editor)
        self.new_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.new_preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.new_preview_label.setFixedHeight(342)
        self.edit_text_button = self.new_preview_label.edit_button
        self.edit_text_button.clicked.connect(self.open_text_editor)
        new_preview_layout.addWidget(self.new_preview_label)

        # 미리보기 중앙 정렬을 위한 컨테이너
        new_preview_wrapper = QWidget()
        new_preview_wrapper_layout = QHBoxLayout(new_preview_wrapper)
        new_preview_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        new_preview_wrapper_layout.addStretch()
        new_preview_wrapper_layout.addWidget(new_preview_container)
        new_preview_wrapper_layout.addStretch()
        right_layout.addWidget(new_preview_wrapper)

        # 언어 선택 버튼
        lang_container = QWidget()
        lang_layout = QHBoxLayout(lang_container)
        lang_layout.setContentsMargins(0, 0, 0, 0)
        lang_layout.setSpacing(0)

        # 언어 선택 버튼 스타일
        lang_button_style = styles.PORTRAIT_LANGUAGE_BUTTON_STYLE

        self.kr_btn = QPushButton("한국어")
        self.kr_btn.setFixedWidth(43)
        self.kr_btn.setStyleSheet(lang_button_style)
        self.kr_btn.setCheckable(True)
        self.kr_btn.setChecked(True)
        self.kr_btn.clicked.connect(self.change_language)

        self.en_btn = QPushButton("EN")
        self.en_btn.setFixedWidth(43)
        self.en_btn.setStyleSheet(lang_button_style)
        self.en_btn.setCheckable(True)
        self.en_btn.clicked.connect(self.change_language)

        lang_layout.addWidget(self.kr_btn)
        lang_layout.addWidget(self.en_btn)
        lang_layout.addSpacing(6)
        self.font_button = QToolButton()
        self.font_button.setFixedSize(30, 28)
        self.font_button.setIconSize(QSize(22, 22))
        self.font_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.font_button.setStyleSheet(styles.THEME_BUTTON_STYLE)
        self.font_button.clicked.connect(self.open_font_manager)
        lang_layout.addWidget(self.font_button)
        lang_layout.addSpacing(6)
        self.theme_button = QToolButton()
        self.theme_button.setFixedSize(30, 28)
        self.theme_button.setIconSize(QSize(22, 22))
        self.theme_button.setCheckable(True)
        self.theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_button.setStyleSheet(styles.THEME_BUTTON_STYLE)
        self.theme_button.clicked.connect(self.toggle_theme)
        lang_layout.addWidget(self.theme_button)

        # 좌우 레이아웃 추가
        content_layout.addLayout(left_layout)
        content_layout.addLayout(right_layout)

        # 하단 레이아웃 설정
        bottom_container = QWidget()
        bottom_container.setFixedHeight(35)
        bottom_layout = QHBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(10, 0, 10, 0)
        bottom_layout.setSpacing(2)

        # 왼쪽 영역 (제작자/길드 정보)
        info_container = QWidget()
        info_layout = QHBoxLayout(info_container)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)

        self.creator_label = QLabel("제작자 : 귀물(진하형)")
        self.creator_label.setStyleSheet(styles.CREATOR_STYLE)
        info_layout.addWidget(self.creator_label)

        self.separator_label = QLabel(" /")
        self.separator_label.setStyleSheet(styles.SEPARATOR_STYLE)
        info_layout.addWidget(self.separator_label)

        self.guild_label = QLabel(" 길드 : 노블레스")
        self.guild_label.setStyleSheet(styles.GUILD_STYLE)
        info_layout.addWidget(self.guild_label)

        # 중앙 영역 (초상화 교체 버튼)
        center_container = QWidget()
        center_layout = QHBoxLayout(center_container)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        self.replace_button = QPushButton("초상화 교체")
        self.replace_button.setFixedWidth(120)
        self.replace_button.setStyleSheet(button_style)
        self.replace_button.clicked.connect(self.replace_photo)

        center_layout.addStretch()
        center_layout.addWidget(self.replace_button)
        center_layout.addStretch()

        # 하단 레이아웃에 위젯 추가 (1:2:1 비율)
        bottom_layout.addWidget(info_container, 1)
        bottom_layout.addWidget(center_container, 2)
        bottom_layout.addWidget(lang_container, 1, Qt.AlignmentFlag.AlignRight)  # 오른쪽 정렬

        # 메인 레이아웃에 추가
        main_layout.addLayout(content_layout)
        main_layout.addWidget(bottom_container)

        # 창 크기 고정
        self.setFixedSize(830, 910)

"""A separate portrait text editor; accepting it only updates an in-memory draft."""

from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFontComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPlainTextEdit, QPushButton, QSlider,
    QSizePolicy, QSpinBox, QStyledItemDelegate, QVBoxLayout, QWidget,
)

from core.portrait_edit import TextOverlay
from core.paths import resource_path
from core.text_presets import TextPresetStore
from ui.common import WindowSupport
from ui.font_registry import layer_font, load_downloaded_fonts, registered_path, set_layer_font_file
from ui.styles import ALIGNMENT_COMBO_STYLE, ALIGNMENT_MENU_STYLE, BUTTON_STYLE, TEXT_STYLE_CARD
from ui.text_canvas import TextCanvas, to_pillow


def restore_layer_fonts(layers):
    for layer in layers:
        # Recover drafts that referenced the removed, formerly bundled font.
        # Do not rewrite or remove any independently supplied PC font file.
        old = (layer.font_file or '').replace('\\', '/').casefold()
        if old.endswith('/resources/fonts/cookierun bold.ttf'):
            set_layer_font_file(layer, resource_path('fonts', 'NanumGothic-Bold.ttf'))
        if layer.font_file and Path(layer.font_file).is_file():
            try:
                set_layer_font_file(layer, layer.font_file)
            except ValueError:
                pass
    return layers


class TextEditorDialog(WindowSupport, QDialog):
    def __init__(self, context, base: QImage, layers=None, parent=None, *, batch_handler=None):
        super().__init__(parent)
        if base.isNull():
            raise ValueError("Cannot edit an empty image")
        self.context = context
        self.batch_handler = batch_handler
        self.setWindowTitle(self.label("title"))
        self.resize(1000, 820)
        self.active_id = ""
        self._updating = False
        self._result_layers = None
        self.presets = TextPresetStore(context.settings)
        load_downloaded_fonts()
        self.canvas = TextCanvas(base, restore_layer_fonts(deepcopy(layers or [])))
        self.build_ui()
        self.canvas.selected.connect(self.select_from_canvas)
        self.canvas.text_changed.connect(self.sync_canvas_text)
        for item in self.canvas.items_by_id.values():
            self.append_list_item(item.layer)
        if self.layers_list.count():
            self.layers_list.setCurrentRow(0)
        else:
            self.add_layer()
        self.text_input.setFocus()

    def label(self, key):
        return self.text("text_editor", key)

    def build_ui(self):
        layout = QVBoxLayout(self)
        hint = QLabel(self.label("hint"))
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)
        content = QHBoxLayout()
        content.addWidget(self.canvas, 1)

        panel = QWidget()
        panel.setFixedWidth(365)
        controls = QVBoxLayout(panel)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)

        layers_group = QGroupBox(self.label("layers"))
        layers_group.setMaximumHeight(170)
        layers_layout = QVBoxLayout(layers_group)
        layers_layout.setContentsMargins(10, 12, 10, 10)
        layers_layout.setSpacing(6)
        self.layers_list = QListWidget()
        self.layers_list.setMinimumHeight(50)
        self.layers_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.layers_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.layers_list.currentItemChanged.connect(self.select_from_list)
        layers_layout.addWidget(self.layers_list)
        buttons = QHBoxLayout()
        self.add_button = QPushButton(self.label("add"))
        self.remove_button = QPushButton(self.label("remove"))
        self.add_button.clicked.connect(self.add_layer)
        self.remove_button.clicked.connect(self.remove_layer)
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        layers_layout.addLayout(buttons)
        controls.addWidget(layers_group, 1)

        self.properties = QGroupBox(self.label("properties"))
        form = QFormLayout(self.properties)
        form.setContentsMargins(10, 12, 10, 10)
        form.setVerticalSpacing(6)
        form.setHorizontalSpacing(8)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        self.text_input = QPlainTextEdit()
        self.text_input.setPlaceholderText(self.label("placeholder"))
        self.text_input.setMinimumHeight(64)
        self.text_input.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.text_input.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        form.addRow(self.label("text"), self.text_input)
        self.font_combo = QFontComboBox()
        self.font_combo.setMinimumWidth(0)
        self.font_combo.setMinimumContentsLength(6)
        self.font_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.font_combo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        form.addRow(self.label("font"), self.font_combo)
        self.import_font_button = QPushButton(self.label("font_file"))
        self.import_font_button.clicked.connect(self.import_font)
        font_buttons = QHBoxLayout()
        font_buttons.addWidget(self.import_font_button, 1)
        from ui.font_sources import open_font_site, font_site_label, font_site_tooltip
        self.font_site_button = QPushButton(font_site_label(self))
        self.font_site_button.setToolTip(font_site_tooltip(self))
        self.font_site_button.clicked.connect(lambda: open_font_site(self))
        font_buttons.addWidget(self.font_site_button, 1)
        form.addRow(font_buttons)
        self.font_size = self.spin(8, 200)
        self.font_size.setSuffix(" px")
        form.addRow(self.label("size"), self.font_size)
        emphasis = QHBoxLayout()
        emphasis.setSpacing(6)
        for key in ("bold", "italic", "intense", "shadow"):
            button = QPushButton(self.label(key))
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(34)
            button.setMinimumWidth(0)
            button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            button.setStyleSheet(TEXT_STYLE_CARD)
            setattr(self, key, button)
            emphasis.addWidget(button, 1)
        form.addRow(emphasis)
        self.alignment = QComboBox()
        self.alignment.setStyleSheet(ALIGNMENT_COMBO_STYLE)
        self.alignment.setItemDelegate(QStyledItemDelegate(self.alignment))
        alignment_view = self.alignment.view()
        alignment_view.setStyleSheet(ALIGNMENT_MENU_STYLE)
        alignment_view.setMouseTracking(True)
        for key in ("left", "center", "right"):
            self.alignment.addItem(self.label(key), key)
        form.addRow(self.label("alignment"), self.alignment)
        self.text_color = QPushButton()
        self.text_color.clicked.connect(lambda: self.choose_color("text_color"))
        form.addRow(self.label("text_color"), self.text_color)
        self.text_opacity, row = self.opacity_controls()
        form.addRow(self.label("text_opacity"), row)
        controls.addWidget(self.properties, 3)

        self.box_properties = QGroupBox(self.label("box_properties"))
        self.box_properties.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        box_form = QFormLayout(self.box_properties)
        box_form.setContentsMargins(10, 12, 10, 10)
        box_form.setVerticalSpacing(6)
        box_form.setHorizontalSpacing(8)
        box_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        box_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        self.background_color = QPushButton()
        self.background_color.clicked.connect(lambda: self.choose_color("background_color"))
        box_form.addRow(self.label("background_color"), self.background_color)
        self.background_opacity, row = self.opacity_controls()
        box_form.addRow(self.label("background_opacity"), row)
        self.radius = self.spin(0, 60)
        box_form.addRow(self.label("radius"), self.radius)
        controls.addWidget(self.box_properties)
        content.addWidget(panel)
        layout.addLayout(content, 1)

        footer = QHBoxLayout()
        self.export_button = QPushButton(self.label("export"))
        self.export_button.clicked.connect(self.export_image)
        footer.addWidget(self.export_button)
        self.load_preset_button = QPushButton(self.label("load_preset"))
        self.load_preset_button.setEnabled(self.presets.has_history())
        self.load_preset_button.clicked.connect(self.load_latest_preset)
        footer.addWidget(self.load_preset_button)
        self.batch_apply_button = QPushButton(self.label('batch_open'))
        self.batch_apply_button.setEnabled(self.batch_handler is not None)
        self.batch_apply_button.clicked.connect(self.apply_to_portraits)
        footer.addWidget(self.batch_apply_button)
        footer.addStretch()
        self.dialog_buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.dialog_buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.label("apply"))
        self.dialog_buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(self.label("cancel"))
        self.dialog_buttons.accepted.connect(self.accept)
        self.dialog_buttons.rejected.connect(self.reject)
        self.dialog_buttons.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(BUTTON_STYLE)
        footer.addWidget(self.dialog_buttons)
        layout.addLayout(footer)

        self.text_input.textChanged.connect(self.update_selected)
        self.font_combo.currentFontChanged.connect(self.update_selected)
        for control in (self.font_size, self.radius,
                        self.text_opacity, self.background_opacity):
            control.valueChanged.connect(self.update_selected)
        self.bold.toggled.connect(self.update_selected)
        self.italic.toggled.connect(self.update_selected)
        self.intense.toggled.connect(self.update_selected)
        self.shadow.toggled.connect(self.update_selected)
        self.alignment.currentIndexChanged.connect(self.update_selected)

    @staticmethod
    def spin(minimum, maximum):
        control = QSpinBox()
        control.setRange(minimum, maximum)
        control.setKeyboardTracking(False)
        return control

    @staticmethod
    def opacity_controls():
        row = QHBoxLayout()
        row.setSpacing(6)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimumWidth(0)
        slider.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        slider.setRange(0, 100)
        spin = QSpinBox()
        spin.setRange(0, 100)
        spin.setSuffix(" %")
        slider.valueChanged.connect(spin.setValue)
        spin.valueChanged.connect(slider.setValue)
        row.addWidget(slider, 1)
        row.addWidget(spin)
        return spin, row

    def append_list_item(self, layer):
        item = QListWidgetItem(layer.text.splitlines()[0][:24] if layer.text else self.label("empty_layer"))
        item.setData(Qt.ItemDataRole.UserRole, layer.id)
        self.layers_list.addItem(item)
        return item

    def add_layer(self):
        width = max(1, int(self.canvas.base.width() * .8))
        layer = TextOverlay(width=width, x=(self.canvas.base.width() - width) / 2,
                            y=self.canvas.base.height() * .7)
        self.canvas.add_layer(layer)
        self.layers_list.setCurrentItem(self.append_list_item(layer))
        self.text_input.setFocus()

    def remove_layer(self):
        current = self.layers_list.currentItem()
        if current is None:
            return
        layer_id = current.data(Qt.ItemDataRole.UserRole)
        self.active_id = ""
        self.canvas.remove_layer(layer_id)
        self.layers_list.takeItem(self.layers_list.row(current))
        if self.layers_list.currentItem() is not None:
            self.select_from_list(self.layers_list.currentItem())
        else:
            self.set_active("")

    def select_from_list(self, current, _previous=None):
        layer_id = current.data(Qt.ItemDataRole.UserRole) if current is not None else ""
        self.set_active(layer_id)
        self.canvas.select_layer(layer_id)

    def select_from_canvas(self, layer_id):
        if not layer_id:
            return
        for index in range(self.layers_list.count()):
            item = self.layers_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == layer_id:
                with QSignalBlocker(self.layers_list):
                    self.layers_list.setCurrentItem(item)
                self.set_active(layer_id)
                break

    def sync_canvas_text(self, layer_id, text):
        if layer_id != self.active_id:
            return
        with QSignalBlocker(self.text_input):
            self.text_input.setPlainText(text)
        current = self.layers_list.currentItem()
        if current is not None:
            current.setText(text.splitlines()[0][:24] if text else self.label("empty_layer"))

    def set_active(self, layer_id):
        self.active_id = layer_id
        self.properties.setEnabled(bool(layer_id))
        self.box_properties.setEnabled(bool(layer_id))
        self.remove_button.setEnabled(bool(layer_id))
        if not layer_id:
            return
        layer = self.canvas.items_by_id[layer_id].layer
        self._updating = True
        try:
            self.text_input.setPlainText(layer.text)
            self.font_combo.setCurrentFont(layer_font(layer))
            self.font_size.setValue(layer.font_size)
            self.bold.setChecked(layer.bold)
            self.italic.setChecked(layer.italic)
            self.intense.setChecked(layer.intense)
            self.shadow.setChecked(layer.shadow)
            self.alignment.setCurrentIndex(self.alignment.findData(layer.alignment))
            self.text_opacity.setValue(layer.text_opacity)
            self.background_opacity.setValue(layer.background_opacity)
            self.radius.setValue(layer.radius)
            self.update_color_button(self.text_color, layer.text_color)
            self.update_color_button(self.background_color, layer.background_color)
        finally:
            self._updating = False

    @staticmethod
    def update_color_button(button, color):
        foreground = "black" if QColor(color).lightness() > 128 else "white"
        button.setText(color.upper())
        button.setStyleSheet(f"background-color: {color}; color: {foreground}; padding: 4px;")

    def update_selected(self, *_args):
        if self._updating or not self.active_id:
            return
        item = self.canvas.items_by_id[self.active_id]
        layer = deepcopy(item.layer)
        layer.text = self.text_input.toPlainText()
        family = self.font_combo.currentFont().family()
        if family != layer.font_family:
            path = registered_path(family)
            if path is not None:
                set_layer_font_file(layer, path)
            else:
                layer.font_family, layer.font_file = family, None
                layer.font_style, layer.font_weight, layer.font_slant = "", None, "normal"
        layer.font_size = self.font_size.value()
        layer.bold, layer.italic = self.bold.isChecked(), self.italic.isChecked()
        layer.intense, layer.shadow = self.intense.isChecked(), self.shadow.isChecked()
        layer.alignment = self.alignment.currentData()
        layer.text_opacity, layer.background_opacity = self.text_opacity.value(), self.background_opacity.value()
        layer.radius = self.radius.value()
        item.update_layer(layer)
        current = self.layers_list.currentItem()
        if current is not None:
            current.setText(layer.text.splitlines()[0][:24] if layer.text else self.label("empty_layer"))

    def choose_color(self, attribute):
        if not self.active_id:
            return
        item = self.canvas.items_by_id[self.active_id]
        color = QColorDialog.getColor(QColor(getattr(item.layer, attribute)), self, self.label(attribute))
        if color.isValid():
            layer = deepcopy(item.layer)
            setattr(layer, attribute, color.name())
            item.update_layer(layer)
            self.update_color_button(getattr(self, attribute), color.name())

    def import_font(self):
        path, _filter = QFileDialog.getOpenFileName(self, self.label("font_file"), "", "Fonts (*.ttf *.otf)")
        if path:
            self.use_font_file(path)

    def use_font_file(self, path):
        self._updating = True
        try:
            if self.active_id:
                item = self.canvas.items_by_id[self.active_id]
                layer = deepcopy(item.layer)
                font = set_layer_font_file(layer, path)
                self.font_combo.setCurrentFont(font)
                item.update_layer(layer)
        except ValueError:
            self.show_warning(self.label("font_error"))
        finally:
            self._updating = False

    def load_latest_preset(self):
        from ui.preset_history import PresetHistoryDialog
        for item in self.canvas.items_by_id.values():
            item.finish_inline_edit()
        dialog = PresetHistoryDialog(self.context, self.presets, self)
        result = dialog.exec()
        entry = dialog.selected_entry
        dialog.deleteLater()
        if result != QDialog.DialogCode.Accepted or entry is None:
            return
        layers = restore_layer_fonts(self.presets.layers_for(
            entry, self.canvas.base.width(), self.canvas.base.height()))
        self.active_id = ""
        with QSignalBlocker(self.layers_list):
            for layer_id in list(self.canvas.items_by_id):
                self.canvas.remove_layer(layer_id)
            self.layers_list.clear()
            for layer in layers:
                self.canvas.add_layer(layer)
                self.append_list_item(layer)
        if self.layers_list.count():
            self.layers_list.setCurrentRow(0)
            self.text_input.setFocus()
        else:
            self.set_active("")

    def export_image(self):
        path, _filter = QFileDialog.getSaveFileName(self, self.label("export"), "portrait_text.bmp", "BMP (*.bmp)")
        if not path:
            return
        try:
            self.context.portraits.save_edited(to_pillow(self.canvas.composed_image()), path)
        except (OSError, ValueError) as error:
            self.show_warning(f"{self.label('save_error')}\n{error}")
            return
        self.show_info(self.label("saved"))

    def apply_to_portraits(self):
        if self.batch_handler is None:
            return
        for item in self.canvas.items_by_id.values():
            item.finish_inline_edit()
        self.batch_handler(self)
        self.load_preset_button.setEnabled(self.presets.has_history())

    def layers(self):
        return deepcopy(self._result_layers) if self._result_layers is not None else self.canvas.layers()

    def done(self, result):
        if self._result_layers is None:
            self._result_layers = self.canvas.layers()
            self._updating = True
            self.active_id = ""
            self.canvas.dispose()
        super().done(result)

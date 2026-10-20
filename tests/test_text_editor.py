"""Check text rendering, dragging, cancellation and full-resolution BMP output."""

from copy import deepcopy
import os
from pathlib import Path
import sys
import tempfile
from time import monotonic
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from core.context import AppContext
from core.paths import resource_path
from core.portrait_edit import TextOverlay
from core.settings import Settings
from ui.common import WindowSupport
from ui.portrait_window import PortraitWindow
from ui.styles import apply_theme
from ui.text_canvas import TextCanvas, render_portrait, text_document, to_pillow
from ui.text_editor import TextEditorDialog


class TextEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        apply_theme(cls.app)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jhhorizon-text-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.context = AppContext.create(Settings(self.root / "settings.json"))
        self.base = QImage(320, 400, QImage.Format.Format_RGB32)
        self.base.fill(QColor("blue"))
        self.info = patch.object(WindowSupport, "show_info").start()
        self.warning = patch.object(WindowSupport, "show_warning").start()
        self.slot_errors = []
        patch.object(sys, "excepthook", side_effect=lambda *args: self.slot_errors.append(args)).start()
        self.addCleanup(patch.stopall)

    def wait_for(self, predicate):
        deadline = monotonic() + 5
        while not predicate() and monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate(), 'Background portrait result did not arrive')

    def tearDown(self):
        self.assertEqual(self.slot_errors, [], "Unhandled Qt signal handler exception")

    def editor(self, layers=None):
        editor = TextEditorDialog(self.context, self.base, layers)
        editor.show()
        self.app.processEvents()
        self.addCleanup(editor.deleteLater)
        self.addCleanup(editor.close)
        return editor

    @staticmethod
    def set_geometry(editor, width=None, x=None, y=None):
        item = next(iter(editor.canvas.items_by_id.values()))
        if width is not None:
            layer = deepcopy(item.layer)
            layer.width = width
            item.update_layer(layer)
        item.setPos(item.pos().x() if x is None else x, item.pos().y() if y is None else y)
        return item

    def test_background_opacity_is_independent_of_text_opacity(self):
        layer = TextOverlay(text="A", x=10, y=10, width=150,
                            text_opacity=0, background_color="#ff0000", background_opacity=100)
        opaque = render_portrait(self.base, [layer])
        self.assertEqual(opaque.pixelColor(12, 12).getRgb()[:3], (255, 0, 0))
        self.assertEqual(opaque.pixelColor(0, 0).getRgb()[:3], (0, 0, 255))
        layer.background_opacity = 50
        half = render_portrait(self.base, [layer]).pixelColor(12, 12)
        self.assertAlmostEqual(half.red(), 128, delta=1)
        self.assertAlmostEqual(half.blue(), 127, delta=1)
        layer.background_opacity = 0
        self.assertEqual(render_portrait(self.base, [layer]), self.base)

    def test_plain_text_newlines_and_wrapping(self):
        layer = TextOverlay(text="<b>literal</b>\nsecond line", width=250)
        document = text_document(layer)
        self.assertEqual(document.toPlainText(), layer.text)
        height = document.size().height()
        layer.width = 80
        self.assertGreater(text_document(layer).size().height(), height)

    def test_preview_and_output_use_identical_text_drawing(self):
        layer = TextOverlay(text="Portrait\nTitle", x=20, y=30, width=200,
                            text_color="#ffee00", background_opacity=60, radius=8)
        canvas = TextCanvas(self.base, [layer])
        self.addCleanup(canvas.deleteLater)
        self.addCleanup(canvas.dispose)
        scene_image = QImage(self.base.size(), QImage.Format.Format_RGB32)
        scene_image.fill(QColor("white"))
        painter = QPainter(scene_image)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        canvas.scene().render(painter, QRectF(0, 0, 320, 400), canvas.sceneRect())
        painter.end()
        self.assertEqual(scene_image, canvas.composed_image())
        canvas.select_layer(layer.id)
        self.assertEqual(canvas.composed_image(), scene_image)  # Selection border is UI-only.

    def test_controls_edit_text_font_style_color_opacity_and_geometry(self):
        editor = self.editor()
        editor.text_input.setPlainText("Hello\nPortrait")
        editor.font_size.setValue(22)
        editor.bold.setChecked(True)
        editor.italic.setChecked(True)
        editor.background_opacity.setValue(0)
        editor.text_opacity.setValue(70)
        self.set_geometry(editor, width=200)
        editor.radius.setValue(8)
        editor.alignment.setCurrentIndex(editor.alignment.findData("right"))
        with patch("ui.text_editor.QColorDialog.getColor", return_value=QColor("#00ff00")):
            editor.text_color.click()
        layer = editor.layers()[0]
        self.assertEqual(layer.text, "Hello\nPortrait")
        self.assertEqual((layer.font_size, layer.width, layer.padding, layer.radius), (22, 200, 10, 8))
        self.assertTrue(layer.bold and layer.italic)
        self.assertEqual((layer.background_opacity, layer.text_opacity), (0, 70))
        self.assertEqual(layer.alignment, "right")
        self.assertEqual(layer.text_color, "#00ff00")

    def test_multiple_layers_can_be_added_selected_and_deleted(self):
        editor = self.editor()
        editor.text_input.setPlainText("First")
        editor.add_button.click()
        editor.text_input.setPlainText("Second")
        self.assertEqual([l.text for l in editor.layers()], ["First", "Second"])
        editor.layers_list.setCurrentRow(0)
        self.assertEqual(editor.text_input.toPlainText(), "First")
        editor.remove_button.click()
        self.assertEqual([l.text for l in editor.layers()], ["Second"])
        editor.remove_button.click()
        self.assertEqual(editor.layers(), [])
        self.assertFalse(editor.properties.isEnabled())
        editor.add_button.click()
        self.assertTrue(editor.properties.isEnabled())

    def test_coordinates_and_arrow_keys_stay_inside_original_image(self):
        editor = self.editor()
        editor.text_input.setPlainText("Move")
        item = self.set_geometry(editor, width=150, x=10, y=20)
        editor.canvas.setFocus()
        QTest.keyClick(editor.canvas, Qt.Key.Key_Right)
        self.assertEqual(item.pos().x(), 11)
        QTest.keyClick(editor.canvas, Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(item.pos().y(), 30)
        item.setPos(-500, 9000)
        self.assertEqual(item.pos().x(), 0)
        self.assertLessEqual(item.pos().y() + item.boundingRect().height(), 400.01)
        self.assertEqual(item.layer.y, item.pos().y())

    def test_mouse_drag_updates_position(self):
        editor = self.editor()
        editor.text_input.setPlainText("Drag")
        self.set_geometry(editor, width=150, x=20, y=40)
        self.app.processEvents()
        item = next(iter(editor.canvas.items_by_id.values()))
        start = editor.canvas.mapFromScene(item.mapToScene(item.boundingRect().center()))
        end = start + QPoint(35, 30)
        QTest.mousePress(editor.canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(editor.canvas.viewport(), end, 20)
        QTest.mouseRelease(editor.canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
        self.assertGreater(item.pos().x(), 20)
        self.assertGreater(item.pos().y(), 40)
        self.assertEqual(item.layer.x, item.pos().x())

    def test_cancel_does_not_mutate_supplied_layers(self):
        source = TextOverlay(text="Original", x=20, y=30, width=200)
        original = deepcopy(source)
        editor = self.editor([source])
        editor.text_input.setPlainText("Changed")
        self.set_geometry(editor, x=40)
        editor.reject()
        self.assertEqual(source, original)

    def test_font_file_import_renders_and_keeps_registration_after_close(self):
        editor = self.editor()
        with patch("ui.text_editor.QFileDialog.getOpenFileName",
                   return_value=(str(resource_path("fonts", "CookieRun Bold.ttf")), "")):
            editor.import_font_button.click()
        editor.text_input.setPlainText("Font")
        self.assertIn("CookieRun", editor.layers()[0].font_family)
        layers = editor.layers()
        editor.close()
        self.assertFalse(render_portrait(self.base, layers).isNull())
        self.warning.assert_not_called()

    def test_export_saves_full_resolution_rgb_bmp(self):
        editor = self.editor()
        editor.text_input.setPlainText("Export")
        output = self.root / "copy.bmp"
        with patch("ui.text_editor.QFileDialog.getSaveFileName", return_value=(str(output), "")):
            editor.export_button.click()
        with Image.open(output) as image:
            self.assertEqual(image.format, "BMP")
            self.assertEqual(image.mode, "RGB")
            self.assertEqual(image.size, (320, 400))
            self.assertEqual(image.tobytes(), to_pillow(editor.canvas.composed_image()).tobytes())
        self.warning.assert_not_called()

    def portrait_window(self):
        current, new = self.root / "current", self.root / "new"
        current.mkdir()
        new.mkdir()
        Image.new("RGB", (320, 400), "red").save(current / "character.bmp")
        Image.new("RGB", (320, 400), "blue").save(new / "mage.bmp")
        self.context.settings.update(portrait_folder=str(current), new_portrait_folder=str(new))
        window = PortraitWindow(self.context)
        def dispose():
            window.loader.stop()
            window.loader.pool.waitForDone()
            self.app.processEvents()
            window.close()
            window.deleteLater()
        self.addCleanup(dispose)
        self.wait_for(lambda: len(window.current_tiles.tiles) == len(window.new_tiles.tiles) == 1)
        window.thumbnail_clicked(window.current_tiles.tiles[0], True)
        window.thumbnail_clicked(window.new_tiles.tiles[0], False)
        self.wait_for(lambda: len(window.preview_snapshots) == 2 and not window.pending_previews)
        return window, current / "character.bmp", new / "mage.bmp"

    def test_apply_updates_preview_and_replacement_without_changing_source(self):
        window, target, source = self.portrait_window()
        original, replacement = target.read_bytes(), source.read_bytes()

        def fill_editor():
            editor = QApplication.activeModalWidget()
            editor.text_input.setPlainText("Custom title")
            self.set_geometry(editor, y=30)
            editor.dialog_buttons.button(QDialogButtonBox.StandardButton.Ok).click()

        QTimer.singleShot(20, fill_editor)
        window.edit_text_button.click()
        self.wait_for(lambda: not window.pending_previews)
        self.assertEqual(window.preview_snapshots['new']['path'], source)
        self.assertEqual(source.read_bytes(), replacement)
        self.assertEqual(target.read_bytes(), original)
        draft = window.valid_draft(source)
        expected = to_pillow(render_portrait(draft.base, draft.layers))
        window.replace_button.click()
        with Image.open(target) as actual:
            self.assertEqual(actual.size, (320, 400))
            self.assertEqual(actual.tobytes(), expected.tobytes())
        self.assertEqual(source.read_bytes(), replacement)
        backup = next((target.parent / "backup").iterdir())
        self.assertEqual(backup.read_bytes(), original)
        self.warning.assert_not_called()

    def test_reopening_then_cancelling_keeps_previous_draft(self):
        window, _target, source = self.portrait_window()

        def accept_first():
            editor = QApplication.activeModalWidget()
            editor.text_input.setPlainText("Keep this")
            editor.accept()

        QTimer.singleShot(20, accept_first)
        window.open_text_editor()
        self.wait_for(lambda: not window.pending_previews)

        def cancel_second():
            editor = QApplication.activeModalWidget()
            self.assertEqual(editor.text_input.toPlainText(), "Keep this")
            editor.text_input.setPlainText("Discard this")
            editor.reject()

        QTimer.singleShot(20, cancel_second)
        window.open_text_editor()
        self.assertEqual(window.valid_draft(source).layers[0].text, "Keep this")

    def test_english_editor_labels(self):
        self.context.translations.set_language("en")
        editor = self.editor()
        self.assertEqual(editor.windowTitle(), "Portrait Text Editor")
        self.assertEqual(editor.dialog_buttons.button(QDialogButtonBox.StandardButton.Ok).text(), "Apply to Preview")

    def test_repeated_open_edit_accept_cancel_and_destroy(self):
        layers = []
        for index in range(15):
            editor = TextEditorDialog(self.context, self.base, layers)
            editor.show()
            self.app.processEvents()
            editor.text_input.setPlainText(f"Title {index}")
            if index % 2:
                editor.reject()
            else:
                editor.accept()
                layers = editor.layers()
            editor.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.app.processEvents()
        self.assertEqual(layers[0].text, "Title 14")


if __name__ == "__main__":
    unittest.main()

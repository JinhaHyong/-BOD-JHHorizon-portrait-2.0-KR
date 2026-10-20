"""Exercise real PySide6 windows against temporary portrait/game folders."""

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
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from core.context import AppContext
from core.paths import resource_path
from core.settings import Settings
from ui.common import WindowSupport
from ui.portrait_window import PortraitWindow
from ui.styles import apply_theme


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        apply_theme(cls.app)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jhhorizon-ui-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.current = self.root / "current"
        self.new = self.root / "new"
        self.current.mkdir()
        self.new.mkdir()
        Image.new("RGB", (100, 200), "red").save(self.current / "character.bmp")
        Image.new("RGB", (100, 200), "blue").save(self.new / "mage.bmp")
        settings = Settings(self.root / "settings.json")
        settings.update(portrait_folder=str(self.current), new_portrait_folder=str(self.new),
                        font_folder=str(self.root / "game/prestringtable/font"),
                        extra_font_folders=[str(resource_path("fonts"))])
        self.context = AppContext.create(settings)
        self.info = patch.object(WindowSupport, "show_info").start()
        self.warning = patch.object(WindowSupport, "show_warning").start()
        self.addCleanup(patch.stopall)
        self.slot_errors = []
        patch.object(sys, "excepthook", side_effect=lambda *args: self.slot_errors.append(args)).start()
        self.window = PortraitWindow(self.context)
        self.window.show()
        self.addCleanup(self.close_windows)

    def wait_for(self, predicate):
        deadline = monotonic() + 5
        while not predicate() and monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate(), 'Background portrait result did not arrive')

    def tearDown(self):
        self.assertEqual(self.slot_errors, [], "Unhandled Qt signal handler exception")

    def close_windows(self):
        if self.window is not None:
            loader = self.window.loader
            loader.stop()
            loader.pool.waitForDone()
            self.app.processEvents()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_portrait_starts_directly_and_font_shortcut_reuses_window(self):
        portrait = self.window
        self.assertEqual((portrait.width(), portrait.height()), (830, 910))
        self.assertTrue(portrait.isWindow())
        self.assertTrue(portrait.isVisible())
        self.assertIsNone(portrait.parent())
        self.assertIsNone(portrait.font_window)
        portrait.font_button.click()
        font = portrait.font_window
        self.assertTrue(font.isWindow())
        self.assertTrue(font.isVisible())
        self.wait_for(lambda: portrait.current_tiles.model.rowCount() == 1)
        self.assertFalse((self.root / "game").exists())
        font.close()
        portrait.font_button.click()
        self.assertIs(portrait.font_window, font)
        self.assertTrue(font.isVisible())
        portrait.close()
        self.assertFalse(font.isVisible())
        self.assertFalse((self.root / "game").exists())
        self.warning.assert_not_called()

    def test_light_background_and_text_stay_readable_with_windows_dark_theme(self):
        self.window.open_font_manager()
        self.app.processEvents()
        for label in (self.window.current_title, self.window.font_window.title):
            self.assertEqual(label.palette().color(QPalette.ColorRole.WindowText).name(), "#111827")
        self.assertEqual(self.app.palette().color(QPalette.ColorRole.Base).name(), "#ffffff")

    def test_language_buttons_update_all_windows_and_persist(self):
        self.window.open_font_manager()
        self.window.en_btn.click()
        portrait = self.window
        self.assertEqual(portrait.current_title.text(), "Current Portrait List")
        self.assertEqual(self.window.font_window.apply_button.text(), "Apply Font")
        self.assertTrue(portrait.en_btn.isChecked())
        self.assertEqual(portrait.font_button.toolTip(), "Change Font")
        self.window.en_btn.click()
        self.assertEqual(self.context.translations.language, "en")
        self.assertTrue(self.window.en_btn.isChecked())
        portrait.kr_btn.click()
        self.assertEqual(portrait.current_title.text(), "현재 초상화 목록")
        self.assertEqual(self.context.settings.get("language"), "kr")

    def test_thumbnail_mouse_click_and_replace_button(self):
        window = self.window
        original = (self.current / "character.bmp").read_bytes()
        self.wait_for(lambda: len(window.current_tiles.tiles) == len(window.new_tiles.tiles) == 1)
        self.app.processEvents()
        for grid in (window.current_tiles, window.new_tiles):
            rect = grid.view.visualRect(grid.model.index(0))
            QTest.mouseClick(grid.view.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
        self.wait_for(lambda: len(window.preview_snapshots) == 2 and not window.pending_previews)
        self.assertIsNotNone(window.current_photo)
        self.assertIsNotNone(window.new_photo)
        window.replace_button.click()
        self.assertEqual((self.current / "character.bmp").read_bytes(), (self.new / "mage.bmp").read_bytes())
        backup = next((self.current / "backup").iterdir())
        self.assertEqual(backup.read_bytes(), original)
        self.assertIsNotNone(window.current_selected_label)
        self.assertIsNotNone(window.new_selected_label)
        self.warning.assert_not_called()
        self.info.assert_called_once()

    def test_filtering_clears_hidden_selection_then_can_select_again(self):
        window = self.window
        self.wait_for(lambda: len(window.new_tiles.tiles) == 1)
        window.thumbnail_clicked(window.new_tiles.tiles[0], False)
        window.search_input.setText("no-match")
        self.assertIsNone(window.new_photo)
        self.assertEqual(window.new_tiles.model.rowCount(), 0)
        window.search_input.clear()
        self.assertEqual(window.new_tiles.model.rowCount(), 1)
        self.wait_for(lambda: len(window.new_tiles.tiles) == 1)
        window.thumbnail_clicked(window.new_tiles.tiles[0], False)
        self.assertIsNotNone(window.new_photo)
        self.warning.assert_not_called()

    def test_font_preview_keeps_path_and_apply_uses_it(self):
        self.window.open_font_manager()
        window = self.window.font_window
        bundled = resource_path("fonts", "NanumGothic-Bold.ttf")
        for index in range(window.font_list.count()):
            item = window.font_list.item(index)
            if Path(item.data(Qt.ItemDataRole.UserRole)) == bundled:
                window.font_list.setCurrentItem(item)
                break
        else:
            self.fail("Bundled font not discovered")
        self.assertEqual(window.current_font_path, bundled)
        self.assertIsNotNone(window.preview_qfont)
        window.preview_input.setText("<b>미리보기</b>")
        self.assertEqual(window.preview_label.text(), "<b>미리보기</b>")
        self.assertFalse((self.root / "game").exists())
        (self.root / "game").mkdir()
        (self.root / "game/BlackDesertLauncher.exe").touch()
        window.apply_button.click()
        self.assertEqual((window.font_path / "pearl.ttf").read_bytes(), bundled.read_bytes())
        window.apply_button.click()
        self.assertEqual(len(list((window.font_path / "backup").iterdir())), 1)
        self.warning.assert_not_called()

    def test_cancelled_game_folder_selection_creates_nothing(self):
        self.window.open_font_manager()
        window = self.window.font_window
        window.current_font_path = resource_path("fonts", "NanumGothic-Bold.ttf")
        with patch("ui.font_window.GameLocationDialog") as selector:
            selector.return_value.exec.return_value = QDialog.DialogCode.Rejected
            selector.return_value.game_root = None
            window.apply_font()
        self.assertFalse((self.root / "game").exists())

    def test_folder_buttons_load_and_remember_new_locations(self):
        window = self.window
        with patch("ui.portrait_window.QFileDialog.getExistingDirectory", return_value=str(self.new)):
            window.current_folder_btn.click()
        self.assertEqual(window.photo_path, self.new)
        self.assertEqual(self.context.settings.get("portrait_folder"), str(self.new))
        self.wait_for(lambda: window.current_tiles.model.rowCount() == 1)
        with patch("ui.portrait_window.QFileDialog.getExistingDirectory", return_value=str(self.current)):
            window.new_folder_btn.click()
        self.assertEqual(window.new_path, self.current)
        self.assertEqual(self.context.settings.get("new_portrait_folder"), str(self.current))
        self.wait_for(lambda: window.new_tiles.model.rowCount() == 1)

    def test_selecting_game_installation_applies_and_remembers_font_folder(self):
        self.window.open_font_manager()
        window = self.window.font_window
        window.current_font_path = resource_path("fonts", "NanumGothic-Bold.ttf")
        installation = self.root / "selected-game"
        installation.mkdir()
        (installation / 'BlackDesertLauncher.exe').touch()
        with patch("ui.font_window.GameLocationDialog") as selector:
            selector.return_value.exec.return_value = QDialog.DialogCode.Accepted
            selector.return_value.game_root = installation
            window.apply_font()
        target = installation / "prestringtable/font/pearl.ttf"
        self.assertEqual(target.read_bytes(), window.current_font_path.read_bytes())
        self.assertEqual(self.context.settings.get("font_folder"), str(target.parent))
        self.warning.assert_not_called()

    def test_real_shared_dialog_closes_via_ok_button(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QPushButton
        from ui.dialogs import show_message

        def accept():
            dialog = QApplication.activeModalWidget()
            self.assertIsInstance(dialog, QDialog)
            dialog.findChild(QPushButton).click()

        QTimer.singleShot(20, accept)
        show_message(self.window, self.context.translations, "테스트 알림")
        self.assertIsNone(QApplication.activeModalWidget())

    def test_resources_resolve_from_another_working_directory(self):
        original = Path.cwd()
        try:
            os.chdir(self.root)
            other = AppContext.create(Settings(self.root / "second-settings.json"))
            self.assertEqual(other.translations.text("start_window", "portrait_btn"), "초상화 교체")
            self.assertTrue(resource_path("아이콘.ico").is_file())
        finally:
            os.chdir(original)


if __name__ == "__main__":
    unittest.main()

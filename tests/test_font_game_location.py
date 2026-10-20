"""Only temporary installations are used for game-location regression tests."""

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication, QDialog

from core.context import AppContext
from core.paths import resource_path
from core.settings import Settings
from services.font_service import FontService
from ui.common import WindowSupport
from ui.font_window import FontWindow


class FontGameLocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='jhnode-font-location-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.old_root = self.root / 'old-game'
        self.old_root.mkdir()
        self.settings = Settings(self.root / 'settings.json')
        self.settings.update(font_folder=str(self.old_root / 'prestringtable/font'))
        self.context = AppContext.create(self.settings)
        self.warning = patch.object(WindowSupport, 'show_warning').start()
        self.info = patch.object(WindowSupport, 'show_info').start()
        self.addCleanup(patch.stopall)
        self.window = FontWindow(self.context)
        self.addCleanup(self.window.deleteLater)
        self.addCleanup(self.window.close)
        self.source = resource_path('fonts', 'NanumGothic-Bold.ttf')
        self.window.current_font_path = self.source
        self.window.update_apply_state()

    def selector(self, root=None):
        mocked = patch('ui.font_window.GameLocationDialog').start()
        mocked.return_value.exec.return_value = (QDialog.DialogCode.Accepted if root is not None
                                                  else QDialog.DialogCode.Rejected)
        mocked.return_value.game_root = root
        return mocked

    def test_residual_empty_folder_opens_selector_and_cancel_writes_nothing(self):
        chooser = self.selector()
        self.assertEqual(self.window.location_status.text(), self.window.word('ui_location_missing'))
        self.window.apply_button.click()
        chooser.assert_called_once()
        self.assertFalse((self.old_root / 'prestringtable').exists())
        self.info.assert_not_called()

    def test_invalid_accepted_location_is_not_saved_or_written(self):
        invalid = self.root / 'not-a-game'
        invalid.mkdir()
        self.selector(invalid)
        previous = self.settings.get('font_folder')
        self.window.apply_button.click()
        self.assertEqual(self.settings.get('font_folder'), previous)
        self.assertFalse((invalid / 'prestringtable').exists())
        self.warning.assert_called_once()
        self.info.assert_not_called()

    def test_verified_client_location_is_applied_and_remembered(self):
        valid = self.root / 'selected-game'
        (valid / 'bin64').mkdir(parents=True)
        (valid / 'bin64/BlackDesert64.exe').touch()
        self.selector(valid)
        self.window.apply_button.click()
        target = valid / 'prestringtable/font/pearl.ttf'
        self.assertEqual(target.read_bytes(), self.source.read_bytes())
        self.assertEqual(self.settings.get('font_folder'), str(target.parent))
        self.assertFalse((self.old_root / 'prestringtable').exists())
        self.info.assert_called_once()
        self.warning.assert_not_called()

    def test_service_rechecks_location_before_creating_any_files(self):
        with self.assertRaises(ValueError):
            FontService().apply(self.source, self.old_root / 'prestringtable/font')
        self.assertFalse((self.old_root / 'prestringtable').exists())

    def test_apply_button_has_no_caption_and_is_vertically_centered(self):
        self.window.show()
        self.app.processEvents()
        self.assertFalse(hasattr(self.window, 'selected_label'))
        button = self.window.apply_button
        self.assertLessEqual(abs(button.geometry().center().y() - button.parentWidget().rect().center().y()), 2)


if __name__ == '__main__':
    unittest.main()

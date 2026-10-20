"""External font discovery leaves font selection and user data unchanged."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from core.context import AppContext
from core.paths import resource_path
from core.portrait_edit import TextOverlay
from core.settings import Settings
from ui.font_sources import FONT_SITE_URL
from ui.font_window import FontWindow
from ui.text_editor import TextEditorDialog, restore_layer_fonts


class FontSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='jhnode-font-site-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.context = AppContext.create(Settings(self.root / 'settings.json'))
        self.font = resource_path('fonts', 'NanumGothic-Bold.ttf')
        self.context.settings.update(extra_font_files=[str(self.font)])

    def test_manager_link_opens_site_only_on_click_and_keeps_selection(self):
        with patch('ui.font_sources.QDesktopServices.openUrl', return_value=True) as opened:
            window = FontWindow(self.context)
            try:
                opened.assert_not_called()
                self.assertFalse(hasattr(window, 'tabs'))
                window.current_font_path = self.font
                window.font_site_button.click()
                self.assertEqual(opened.call_args.args[0].toString(), FONT_SITE_URL)
                self.assertEqual(window.current_font_path, self.font)
            finally:
                window.close()
                window.deleteLater()

    def test_editor_link_keeps_box_content_and_selected_font(self):
        image = QImage(320, 400, QImage.Format.Format_RGB32)
        image.fill(0)
        with patch('ui.font_sources.QDesktopServices.openUrl', return_value=True) as opened:
            editor = TextEditorDialog(self.context, image, [TextOverlay(text='Keep text')])
            try:
                editor.use_font_file(self.font)
                before = editor.layers()[0]
                opened.assert_not_called()
                editor.font_site_button.click()
                self.assertEqual(opened.call_args.args[0].toString(), FONT_SITE_URL)
                self.assertEqual(editor.layers()[0], before)
            finally:
                editor.reject()
                editor.deleteLater()

    def test_browser_failure_has_a_usable_fallback_address(self):
        window = FontWindow(self.context)
        try:
            with patch('ui.font_sources.QDesktopServices.openUrl', return_value=False), patch.object(window, 'show_warning') as warning:
                window.font_site_button.click()
            self.assertIn(FONT_SITE_URL, warning.call_args.args[0])
        finally:
            window.close()
            window.deleteLater()

    def test_font_site_button_tracks_language_changes(self):
        window = FontWindow(self.context)
        try:
            self.assertIn('눈누', window.font_site_button.text())
            self.context.translations.set_language('en')
            self.assertIn('Noonnu', window.font_site_button.text())
        finally:
            window.close()
            window.deleteLater()

    def test_draft_from_old_bundled_font_recovers_without_losing_content(self):
        layer = TextOverlay(text='Keep text', x=50, y=60,
                            font_file='C:/Temp/_MEI123/resources/fonts/CookieRun Bold.ttf')
        restore_layer_fonts([layer])
        self.assertEqual(Path(layer.font_file), self.font.resolve())
        self.assertEqual((layer.text, layer.x, layer.y), ('Keep text', 50, 60))

    def test_bundle_retains_original_ofl_notice_and_has_no_online_catalogue(self):
        self.assertIn(b'SIL OPEN FONT LICENSE', resource_path('font_licenses', 'NanumGothic-OFL.txt').read_bytes())
        self.assertFalse(resource_path('online_font_catalog.json').exists())
        self.assertEqual([p.name for p in resource_path('fonts').glob('*.ttf')], ['NanumGothic-Bold.ttf'])


if __name__ == '__main__': unittest.main()

"""Selected font faces survive rendering, storage, templates and bulk edits."""

from copy import deepcopy
from dataclasses import asdict
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtGui import QColor, QFontDatabase, QImage, QRawFont
from PySide6.QtWidgets import QApplication

from core.context import AppContext
from core.portrait_edit import TextOverlay
from core.settings import Settings
from core.text_presets import TextPresetStore, decode_layers
import ui.font_registry as registry
from ui.font_registry import font_from_file, register_font, registered_path, set_layer_font_file
from ui.text_canvas import render_portrait, text_document
from ui.text_editor import TextEditorDialog, restore_layer_fonts


class FontVariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        folder = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
        cls.paths = {name: folder / filename for name, filename in (
            ('regular', 'arial.ttf'), ('bold', 'arialbd.ttf'),
            ('italic', 'ariali.ttf'), ('bold_italic', 'arialbi.ttf'))}
        if not all(path.is_file() for path in cls.paths.values()):
            raise unittest.SkipTest('Windows Arial faces are needed for face matching checks')
        cls.old_fonts = dict(registry._registered_fonts)
        cls.old_paths = {family: list(paths) for family, paths in registry._family_paths.items()}
        for path in cls.paths.values():
            register_font(str(path))

    @classmethod
    def tearDownClass(cls):
        for path, entry in registry._registered_fonts.items():
            if path not in cls.old_fonts:
                QFontDatabase.removeApplicationFont(entry[0])
        registry._registered_fonts.clear()
        registry._registered_fonts.update(cls.old_fonts)
        registry._family_paths.clear()
        registry._family_paths.update(cls.old_paths)

    def layer(self, face):
        layer = TextOverlay(text='MMMM WWWW', font_size=40, width=310,
                            height=100, background_opacity=0)
        set_layer_font_file(layer, self.paths[face])
        return layer

    def assert_face(self, layer, face):
        expected = QRawFont(str(self.paths[face]), 40)
        actual = QRawFont.fromFont(text_document(layer).defaultFont())
        self.assertEqual(actual.familyName(), expected.familyName())
        self.assertEqual(actual.styleName(), expected.styleName())
        self.assertEqual(actual.weight(), expected.weight())
        self.assertEqual(actual.style(), expected.style())

    def test_file_helper_and_renderer_keep_each_selected_face(self):
        for face, path in self.paths.items():
            with self.subTest(face=face):
                expected = QRawFont(str(path), 40)
                actual = QRawFont.fromFont(font_from_file(path, pixel_size=40))
                self.assertEqual(actual.styleName(), expected.styleName())
                self.assertEqual(actual.weight(), expected.weight())
                self.assert_face(self.layer(face), face)

    def test_family_lookup_does_not_become_the_last_registered_bold_italic(self):
        family = register_font(str(self.paths['bold_italic']))
        self.assertEqual(registered_path(family), str(self.paths['regular'].resolve()))

    def test_checkbox_effects_add_to_and_restore_the_original_face(self):
        regular = self.layer('regular')
        regular.bold = True
        self.assert_face(regular, 'bold')
        regular.italic = True
        self.assert_face(regular, 'bold_italic')
        regular.bold = regular.italic = False
        self.assert_face(regular, 'regular')
        for face in ('bold', 'italic', 'bold_italic'):
            layer = self.layer(face)
            self.assertFalse(layer.bold or layer.italic)
            self.assert_face(layer, face)
            layer.bold = layer.italic = True
            self.assert_face(layer, 'bold_italic')
            layer.bold = layer.italic = False
            self.assert_face(layer, face)

    def test_full_image_uses_the_selected_file_face(self):
        image = QImage(320, 120, QImage.Format.Format_RGB32)
        image.fill(QColor('black'))
        self.assertNotEqual(render_portrait(image, [self.layer('regular')]),
                            render_portrait(image, [self.layer('bold')]))

    def test_saved_draft_template_and_batch_keep_face_metadata(self):
        with tempfile.TemporaryDirectory(prefix='jhnode-font-face-') as temporary:
            root = Path(temporary)
            settings = Settings(root / 'settings.json')
            store = TextPresetStore(settings)
            selected = self.layer('bold_italic')
            settings.update(**store.updates_for_apply(root / 'portrait.bmp', (1, 2), 320, 400, [selected]))
            reopened = TextPresetStore(Settings(settings.path))
            draft = restore_layer_fonts(reopened.load_draft(root / 'portrait.bmp', (1, 2)))
            self.assert_face(draft[0], 'bold_italic')
            self.assertEqual(asdict(draft[0]), asdict(selected))
            template = reopened.template_for(320, 400)
            self.assertEqual(template[0].text, '')
            self.assert_face(template[0], 'bold_italic')
            source = {'width': 320, 'height': 400, 'layers': [asdict(selected)]}
            same_count = store.batch_layers_for(source, 320, 400, [TextOverlay(text='Keep me')])
            self.assertEqual(same_count[0].text, 'Keep me')
            self.assert_face(same_count[0], 'bold_italic')
            changed_count = store.batch_layers_for(source, 320, 400, [])
            self.assertEqual(changed_count[0].text, '')
            self.assert_face(changed_count[0], 'bold_italic')

    def test_legacy_draft_recovers_metadata_from_its_font_file(self):
        legacy = {'text': 'Old draft', 'font_family': 'Arial',
                  'font_file': str(self.paths['italic'])}
        layers = restore_layer_fonts(decode_layers([legacy]))
        self.assertEqual(layers[0].font_slant, 'italic')
        self.assert_face(layers[0], 'italic')

    def test_editor_keeps_face_after_text_edits_checkbox_changes_and_reopen(self):
        with tempfile.TemporaryDirectory(prefix='jhnode-font-editor-') as temporary:
            root = Path(temporary)
            context = AppContext.create(Settings(root / 'settings.json'))
            image = QImage(320, 400, QImage.Format.Format_RGB32)
            image.fill(QColor('black'))
            with patch('ui.text_editor.load_downloaded_fonts'):
                editor = TextEditorDialog(context, image)
            try:
                editor.use_font_file(self.paths['bold_italic'])
                editor.text_input.setPlainText('Keep chosen face')
                editor.bold.setChecked(True)
                editor.bold.setChecked(False)
                editor.italic.setChecked(True)
                editor.italic.setChecked(False)
                saved = deepcopy(editor.layers())
                self.assert_face(saved[0], 'bold_italic')
            finally:
                editor.reject()
                editor.deleteLater()
            with patch('ui.text_editor.load_downloaded_fonts'):
                reopened = TextEditorDialog(context, image, saved)
            try:
                self.assert_face(reopened.layers()[0], 'bold_italic')
                self.assertFalse(reopened.bold.isChecked() or reopened.italic.isChecked())
            finally:
                reopened.reject()
                reopened.deleteLater()

    def test_invalid_saved_face_metadata_is_rejected(self):
        for values in ({'font_weight': -1}, {'font_weight': True},
                       {'font_weight': 1001}, {'font_style': []}, {'font_slant': 'bad'}):
            self.assertEqual(decode_layers([{'text': 'bad', **values}]), [])


if __name__ == '__main__':
    unittest.main()

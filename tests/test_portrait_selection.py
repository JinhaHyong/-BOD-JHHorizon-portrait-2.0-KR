"""Regression checks for visible portrait selection and the actual write target."""

import os
from pathlib import Path
import sys
import tempfile
from time import monotonic
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image
from PySide6.QtCore import QCoreApplication, QEvent, QItemSelectionModel, QSignalBlocker, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QAbstractItemView

from core.context import AppContext
from core.settings import Settings
from ui.common import WindowSupport
from ui.portrait_grid import PortraitGrid, PortraitGridView
from ui.portrait_window import PortraitWindow
from ui.styles import apply_theme


class PortraitSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')
        apply_theme(cls.app)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='jhnode-selection-')
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        for side in ('current', 'new'):
            folder = self.root / side
            folder.mkdir()
            for number in range(3):
                Image.new('RGB', (320, 400), (50 + number * 55, 60, 150 if side == 'current' else 80)).save(
                    folder / f'{number}-portrait.bmp')
        settings = Settings(self.root / 'settings.json')
        settings.update(portrait_folder=str(self.root / 'current'),
                        new_portrait_folder=str(self.root / 'new'))
        self.context = AppContext.create(settings)
        self.info = patch.object(WindowSupport, 'show_info').start()
        self.warning = patch.object(WindowSupport, 'show_warning').start()
        self.slot_errors = []
        patch.object(sys, 'excepthook', side_effect=lambda *args: self.slot_errors.append(args)).start()
        self.addCleanup(patch.stopall)
        self.window = PortraitWindow(self.context)
        self.addCleanup(self.dispose_window)
        self.window.show()
        self.wait_for(lambda: len(self.window.current_tiles.tiles) == len(self.window.new_tiles.tiles) == 3)
        self.app.processEvents()

    def dispose_window(self):
        self.window.loader.stop()
        self.window.loader.pool.waitForDone()
        self.app.processEvents()
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def tearDown(self):
        self.assertEqual(self.slot_errors, [], 'Unhandled Qt callback exception')

    def wait_for(self, predicate):
        deadline = monotonic() + 5
        while not predicate() and monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate(), 'Portrait selection/preview did not synchronize')

    def parts(self, side):
        return ((self.window.current_tiles, self.window.current_scroll)
                if side == 'current' else (self.window.new_tiles, self.window.new_scroll))

    def click(self, side, row):
        tiles, view = self.parts(side)
        self.wait_for(lambda: view.visualRect(tiles.model.index(row)).isValid())
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton,
                         pos=view.visualRect(tiles.model.index(row)).center())
        self.wait_for(lambda: self.window.selection_matches_preview(side)
                      and side not in self.window.pending_previews)

    def assert_selected(self, side, row):
        tiles, view = self.parts(side)
        expected = tiles.model.entries[row]
        actual = self.window.current_photo if side == 'current' else self.window.new_photo
        self.assertEqual(view.currentIndex().row(), row)
        self.assertEqual([index.row() for index in view.selectionModel().selectedRows()], [row])
        self.assertIs(tiles.selected, expected)
        self.assertEqual(actual, expected.file_path)
        self.assertEqual(self.window.preview_snapshots[side]['path'], expected.file_path)
        self.assertTrue(self.window.selection_matches_preview(side))

    def test_mouse_and_keyboard_share_one_preview_request_per_selection(self):
        for side in ('current', 'new'):
            tiles, view = self.parts(side)
            with patch.object(self.window.loader, 'request_preview',
                              wraps=self.window.loader.request_preview) as requests:
                self.click(side, 0)
                self.assertEqual(requests.call_count, 1)
                self.assert_selected(side, 0)
                requests.reset_mock()
                view.setFocus()
                QTest.keyClick(view, Qt.Key.Key_Right)
                self.wait_for(lambda: self.window.selection_matches_preview(side)
                              and side not in self.window.pending_previews)
                self.assert_selected(side, 1)
                self.assertEqual(requests.call_count, 1)
                self.click(side, 1)
                self.assertEqual(requests.call_count, 1, 'Clicking the selected card reloaded the image')

    def test_filter_reset_preserves_selection_without_reloading(self):
        self.click('new', 1)
        expected = self.window.new_photo
        with patch.object(self.window.loader, 'request_preview',
                          wraps=self.window.loader.request_preview) as requests:
            self.window.arrange_thumbnails(False, '1-')
            self.assertEqual(self.window.new_photo, expected)
            self.assert_selected('new', 0)
            self.window.arrange_thumbnails(False, '')
            self.assert_selected('new', 1)
            self.assertEqual(requests.call_count, 0)

    def test_filter_hiding_selection_clears_preview_and_paths(self):
        self.click('new', 1)
        self.window.arrange_thumbnails(False, '0-')
        self.assertIsNone(self.window.new_photo)
        self.assertIsNone(self.window.new_selected_label)
        self.assertIsNone(self.window.new_tiles.selected)
        self.assertEqual(self.window.new_scroll.selectionModel().selectedRows(), [])
        self.assertNotIn('new', self.window.preview_snapshots)
        self.assertNotIn('new', self.window.pending_previews)
        self.assertFalse(self.window.edit_text_button.isEnabled())

    def test_native_clear_selection_clears_actual_selection(self):
        self.click('current', 0)
        self.window.current_scroll.clearSelection()
        self.assertIsNone(self.window.current_photo)
        self.assertIsNone(self.window.current_tiles.selected)
        self.assertNotIn('current', self.window.preview_snapshots)

    def test_fast_keyboard_changes_discard_older_preview_results(self):
        self.click('new', 0)
        self.window.new_scroll.setFocus()
        QTest.keyClick(self.window.new_scroll, Qt.Key.Key_Right)
        QTest.keyClick(self.window.new_scroll, Qt.Key.Key_Right)
        QTest.keyClick(self.window.new_scroll, Qt.Key.Key_Left)
        self.wait_for(lambda: self.window.selection_matches_preview('new')
                      and 'new' not in self.window.pending_previews)
        self.assert_selected('new', 1)

    def test_failed_preview_can_retry_same_card_without_duplicate_requests(self):
        self.click('new', 0)
        self.window.clear_preview('new')
        with patch.object(self.window.loader, 'request_preview',
                          wraps=self.window.loader.request_preview) as requests:
            self.click('new', 0)
            self.assertEqual(requests.call_count, 1)
        self.assert_selected('new', 0)

    def test_keyboard_selection_replaces_only_highlighted_fixture(self):
        for side in ('current', 'new'):
            self.click(side, 0)
            _tiles, view = self.parts(side)
            view.setFocus()
            QTest.keyClick(view, Qt.Key.Key_Right)
            self.wait_for(lambda name=side: self.window.selection_matches_preview(name)
                          and name not in self.window.pending_previews)
            self.assert_selected(side, 1)
        untouched = self.root / 'current' / '0-portrait.bmp'
        destination = self.root / 'current' / '1-portrait.bmp'
        source = self.root / 'new' / '1-portrait.bmp'
        untouched_bytes, original = untouched.read_bytes(), destination.read_bytes()
        expected = source.read_bytes()
        self.window.replace_photo()
        self.assertEqual(destination.read_bytes(), expected)
        self.assertEqual(untouched.read_bytes(), untouched_bytes)
        backups = list((destination.parent / 'backup').glob('*.bmp'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)

    def test_replace_guard_resynchronizes_qt_selection_before_any_write(self):
        self.click('current', 0)
        self.click('new', 0)
        with QSignalBlocker(self.window.current_scroll.selectionModel()):
            self.window.current_scroll.selectionModel().setCurrentIndex(
                self.window.current_tiles.model.index(1), QItemSelectionModel.SelectionFlag.ClearAndSelect)
        self.assertFalse(self.window.selection_matches_preview('current'))
        with patch.object(self.context.portraits, 'replace') as replace:
            self.window.replace_photo()
            replace.assert_not_called()
        self.wait_for(lambda: self.window.selection_matches_preview('current')
                      and 'current' not in self.window.pending_previews)
        self.assert_selected('current', 1)
        self.assertFalse((self.root / 'current' / 'backup').exists())

    def test_replace_guard_rejects_a_snapshot_for_another_photo(self):
        self.click('current', 0)
        self.click('new', 0)
        self.window.preview_snapshots['new']['path'] = self.root / 'new' / '1-portrait.bmp'
        with patch.object(self.context.portraits, 'replace') as replace:
            self.window.replace_photo()
            replace.assert_not_called()
        self.wait_for(lambda: self.window.selection_matches_preview('new')
                      and 'new' not in self.window.pending_previews)
        self.assert_selected('new', 0)

    def test_batch_grid_can_keep_multiple_selected_photos(self):
        view = PortraitGridView()
        grid = PortraitGrid(view)
        self.addCleanup(view.deleteLater)
        view.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        grid.set_records([{'path': tile.file_path, 'stamp': tile.stamp}
                          for tile in self.window.new_tiles.tiles])
        changes = []
        grid.selection_changed.connect(changes.append)
        for row in (0, 1):
            view.selectionModel().select(grid.model.index(row), QItemSelectionModel.SelectionFlag.Select)
        self.assertEqual([index.row() for index in view.selectionModel().selectedRows()], [0, 1])
        self.assertEqual(changes, [])
        self.assertIsNone(grid.selected)


if __name__ == '__main__':
    unittest.main()

"""Onefile extraction must not become the root for user-owned folders."""

import os
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch


PATHS = Path(__file__).resolve().parents[1] / 'core/paths.py'


class RuntimePathTests(unittest.TestCase):
    def test_source_mode_uses_project_resources_and_app_root(self):
        with patch.object(sys, 'frozen', False, create=True):
            paths = runpy.run_path(str(PATHS))
        self.assertEqual(paths['APP_ROOT'], PATHS.parent.parent)
        self.assertEqual(paths['RESOURCE_ROOT'], PATHS.parent.parent / 'resources')

    def test_frozen_mode_separates_exe_folder_from_packaged_resources(self):
        exe = Path('C:/One File/한글/JHnode.exe').resolve()
        bundle = Path('C:/Temp/_MEI-one').resolve()
        with patch.object(sys, 'frozen', True, create=True), \
                patch.object(sys, 'executable', str(exe)), \
                patch.object(sys, '_MEIPASS', str(bundle), create=True):
            paths = runpy.run_path(str(PATHS))
        self.assertEqual(paths['APP_ROOT'], exe.parent)
        self.assertEqual(paths['RESOURCE_ROOT'], bundle / 'resources')

    def test_reextracting_does_not_move_settings_or_new_portrait_root(self):
        exe = Path('C:/One File/JHnode.exe').resolve()
        appdata = Path('C:/Users/Test/AppData/Local').resolve()
        locations = []
        for folder in ('_MEI-first', '_MEI-second'):
            with patch.object(sys, 'frozen', True, create=True), \
                    patch.object(sys, 'executable', str(exe)), \
                    patch.object(sys, '_MEIPASS', str(Path('C:/Temp') / folder), create=True), \
                    patch.dict(os.environ, {'LOCALAPPDATA': str(appdata)}):
                paths = runpy.run_path(str(PATHS))
                locations.append((paths['APP_ROOT'], paths['settings_file']()))
        self.assertEqual(locations[0], locations[1])
        self.assertEqual(locations[0][1], appdata / 'JHHorizon/PortraitManager/settings.json')

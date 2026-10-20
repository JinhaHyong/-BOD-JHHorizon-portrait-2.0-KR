"""Settings recovery and independent writers use temporary JSON files only."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.settings import Settings


class SettingsRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='jhnode-settings-')
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'settings.json'

    def test_stale_writer_preserves_new_photo_drafts_and_history(self):
        first, stale = Settings(self.path), Settings(self.path)
        drafts = {'portrait.bmp': {'layers': [{'text': 'saved name'}]}}
        history = [{'id': 'first-setting'}]
        first.update(portrait_text_drafts=drafts, portrait_text_history=history)
        stale.update(language='en')
        saved = Settings(self.path)
        self.assertEqual(saved.get('portrait_text_drafts'), drafts)
        self.assertEqual(saved.get('portrait_text_history'), history)
        self.assertEqual(saved.get('language'), 'en')
        self.assertEqual(stale.get('portrait_text_drafts'), drafts)

    def test_corrupt_main_recovers_last_valid_backup_without_writing_on_load(self):
        settings = Settings(self.path)
        drafts = {'portrait.bmp': {'layers': [{'text': 'saved name'}]}}
        settings.update(language='kr', portrait_text_drafts=drafts)
        settings.update(theme_mode='dark')
        corrupt = '{interrupted-json'
        self.path.write_text(corrupt, encoding='utf-8')
        with self.assertLogs('core.settings', level='WARNING'):
            recovered = Settings(self.path)
        self.assertEqual(recovered.get('portrait_text_drafts'), drafts)
        self.assertEqual(recovered.get('language'), 'kr')
        self.assertEqual(self.path.read_text(encoding='utf-8'), corrupt)
        recovered.update(language='en')
        self.assertEqual(Settings(self.path).get('portrait_text_drafts'), drafts)
        self.assertEqual(json.loads(recovered.backup_path.read_text(encoding='utf-8')),
                         {'language': 'kr', 'portrait_text_drafts': drafts})

    def test_missing_main_recovers_backup(self):
        settings = Settings(self.path)
        settings.update(language='en')
        settings.update(theme_mode='dark')
        self.path.unlink()
        with self.assertLogs('core.settings', level='WARNING'):
            recovered = Settings(self.path)
        self.assertEqual(recovered.get('language'), 'en')
        self.assertFalse(self.path.exists())

    def test_failed_backup_preserves_main_and_in_memory_state(self):
        settings = Settings(self.path)
        settings.update(language='kr')
        original = self.path.read_bytes()
        with patch('core.settings.os.replace', side_effect=PermissionError('backup locked')):
            with self.assertRaises(OSError):
                settings.update(language='en')
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(settings.get('language'), 'kr')
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_failed_main_write_retains_previous_file_and_valid_backup(self):
        import os
        settings = Settings(self.path)
        settings.update(language='kr', portrait_text_drafts={'saved': {}})
        original = self.path.read_bytes()
        replace = os.replace

        def fail_only_main(source, target):
            if Path(target) == self.path:
                raise PermissionError('main locked')
            return replace(source, target)

        with patch('core.settings.os.replace', side_effect=fail_only_main):
            with self.assertRaises(OSError):
                settings.update(language='en')
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(settings.get('language'), 'kr')
        self.assertEqual(json.loads(settings.backup_path.read_text(encoding='utf-8')),
                         json.loads(original))
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_unreadable_latest_file_does_not_get_overwritten_from_stale_memory(self):
        settings = Settings(self.path)
        settings.update(language='kr')
        original = self.path.read_bytes()
        with patch.object(Settings, '_read', side_effect=PermissionError('cannot read latest')):
            with self.assertRaises(OSError):
                settings.update(language='en')
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(settings.get('language'), 'kr')


if __name__ == '__main__':
    unittest.main()

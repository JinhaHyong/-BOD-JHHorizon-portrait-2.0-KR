"""File operations run only against temporary fixtures, never game folders."""

from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.settings import Settings
from core.paths import resource_path
from services.backup_service import BackupService
from services.font_service import FontService
from services.portrait_service import PortraitService


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jhhorizon-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.portraits = PortraitService()

    def image(self, name, color="red", size=(100, 120)):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, color).save(path, format="BMP")
        return path

    def test_portrait_replacement_preserves_name_and_backs_up_exact_original(self):
        current = self.image("game/character.bmp", "red")
        source = self.image("new/mage.bmp", "blue")
        original = current.read_bytes()
        backup = self.portraits.replace(current, source)
        self.assertEqual(current.name, "character.bmp")
        self.assertEqual(current.read_bytes(), source.read_bytes())
        self.assertEqual(backup.parent, current.parent / "backup")
        self.assertEqual(backup.read_bytes(), original)

    def test_repeated_replacements_keep_separate_backups(self):
        current = self.image("game/a.bmp")
        source = self.image("new/b.bmp", "blue")
        first = self.portraits.replace(current, source)
        second = self.portraits.replace(current, source)
        self.assertNotEqual(first, second)
        self.assertEqual(len(list(first.parent.iterdir())), 2)

    def test_oversized_and_disguised_images_do_not_change_target(self):
        current = self.image("game/a.bmp")
        original = current.read_bytes()
        for source in (self.image("wide.bmp", size=(625, 804)),
                       self.image("tall.bmp", size=(624, 805))):
            with self.assertRaises(ValueError):
                self.portraits.replace(current, source)
        disguised = self.root / "fake.bmp"
        Image.new("RGB", (20, 20)).save(disguised, format="PNG")
        with self.assertRaises(ValueError):
            self.portraits.replace(current, disguised)
        self.assertEqual(current.read_bytes(), original)
        self.assertFalse((current.parent / "backup").exists())

    def test_same_file_replacement_is_rejected(self):
        current = self.image("a.bmp")
        original = current.read_bytes()
        with self.assertRaises(ValueError):
            self.portraits.replace(current, current)
        self.assertEqual(current.read_bytes(), original)
        self.assertFalse((self.root / "backup").exists())

    def test_missing_source_preserves_original(self):
        current = self.image("a.bmp")
        original = current.read_bytes()
        with self.assertRaises(FileNotFoundError):
            self.portraits.replace(current, self.root / "missing.bmp")
        self.assertEqual(current.read_bytes(), original)

    def test_failed_backup_leaves_target_untouched_and_removes_staging_file(self):
        current = self.image("a.bmp")
        source = self.image("b.bmp", "blue")
        original = current.read_bytes()
        with patch.object(self.portraits.backups, "backup", side_effect=PermissionError("locked")):
            with self.assertRaises(PermissionError):
                self.portraits.replace(current, source)
        self.assertEqual(current.read_bytes(), original)
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_failed_final_replace_preserves_original_and_backup(self):
        current = self.image("a.bmp")
        source = self.image("b.bmp", "blue")
        original = current.read_bytes()
        with patch("services.backup_service.os.replace", side_effect=PermissionError("locked")):
            with self.assertRaises(PermissionError):
                self.portraits.replace(current, source)
        self.assertEqual(current.read_bytes(), original)
        backups = list((self.root / "backup").iterdir())
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_failed_staging_copy_preserves_original_without_creating_backup(self):
        current = self.image("a.bmp")
        source = self.image("b.bmp", "blue")
        original = current.read_bytes()
        with patch("services.backup_service.shutil.copy2", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.portraits.replace(current, source)
        self.assertEqual(current.read_bytes(), original)
        self.assertFalse((self.root / "backup").exists())
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_readonly_source_remains_unchanged_and_installed_file_is_writable(self):
        current = self.image("a.bmp")
        source = self.image("b.bmp", "blue")
        source.chmod(stat.S_IREAD)
        self.addCleanup(source.chmod, stat.S_IWRITE)
        self.portraits.replace(current, source)
        self.assertEqual(current.read_bytes(), source.read_bytes())
        self.assertTrue(current.stat().st_mode & stat.S_IWRITE)

    def test_partial_backup_is_removed_when_copy_fails(self):
        current = self.image("a.bmp")
        original = current.read_bytes()

        def partial_copy(source, destination):
            Path(destination).write_bytes(b"incomplete")
            raise OSError("disk full")

        with patch("services.backup_service.shutil.copy2", side_effect=partial_copy):
            with self.assertRaises(OSError):
                BackupService().backup(current)
        self.assertEqual(current.read_bytes(), original)
        self.assertEqual(list((self.root / "backup").iterdir()), [])

    def test_listing_filters_case_insensitively_and_skips_invalid_images(self):
        valid = self.image("Mage.BMP", size=(624, 804))
        self.image("warrior.bmp")
        self.image("Mage-large.bmp", size=(625, 804))
        (self.root / "Mage-bad.bmp").write_bytes(b"broken")
        self.assertEqual(self.portraits.list_portraits(self.root, "MAGE"), [valid])
        self.assertEqual(self.portraits.list_portraits(self.root / "absent"), [])

    def test_preview_is_detached_and_does_not_modify_source(self):
        source = self.image("a.bmp", size=(100, 200))
        original = source.read_bytes()
        preview = self.portraits.preview(source, (100, 100))
        self.assertEqual(preview.size, (100, 100))
        self.assertEqual(preview.getpixel((0, 50)), (255, 255, 255))
        self.assertEqual(preview.getpixel((50, 50)), (255, 0, 0))
        self.assertEqual(source.read_bytes(), original)
        source.unlink()  # No image handle remains open on Windows.

    def test_font_discovery_deduplicates_and_excludes_non_truetype(self):
        data = resource_path("fonts", "CookieRun Bold.ttf").read_bytes()
        (self.root / "A.ttf").write_bytes(data)
        (self.root / "b.OTF").write_bytes(data)
        (self.root / "renamed.ttf").write_bytes(b"OTTO" + data[4:])
        (self.root / "broken.ttf").write_bytes(b"font fixture")
        fonts = FontService().list_fonts([self.root, self.root, self.root / "absent"])
        self.assertEqual([p.name for p in fonts], ["A.ttf"])

    def test_first_font_install_and_replacement_backup(self):
        service = FontService()
        source = self.root / "source.ttf"
        original = resource_path("fonts", "CookieRun Bold.ttf").read_bytes()
        replacement = original + b"replacement fixture"
        source.write_bytes(original)
        folder = self.root / "game" / "prestringtable" / "font"
        (self.root / 'game').mkdir()
        (self.root / 'game/BlackDesertLauncher.exe').touch()
        self.assertIsNone(service.apply(source, folder))
        self.assertEqual((folder / "pearl.ttf").read_bytes(), original)
        source.write_bytes(replacement)
        backup = service.apply(source, folder)
        self.assertEqual(backup.read_bytes(), original)
        self.assertEqual((folder / "pearl.ttf").read_bytes(), replacement)

    def test_renamed_otf_does_not_replace_existing_game_font(self):
        source = self.root / "renamed.ttf"
        original = resource_path("fonts", "CookieRun Bold.ttf").read_bytes()
        source.write_bytes(b"OTTO" + original[4:])
        folder = self.root / "game" / "prestringtable" / "font"
        folder.mkdir(parents=True)
        target = folder / "pearl.ttf"
        target.write_bytes(original)
        with self.assertRaises(ValueError):
            FontService().apply(source, folder)
        self.assertEqual(target.read_bytes(), original)
        self.assertFalse((folder / "backup").exists())

    def test_settings_round_trip_and_failed_save_keep_previous_values(self):
        path = self.root / "config" / "settings.json"
        settings = Settings(path)
        self.assertFalse(path.exists())
        settings.update(language="en", portrait_folder="한글 경로")
        self.assertEqual(Settings(path).get("portrait_folder"), "한글 경로")
        with patch("core.settings.os.replace", side_effect=OSError("locked")):
            with self.assertRaises(OSError):
                settings.update(language="kr")
        self.assertEqual(settings.get("language"), "en")
        self.assertEqual(Settings(path).get("language"), "en")
        self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_malformed_settings_fall_back_without_overwriting_on_load(self):
        path = self.root / "settings.json"
        path.write_text("{broken", encoding="utf-8")
        with self.assertLogs("core.settings", level="WARNING"):
            settings = Settings(path)
        self.assertEqual(settings.get("language", "kr"), "kr")
        self.assertEqual(path.read_text(encoding="utf-8"), "{broken")

    def test_edited_portrait_replacement_preserves_dimensions_and_original_backup(self):
        current = self.image("game/a.bmp", "red")
        source = self.image("source/b.bmp", "blue")
        original, source_bytes = current.read_bytes(), source.read_bytes()
        image = Image.new("RGB", (100, 120), "green")
        backup = self.portraits.replace(current, source, image)
        with Image.open(current) as actual:
            self.assertEqual(actual.size, image.size)
            self.assertEqual(actual.mode, "RGB")
            self.assertEqual(actual.tobytes(), image.tobytes())
        self.assertEqual(backup.read_bytes(), original)
        self.assertEqual(source.read_bytes(), source_bytes)
        self.assertEqual(list(current.parent.glob("*.tmp")), [])
        self.assertEqual(list(current.parent.glob("tmp*.bmp")), [])

    def test_edited_portrait_wrong_size_or_same_source_is_rejected(self):
        current = self.image("game/a.bmp")
        source = self.image("source/b.bmp", "blue")
        original = current.read_bytes()
        with self.assertRaises(ValueError):
            self.portraits.replace(current, source, Image.new("RGB", (200, 200)))
        with self.assertRaises(ValueError):
            self.portraits.replace(current, current, Image.new("RGB", (100, 120)))
        self.assertEqual(current.read_bytes(), original)
        self.assertFalse((current.parent / "backup").exists())

    def test_save_edited_rejects_oversized_images(self):
        target = self.root / "too_large.bmp"
        with self.assertRaises(ValueError):
            self.portraits.save_edited(Image.new("RGB", (625, 804)), target)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()

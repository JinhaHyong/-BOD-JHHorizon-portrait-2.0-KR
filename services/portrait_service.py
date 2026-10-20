"""Validate and replace BMP portraits without depending on Qt."""

import logging
import os
from pathlib import Path
import tempfile

from PIL import Image

from services.backup_service import BackupService


MAX_SIZE = (624, 804)


class PortraitService:
    def __init__(self, backups: BackupService | None = None):
        self.backups = backups if backups is not None else BackupService()

    def validate(self, path: Path):
        path = Path(path)
        if path.suffix.lower() != ".bmp":
            raise ValueError("BMP files only")
        with Image.open(path) as image:
            if image.format != "BMP":
                raise ValueError("Not a BMP image")
            if image.width > MAX_SIZE[0] or image.height > MAX_SIZE[1]:
                raise ValueError("Portrait exceeds 624 x 804 pixels")
            image.load()

    def list_portraits(self, folder: Path, query: str = "") -> list[Path]:
        folder = Path(folder)
        if not folder.is_dir():
            return []
        result = []
        for path in sorted(folder.iterdir(), key=lambda p: p.name.casefold()):
            if not path.is_file() or path.suffix.lower() != ".bmp":
                continue
            if query.casefold() not in path.name.casefold():
                continue
            try:
                self.validate(path)
            except (OSError, ValueError, Image.DecompressionBombError):
                logging.getLogger(__name__).warning("Skipping invalid portrait: %s", path)
                continue
            result.append(path)
        return result

    def preview(self, path: Path, size: tuple[int, int], *, background="white") -> Image.Image:
        with Image.open(path) as image:
            return self.preview_image(image, size, background=background)

    @staticmethod
    def preview_image(image: Image.Image, size: tuple[int, int], *, background="white") -> Image.Image:
        image = image.convert("RGB")
        ratio = min(size[0] / image.width, size[1] / image.height)
        image = image.resize((max(1, int(image.width * ratio)),
                              max(1, int(image.height * ratio))), Image.Resampling.LANCZOS)
        # Display-only padding can be transparent so either UI theme shows through.
        canvas = (Image.new("RGBA", size, (0, 0, 0, 0)) if background is None
                  else Image.new("RGB", size, background))
        canvas.paste(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
        return canvas

    def read_image(self, path: Path) -> Image.Image:
        path = Path(path)
        if path.suffix.lower() != '.bmp':
            raise ValueError('BMP files only')
        with Image.open(path) as image:
            if image.format != 'BMP':
                raise ValueError('Not a BMP image')
            if image.width > MAX_SIZE[0] or image.height > MAX_SIZE[1]:
                raise ValueError('Portrait exceeds 624 x 804 pixels')
            return image.convert("RGB")

    @staticmethod
    def validate_edited(image: Image.Image):
        if image.width > MAX_SIZE[0] or image.height > MAX_SIZE[1]:
            raise ValueError("Portrait exceeds 624 x 804 pixels")
        if image.width < 1 or image.height < 1:
            raise ValueError("Empty portrait")

    def save_edited(self, image: Image.Image, destination: Path) -> Path | None:
        """Write a 24-bit BMP, retaining a backup when replacing an existing file."""
        self.validate_edited(image)
        destination = Path(destination)
        if destination.suffix.lower() != ".bmp":
            destination = destination.with_name(destination.name + ".bmp")
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, filename = tempfile.mkstemp(dir=destination.parent, suffix=".bmp")
        os.close(descriptor)
        temporary = Path(filename)
        try:
            image.convert("RGB").save(temporary, format="BMP")
            return self.backups.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    def replace(self, current: Path, replacement: Path, edited_image: Image.Image | None = None) -> Path | None:
        current, replacement = Path(current), Path(replacement)
        if not current.is_file():
            raise FileNotFoundError(current)
        self.validate(replacement)
        if edited_image is not None:
            if os.path.samefile(current, replacement):
                raise ValueError("Source and target refer to the same file")
            with Image.open(replacement) as source:
                if edited_image.size != source.size:
                    raise ValueError("Edited image dimensions do not match the source")
            return self.save_edited(edited_image, current)
        return self.backups.replace(replacement, current)

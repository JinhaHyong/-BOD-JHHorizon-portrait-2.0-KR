"""Find font files and install one as pearl.ttf; previewing belongs to Qt UI."""

from pathlib import Path

from core.font_formats import is_truetype_file
from services.backup_service import BackupService
from services.game_location import is_game_root


class FontService:
    def __init__(self, backups: BackupService | None = None):
        self.backups = backups if backups is not None else BackupService()

    def list_fonts(self, folders: list[Path], *, files: list[Path] | None = None) -> list[Path]:
        result = {}
        for location in [*folders, *(files or [])]:
            location = Path(location)
            if location.is_file():
                candidates = (location,)
            elif location.is_dir():
                candidates = location.iterdir()
            else:
                continue
            for path in candidates:
                if path.is_file() and path.suffix.lower() == ".ttf" and is_truetype_file(path):
                    result[str(path.resolve()).casefold()] = path
        return sorted(result.values(), key=lambda p: (p.name.casefold(), str(p).casefold()))

    def apply(self, source: Path, folder: Path) -> Path | None:
        source = Path(source)
        if source.suffix.lower() != ".ttf" or not is_truetype_file(source):
            raise ValueError("검은사막에는 실제 TTF 형식의 폰트만 적용할 수 있습니다.")
        folder = Path(folder)
        if (folder.name.casefold() != 'font' or folder.parent.name.casefold() != 'prestringtable'
                or not is_game_root(folder.parent.parent)):
            raise ValueError("실제 검은사막 설치 폴더를 확인한 뒤 다시 적용해주세요.")
        return self.backups.replace(source, Path(folder) / "pearl.ttf")

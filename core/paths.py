"""Resolve resources from the application, never the working directory."""

import os
from pathlib import Path
import sys


SOURCE_ROOT = Path(__file__).resolve().parent.parent
# Keep user-supplied folders beside the EXE, outside onefile's temporary files.
APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else SOURCE_ROOT
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", SOURCE_ROOT)) / "resources"


def resource_path(*parts: str) -> Path:
    return RESOURCE_ROOT.joinpath(*parts)


def default_portrait_folder() -> Path:
    # Respect Windows' redirected Documents folder (including OneDrive).
    if sys.platform == "win32":
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer) == 0:
            return Path(buffer.value) / "Black Desert" / "FaceTexture"
    return Path.home() / "Documents" / "Black Desert" / "FaceTexture"


def default_font_folder() -> Path:
    return Path("C:/Pearlabyss/BlackDesert/prestringtable/font")


def system_font_folders() -> list[Path]:
    folders = []
    if windir := os.environ.get("WINDIR"):
        folders.append(Path(windir) / "Fonts")
    if local := os.environ.get("LOCALAPPDATA"):
        folders.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    return folders


def settings_file() -> Path:
    # JHnode keeps the legacy data location so saved fonts and edits still resolve.
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".config"))
    return base / "JHHorizon" / "PortraitManager" / "settings.json"

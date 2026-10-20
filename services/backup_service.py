"""Back up the target before replacing it, using unique backup names."""

from datetime import datetime
import os
from pathlib import Path
import shutil
import stat
import tempfile
from uuid import uuid4


class BackupService:
    def backup(self, target: Path) -> Path | None:
        target = Path(target)
        if not target.exists():
            return None
        folder = target.parent / "backup"
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        destination = folder / f"{target.stem}_{stamp}_{uuid4().hex[:8]}{target.suffix}"
        try:
            shutil.copy2(target, destination)
        except OSError:
            if destination.exists():
                destination.chmod(destination.stat().st_mode | stat.S_IWRITE)
                destination.unlink()
            raise
        return destination

    def replace(self, source: Path, target: Path) -> Path | None:
        source, target = Path(source), Path(target)
        if not source.is_file():
            raise FileNotFoundError(source)
        if target.exists() and os.path.samefile(source, target):
            raise ValueError("Source and target refer to the same file")
        target.parent.mkdir(parents=True, exist_ok=True)
        # Stage the copy first. A failed copy cannot truncate the game file.
        descriptor, filename = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
        os.close(descriptor)
        temporary = Path(filename)
        try:
            shutil.copy2(source, temporary)
            temporary.chmod(temporary.stat().st_mode | stat.S_IWRITE)
            backup = self.backup(target)
            os.replace(temporary, target)
            return backup
        finally:
            temporary.unlink(missing_ok=True)

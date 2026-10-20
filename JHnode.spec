# PyInstaller 6: folder or single-file distribution, no user settings or caches.
from pathlib import Path
from importlib.metadata import distribution
import sys
import os
import PySide6

root = Path(SPECPATH)
mode = os.environ.get('JHNODE_BUILD_MODE', 'folder')
if mode not in ('folder', 'single'):
    raise ValueError('JHNODE_BUILD_MODE must be folder or single')
qt = Path(PySide6.__file__).resolve().parent
data = [(str(root / 'resources'), 'resources'), (str(root / 'LICENSE.md'), 'licenses/JHnode')]
for package in ('PySide6', 'PySide6_Essentials', 'PySide6_Addons', 'shiboken6', 'Pillow', 'PyInstaller'):
    info = distribution(package)
    for record in info.files or []:
        if '/licenses/' in str(record).replace('\\', '/'):
            path = Path(info.locate_file(record))
            if path.is_file():
                data.append((str(path), 'licenses/' + package))
python_license = Path(sys.base_prefix) / 'LICENSE.txt'
if python_license.is_file():
    data.append((str(python_license), 'licenses/Python'))
if (root / 'build_support/licenses').is_dir():
    data.append((str(root / 'build_support/licenses'), 'licenses'))
data.append((str(root / 'build_support/THIRD-PARTY-NOTICES.txt'), '.'))
if mode == 'single':
    data.append((str(root / 'build_support/README-single.txt'), '.'))

# Include the app-local MSVC runtime and native Windows TLS backend explicitly.
runtime = {path.name.casefold(): path for path in qt.glob('*140*.dll')}
binary = [(str(path), 'PySide6') for path in runtime.values()]
binary += [(str(path), '.') for name, path in runtime.items()
           if name.startswith(('msvcp140', 'vcruntime140', 'concrt140'))]
binary.append((str(qt / 'plugins/tls/qschannelbackend.dll'), 'PySide6/plugins/tls'))
a = Analysis(
    [str(root / 'build_support/launcher.py')], pathex=[str(root)],
    binaries=binary, datas=data,
    hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'tkinter', 'pytest', 'IPython', 'matplotlib', 'numpy'],
    noarchive=False, optimize=0,
)
# Qt uses Windows' native, unversioned ICU API. Never ship an unrelated
# development tool's ICU under the same name (its exported API can differ).
a.binaries = [row for row in a.binaries
              if Path(row[0]).name.casefold() not in ('icuuc.dll', 'icuin.dll', 'icu.dll')]
# Keep the Python and Qt copies on one, compatible app-local MSVC version.
a.binaries = [(name, str(runtime.get(Path(name).name.casefold(), Path(path))), kind)
              for name, path, kind in a.binaries]
pyz = PYZ(a.pure)
options = dict(name='JHnode', debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False, console=False,
    disable_windowed_traceback=False, icon=str(root / 'resources/아이콘.ico'),
)
if mode == 'single':
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **options)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **options)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='JHnode')

"""Read selected shortcuts and local install metadata without launching a client."""

from configparser import ConfigParser
import json
import os
from pathlib import Path
import re
import subprocess


class GameLocationError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def is_game_root(path):
    path = Path(path)
    return (path.is_dir() and ((path / 'BlackDesertLauncher.exe').is_file()
            or (path / 'bin64' / 'BlackDesert64.exe').is_file()))


def nearby_roots(value):
    if not value:
        return []
    path = Path(os.path.expandvars(str(value).strip().strip('"'))).expanduser()
    if not path.is_absolute():
        return []
    if path.is_file() or path.suffix.lower() in ('.exe', '.pae', '.ico'):
        path = path.parent
    candidates = [path, *list(path.parents)[:3]]
    # A selected client inside bin64 belongs to its parent installation; a
    # launcher subfolder must likewise not become the font destination root.
    for candidate in candidates:
        if (candidate / 'bin64' / 'BlackDesert64.exe').is_file():
            return [candidate.resolve()]
    for candidate in candidates:
        if is_game_root(candidate):
            return [candidate.resolve()]
    # Also accept choosing the publisher's installation folder.
    return [child.resolve() for name in ('BlackDesert', 'Black Desert')
            if is_game_root(child := path / name)]


def read_link(path):
    if os.name != 'nt':
        raise GameLocationError('shortcut_unreadable')
    powershell = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    # The file name is data on stdin, never PowerShell source. No Save/Run/ShellExecute.
    script = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$locationSource = ConvertFrom-Json ([Console]::In.ReadToEnd())
$locationShell = New-Object -ComObject WScript.Shell
$locationLink = $locationShell.CreateShortcut($locationSource)
[Console]::Write((@{
    target = $locationLink.TargetPath
    arguments = $locationLink.Arguments
    working = $locationLink.WorkingDirectory
} | ConvertTo-Json -Compress))
'''
    try:
        completed = subprocess.run(
            [str(powershell), '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', script],
            input=json.dumps(str(path), ensure_ascii=True).encode('ascii'),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8, check=True,
            creationflags=subprocess.CREATE_NO_WINDOW)
        result = json.loads(completed.stdout.decode('utf-8-sig'))
        if not isinstance(result, dict):
            raise ValueError('Invalid shortcut data')
        return result
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise GameLocationError('shortcut_unreadable') from error


def read_url(path):
    raw = Path(path).read_bytes()
    if len(raw) > 256 * 1024:
        raise GameLocationError('shortcut_unreadable')
    for encoding in ('utf-8-sig', 'utf-16', 'cp949', 'cp1252'):
        try:
            parser = ConfigParser(interpolation=None, strict=False)
            parser.read_string(raw.decode(encoding))
            return {'target': parser.get('InternetShortcut', 'URL', fallback=''),
                    'icon': parser.get('InternetShortcut', 'IconFile', fallback='')}
        except (UnicodeError, ValueError):
            continue
        except Exception as error:
            raise GameLocationError('shortcut_unreadable') from error
    raise GameLocationError('shortcut_unreadable')


def read_vdf(path):
    with Path(path).open('r', encoding='utf-8-sig', errors='replace') as handle:
        text = handle.read(2 * 1024 * 1024 + 1)
    if len(text) > 2 * 1024 * 1024:
        raise ValueError('Install metadata is too large')
    tokens = iter(re.findall(r'//[^\n]*|"(?:\\.|[^"\\])*"|[{}]', text))

    def item(token):
        if not token.startswith('"'):
            raise ValueError('Invalid install metadata')
        return token[1:-1].replace('\\"', '"').replace('\\\\', '\\')

    def block(nested=False, depth=0):
        if depth > 16:
            raise ValueError('Install metadata nesting limit')
        result = {}
        for token in tokens:
            if token.startswith('//'):
                continue
            if token == '}':
                if nested:
                    return result
                raise ValueError('Unexpected metadata brace')
            key = item(token).casefold()
            value = next(tokens, None)
            while value is not None and value.startswith('//'):
                value = next(tokens, None)
            if value is None:
                raise ValueError('Incomplete install metadata')
            result[key] = block(True, depth + 1) if value == '{' else item(value)
        if nested:
            raise ValueError('Unclosed install metadata')
        return result
    return block()


def steam_folders(hint=None):
    folders = [Path(hint)] if hint else []
    if os.name == 'nt':
        import winreg
        for hive, key, field in (
            (winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath'),
            (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Valve\Steam', 'InstallPath'),
            (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath'),
        ):
            try:
                with winreg.OpenKey(hive, key) as handle:
                    value, _kind = winreg.QueryValueEx(handle, field)
                    if isinstance(value, str) and value:
                        folders.append(Path(value))
            except OSError:
                pass
    for variable in ('ProgramFiles(x86)', 'ProgramFiles'):
        if value := os.environ.get(variable):
            folders.append(Path(value) / 'Steam')
    unique = {}
    for folder in folders:
        if folder.is_dir():
            unique.setdefault(os.path.normcase(str(folder.resolve())), folder.resolve())
    return list(unique.values())


def steam_roots(app_id, hint=None):
    libraries = {}
    for folder in steam_folders(hint):
        libraries[os.path.normcase(str(folder))] = folder
        try:
            data = read_vdf(folder / 'steamapps/libraryfolders.vdf').get('libraryfolders', {})
            if not isinstance(data, dict):
                continue
            for key, value in data.items():
                location = value.get('path') if isinstance(value, dict) else value if key.isdecimal() else None
                if isinstance(location, str) and Path(location).is_absolute():
                    libraries[os.path.normcase(location)] = Path(location)
        except (OSError, ValueError):
            pass
    roots = []
    for library in libraries.values():
        try:
            manifest = read_vdf(library / 'steamapps' / f'appmanifest_{app_id}.acf').get('appstate', {})
            if not isinstance(manifest, dict) or str(manifest.get('appid')) != app_id:
                continue
            directory = manifest.get('installdir')
            if not isinstance(directory, str) or not directory:
                continue
            common = (library / 'steamapps/common').resolve()
            target = (common / directory).resolve()
            if target.is_relative_to(common) and is_game_root(target):
                roots.append(target)
        except (OSError, ValueError):
            pass
    return roots


def find_game_roots(selected, seen=None):
    selected = Path(selected).resolve()
    seen = set() if seen is None else seen
    key = os.path.normcase(str(selected))
    if key in seen or len(seen) >= 5:
        raise GameLocationError('shortcut_unreadable')
    seen.add(key)
    if selected.is_dir():
        roots = nearby_roots(selected)
    elif not selected.is_file():
        raise GameLocationError('not_found')
    elif selected.suffix.lower() == '.exe':
        roots = nearby_roots(selected)
    elif selected.suffix.lower() in ('.lnk', '.url'):
        data = read_link(selected) if selected.suffix.lower() == '.lnk' else read_url(selected)
        target = os.path.expandvars(str(data.get('target', '')).strip().strip('"'))
        arguments = str(data.get('arguments', ''))
        launch = re.search(r'steam://(?:rungameid|run)/(\d+)(?:[/\s]|$)', target + ' ' + arguments, re.I)
        if launch is None and Path(target).name.casefold() == 'steam.exe':
            launch = re.search(r'(?:^|\s)-applaunch\s+(\d+)(?:\s|$)', arguments, re.I)
        if launch is not None:
            hint = Path(target).parent if Path(target).name.casefold() == 'steam.exe' else None
            roots = steam_roots(launch.group(1), hint)
        elif '://' in target:
            roots = nearby_roots(data.get('icon'))
            if not roots:
                raise GameLocationError('unsupported_url')
        else:
            roots = nearby_roots(target)
            if not roots and target and Path(target).suffix.lower() in ('.lnk', '.url'):
                roots = find_game_roots(target, seen)
            if not roots:
                roots = nearby_roots(data.get('working')) or nearby_roots(data.get('icon'))
            if not roots:
                # Some user shortcuts wrap the launcher in another executable.
                # Inspect argument paths as data; never evaluate the command line.
                for quoted, bare in re.findall(r'"([^"]+)"|(\S+)', arguments):
                    value = quoted or bare
                    if Path(value).suffix.lower() in ('.exe', '.pae'):
                        roots.extend(nearby_roots(value))
    else:
        raise GameLocationError('not_found')
    unique = {os.path.normcase(str(path)): path for path in roots}
    if not unique:
        raise GameLocationError('not_found')
    return list(unique.values())

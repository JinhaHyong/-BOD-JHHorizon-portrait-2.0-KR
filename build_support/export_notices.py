"""Export the exact notices bundled in a onefile EXE for redistribution."""

import argparse
from pathlib import Path, PurePosixPath

from PyInstaller.archive.readers import CArchiveReader


def export(executable, destination):
    root = Path(destination).resolve()
    archive = CArchiveReader(str(executable))
    count = 0
    for name in archive.toc:
        relative = PurePosixPath(name.replace('\\', '/'))
        if relative.parts[0] != 'licenses' and str(relative) != 'THIRD-PARTY-NOTICES.txt':
            continue
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Invalid notice path in executable')
        target = root.joinpath(*relative.parts).resolve()
        if not target.is_relative_to(root):
            raise ValueError('Notice path escaped output directory')
        target.parent.mkdir(parents=True, exist_ok=True)
        content = archive.extract(name)
        if str(relative) == 'THIRD-PARTY-NOTICES.txt':
            content = (b'Single-file edition: runtime libraries are embedded in JHnode.exe.\n'
                       b'References below to _internal describe the folder edition.\n'
                       b'Companion license documents are also in the licenses directory.\n'
                       b'No external _internal folder is needed to run this edition.\n\n' + content)
        target.write_bytes(content)
        count += 1
    if not (root / 'licenses/Python/LICENSE.txt').is_file():
        raise RuntimeError('Python license was not exported')
    if not (root / 'licenses/Pillow/LICENSE').is_file():
        raise RuntimeError('Pillow license was not exported')
    print(f'Exported {count} bundled notice files.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    export(args.exe, args.output)

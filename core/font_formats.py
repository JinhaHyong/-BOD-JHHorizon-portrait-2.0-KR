"""Inspect the sfnt directory without loading an entire font for UI checks."""

from pathlib import Path
import struct


def _truetype_directory(header, directory, size):
    if len(header) != 12 or header[:4] not in (b'\x00\x01\x00\x00', b'true'):
        return False
    count = struct.unpack_from('>H', header, 4)[0]
    if not 1 <= count <= 4096 or len(directory) != count * 16:
        return False
    tables = {}
    for tag, _checksum, offset, length in struct.iter_unpack('>4sIII', directory):
        if tag in tables or offset < 12 + len(directory) or offset + length > size:
            return False
        tables[tag] = length
    required = {b'head': 54, b'maxp': 6, b'cmap': 4, b'loca': 2,
                b'glyf': 1, b'hhea': 36, b'hmtx': 4}
    return (not ({b'CFF ', b'CFF2'} & tables.keys())
            and all(tables.get(tag, 0) >= minimum for tag, minimum in required.items()))


def is_truetype(data: bytes) -> bool:
    if len(data) < 12:
        return False
    count = struct.unpack_from('>H', data, 4)[0]
    return _truetype_directory(data[:12], data[12:12 + count * 16], len(data))


def is_truetype_file(path: Path) -> bool:
    try:
        with Path(path).open('rb') as stream:
            header = stream.read(12)
            if len(header) != 12:
                return False
            count = struct.unpack_from('>H', header, 4)[0]
            if not 1 <= count <= 4096:
                return False
            directory = stream.read(count * 16)
            stream.seek(0, 2)
            return _truetype_directory(header, directory, stream.tell())
    except OSError:
        return False

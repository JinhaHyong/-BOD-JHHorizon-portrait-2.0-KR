"""Persistent application fonts shared by the browser and portrait editor."""

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase, QRawFont

from core.local_fonts import font_storage


_registered_fonts = {}
_family_paths = {}


def font_from_file(path, *, pixel_size=None):
    """Describe the file's face; the caller owns its application registration.

    Use this on the GUI thread when a file is selected. Workers render from the
    face metadata saved in TextOverlay and never register fonts themselves.
    """
    raw = QRawFont(str(path), 32)
    if not raw.isValid():
        raise ValueError('Could not load font')
    font = QFont(raw.familyName())
    font.setStyleName(raw.styleName())
    font.setWeight(QFont.Weight(raw.weight()))
    font.setStyle(raw.style())
    if pixel_size is not None:
        font.setPixelSize(pixel_size)
    return font


def set_layer_font_file(layer, path):
    """Register an explicitly selected file and retain its face in the layer."""
    family = register_font(str(path))
    font = font_from_file(path)
    layer.font_family = family
    layer.font_file = str(Path(path).resolve())
    layer.font_style = font.styleName()
    layer.font_weight = int(font.weight())
    layer.font_slant = {QFont.Style.StyleNormal: 'normal',
                        QFont.Style.StyleItalic: 'italic',
                        QFont.Style.StyleOblique: 'oblique'}[font.style()]
    return font


def layer_font(layer):
    """Build the selected face, adding optional bold/italic without erasing it."""
    font = QFont(layer.font_family)
    base_weight = layer.font_weight if layer.font_weight is not None else int(QFont.Weight.Normal)
    base_style = {'normal': QFont.Style.StyleNormal, 'italic': QFont.Style.StyleItalic,
                  'oblique': QFont.Style.StyleOblique}[layer.font_slant]
    weight = max(base_weight, int(QFont.Weight.Bold)) if layer.bold else base_weight
    style = QFont.Style.StyleItalic if layer.italic and base_style == QFont.Style.StyleNormal else base_style
    # An exact style name takes precedence over weight/style matching in Qt.
    # Release it only when a checkbox requests a different face/effect.
    if weight == base_weight and style == base_style:
        font.setStyleName(layer.font_style)
    font.setWeight(QFont.Weight(weight))
    font.setStyle(style)
    font.setPixelSize(layer.font_size)
    return font


def register_font(path: str) -> str:
    path = str(Path(path).resolve())
    if path in _registered_fonts:
        return _registered_fonts[path][1]
    font_id = QFontDatabase.addApplicationFont(path)
    families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
    if not families:
        if font_id >= 0:
            QFontDatabase.removeApplicationFont(font_id)
        raise ValueError('Could not load font')
    _registered_fonts[path] = (font_id, families[0])
    _family_paths.setdefault(families[0], []).append(path)
    return families[0]


def registered_path(family):
    paths = _family_paths.get(family, [])
    if len(paths) == 1:
        return paths[0]
    # Selecting a family in QFontComboBox means its normal face. Do not silently
    # associate it with whichever bold/italic file happened to register last.
    normal = []
    for path in paths:
        try:
            font = font_from_file(path)
            if font.weight() == QFont.Weight.Normal and font.style() == QFont.Style.StyleNormal:
                normal.append(path)
        except ValueError:
            continue
    return normal[0] if len(normal) == 1 else None


def load_downloaded_fonts():
    folder = font_storage()
    if folder.is_dir():
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.suffix.lower() in ('.ttf', '.otf'):
                try:
                    register_font(str(path))
                except ValueError:
                    pass

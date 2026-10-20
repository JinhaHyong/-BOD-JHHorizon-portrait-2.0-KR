"""Shared light/dark palette and widget styles."""

from PySide6.QtGui import QColor, QPalette


def apply_theme(app, mode='light'):
    """Use explicit light/dark colors independently of the Windows theme."""
    dark = mode == 'dark'
    colors = {
        'Window': ('#ffffff', '#171c25'), 'WindowText': ('#111827', '#e5edf8'),
        'Base': ('#ffffff', '#111720'), 'AlternateBase': ('#f5f7fa', '#222c3a'),
        'Text': ('#111827', '#e5edf8'), 'Button': ('#f0f0f0', '#2a3444'),
        'ButtonText': ('#111827', '#e5edf8'), 'PlaceholderText': ('#64748b', '#a7b6ca'),
        'Highlight': ('#1E3D59', '#426a98'), 'HighlightedText': ('#ffffff', '#ffffff'),
        'ToolTipBase': ('#ffffdc', '#263244'), 'ToolTipText': ('#111827', '#e5edf8'),
        'Mid': ('#cbd5e1', '#40506a'), 'Midlight': ('#e2e8f0', '#34435a'),
        'Dark': ('#94a3b8', '#0b1018'), 'Light': ('#f8fafc', '#334155'),
        'Shadow': ('#9ca3af', '#070b11'), 'BrightText': ('#dc2626', '#ff9b9b'),
        'Link': ('#2563eb', '#85baff'), 'LinkVisited': ('#7c3aed', '#c4a5ff'),
    }
    palette = QPalette()
    for role, values in colors.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(values[dark]))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText,
                 QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor('#75869b' if dark else '#808080'))
    app.setPalette(palette)

BUTTON_STYLE = """
QPushButton {
    background-color: palette(highlight);
    color: palette(highlighted-text);
    border: none;
    padding: 5px 10px;
    border-radius: 3px;
    font-family: '맑은 고딕';
    font-size: 9pt;
}
QPushButton:hover {
    background-color: #2E4D69;
}
"""

PORTRAIT_LANGUAGE_BUTTON_STYLE = """
QPushButton {
    background-color: palette(button);
    border: 1px solid palette(mid);
    padding: 2px;
    font-size: 8pt;
    margin: 0px;
}
QPushButton:hover {
    background-color: palette(alternate-base);
}
QPushButton:checked {
    background-color: palette(highlight); color: palette(highlighted-text);
}
"""

WINDOW_STYLE = """
background-color: palette(window);
color: palette(window-text);
"""

LIST_FRAME_STYLE = """
QFrame { border: 1px solid palette(mid); background-color: palette(base); }
"""

LABEL_PADDING_STYLE = """
padding: 0px; margin: 0px; border: none;
"""

BORDERLESS_STYLE = """
border: none;
"""

PREVIEW_TITLE_STYLE = """
padding: 0px; margin: 0px;
"""

PORTRAIT_SEARCH_INPUT_STYLE = """
QLineEdit { padding: 3px; font: 9pt '맑은 고딕'; }
"""

CREATOR_STYLE = """
color: palette(link); font-family: '맑은 고딕'; font-size: 8pt;
"""

SEPARATOR_STYLE = """
font-family: '맑은 고딕'; font-size: 8pt;
"""

GUILD_STYLE = """
color: palette(bright-text); font-family: '맑은 고딕'; font-size: 8pt;
"""

FONT_SECTION_TITLE_STYLE = """
QLabel {
    padding: 0px;
    margin: 0px;
    border: none;
    background: transparent;
}
"""

FONT_ADD_PATH_BUTTON_STYLE = """
QPushButton {
    background-color: #2E4D69;
    color: palette(highlighted-text);
    border: none;
    padding: 0px 4px;
    border-radius: 2px;
    font-family: '맑은 고딕';
    font-size: 9pt;
    min-width: 15px;
    max-width: 15px;
    min-height: 15px;
    max-height: 15px;
}
QPushButton:hover {
    background-color: #3E5D69;
}
"""

FONT_SEARCH_INPUT_STYLE = """
QLineEdit {
    padding: 1px;
    border: 1px solid palette(mid);
    border-radius: 2px;
}
"""

FONT_LIST_STYLE = """
QListWidget {
    border: 1px solid palette(mid);
    background-color: palette(base);
}
QListWidget::item {
    padding: 5px;
}
QListWidget::item:selected {
    background-color: palette(highlight);
    color: palette(highlighted-text);
}
"""

FONT_PREVIEW_FRAME_STYLE = """
QFrame { border: 1px solid palette(mid); background-color: palette(alternate-base); }
"""

FONT_PREVIEW_INPUT_STYLE = """
QLineEdit {
    padding: 5px;
    border: 1px solid palette(mid);
    border-radius: 2px;
    background-color: palette(base);
}
"""

FONT_PREVIEW_LABEL_STYLE = """
QLabel {
    background-color: #2D2D31;  /* 진한 회색 배경 */
    border: 1px solid palette(mid);
    padding: 20px;
    font-size: 13pt;
}
"""

START_LANG_BUTTON_STYLE = """
QPushButton {
    background-color: palette(highlight);
    color: palette(highlighted-text);
    border: none;
    padding: 3px 8px;
    font-family: '맑은 고딕';
    font-size: 8pt;
}
QPushButton:hover {
    background-color: #2E4D69;
}
QPushButton:checked {
    background-color: #2E4D69;
}
"""

START_TITLE_LABEL_STYLE = """
color: palette(link); margin-bottom: 10px;
"""

START_ACTION_BUTTON_STYLE = """
QPushButton {
    background-color: palette(highlight);
    color: palette(highlighted-text);
    border: none;
    padding: 15px;
    border-radius: 5px;
    font-family: '맑은 고딕';
    font-size: 12pt;
    min-width: 200px;
}
QPushButton:hover {
    background-color: #2E4D69;
}
"""

KR_LANGUAGE_BUTTON_STYLE = """
QPushButton {
    border-top-left-radius: 3px;
    border-bottom-left-radius: 3px;
    min-width: 50px;
}
"""

EN_LANGUAGE_BUTTON_STYLE = """
QPushButton {
    border-top-right-radius: 3px;
    border-bottom-right-radius: 3px;
    min-width: 30px;
}
"""

THUMBNAIL_NORMAL = """
QFrame#portraitThumbnail { border: 2px solid palette(mid); border-radius: 5px; background-color: palette(base); margin: 0px; padding: 0px; }
QFrame#portraitThumbnail:hover { border-color: palette(link); }
"""

THUMBNAIL_SELECTED = """
QFrame#portraitThumbnail { border: 2px solid palette(link); border-radius: 5px; background-color: palette(base); margin: 0px; padding: 0px; }
"""

THUMBNAIL_LABEL = """
QLabel { border: none; background-color: palette(base); margin: 0px; padding: 0px; }
"""

PORTRAIT_PANEL_STYLE = """
QFrame#portraitPanel {
    border: 1px solid palette(mid);
    border-radius: 6px;
    background-color: palette(window);
}
"""

PORTRAIT_TITLE_STYLE = """
QLabel { color: palette(window-text); border: none; padding: 0; background: transparent; }
"""

DIALOG_STYLE = """
QDialog { background-color: palette(base); }
QLabel { color: palette(text); font-family: '맑은 고딕'; font-size: 10pt; }
QPushButton { background-color: palette(highlight); color: palette(highlighted-text); border: none; padding: 5px; font-family: '맑은 고딕'; font-size: 9pt; }
QPushButton:hover { background-color: #2E4D69; }
"""

TEXT_STYLE_CARD = """
QPushButton {
    background-color: palette(button);
    color: palette(button-text);
    border: 1px solid palette(mid);
    border-radius: 6px;
    padding: 5px 3px;
    font-family: '맑은 고딕';
    font-size: 9pt;
}
QPushButton:hover {
    background-color: palette(alternate-base);
    border-color: palette(link);
}
QPushButton:checked {
    background-color: palette(highlight);
    color: palette(highlighted-text);
    border-color: palette(highlight);
}
QPushButton:checked:hover {
    background-color: #2E4D69;
}
QPushButton:disabled {
    background-color: palette(button);
    color: palette(text);
    border-color: palette(mid);
}
"""

ALIGNMENT_COMBO_STYLE = """
QComboBox {
    background-color: palette(base);
    color: palette(text);
}
QComboBox:hover, QComboBox:focus, QComboBox:on {
    background-color: palette(base);
    color: palette(text);
}
QComboBox:disabled {
    color: palette(text);
}
"""

ALIGNMENT_MENU_STYLE = """
QAbstractItemView {
    background-color: palette(base);
    color: palette(text);
    border: 1px solid palette(mid);
    outline: none;
    selection-background-color: palette(highlight);
    selection-color: palette(highlighted-text);
}
QAbstractItemView::item {
    background-color: palette(base);
    color: palette(text);
    min-height: 22px;
    padding: 3px 8px;
}
QAbstractItemView::item:hover, QAbstractItemView::item:selected {
    background-color: palette(highlight);
    color: palette(highlighted-text);
}
"""


THEME_BUTTON_STYLE = """
QToolButton {
    background-color: palette(button);
    border: 1px solid palette(mid);
    border-radius: 6px;
    padding: 2px;
}
QToolButton:hover { background-color: palette(alternate-base); border-color: palette(link); }
QToolButton:checked { border-color: palette(highlight); }
QToolButton:focus { border-color: palette(link); }
"""

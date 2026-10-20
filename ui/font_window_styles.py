"""Palette-based layout styles scoped to the font manager."""

MANAGER_STYLE = '''
QWidget#fontManager { background:palette(window); color:palette(window-text); }
QFrame#fontPanel { background:palette(base); border:1px solid palette(mid); border-radius:8px; }
QLabel#fontHeading { font:600 18pt '맑은 고딕'; background:transparent; border:0; }
QLabel#fontName { font:600 15pt '맑은 고딕'; background:transparent; border:0; }
QLabel#fontSection { font:600 10pt '맑은 고딕'; background:transparent; border:0; }
QLabel#fontMuted { color:palette(placeholder-text); background:transparent; border:0; }
QWidget#fontManager QLineEdit { background:palette(base); color:palette(text);
    border:1px solid palette(mid); border-radius:6px; padding:7px 9px; }
QWidget#fontManager QLineEdit:focus { border-color:palette(link); }
QTabWidget#fontTabs::pane { border:0; background:transparent; }
QTabBar::tab { background:palette(window); color:palette(placeholder-text);
    border:0; padding:10px 18px; margin-right:6px; }
QTabBar::tab:selected { background:palette(base); color:palette(text);
    border-bottom:2px solid palette(link); }
QTabBar::tab:hover { background:palette(alternate-base); color:palette(text); }
QSplitter::handle { background:transparent; width:12px; }
QSplitter::handle:hover { background:palette(alternate-base); }
'''

LIST_STYLE = '''
QListWidget { border:0; background:palette(base); color:palette(text); outline:0; }
QListWidget::item { padding:9px 8px; border:1px solid transparent; border-radius:5px; }
QListWidget::item:hover { background:palette(alternate-base); }
QListWidget::item:selected { border-color:palette(link); background:palette(highlight);
    color:palette(highlighted-text); }
'''

SECONDARY_STYLE = '''
QPushButton { background:palette(base); color:palette(text); border:1px solid palette(mid);
    border-radius:6px; padding:7px 11px; }
QPushButton:hover { background:palette(alternate-base); border-color:palette(link); }
QPushButton:disabled { color:palette(placeholder-text); }
'''

PRIMARY_STYLE = '''
QPushButton { background:palette(highlight); color:palette(highlighted-text);
    border:1px solid palette(highlight); border-radius:6px; padding:9px 18px; font-weight:600; }
QPushButton:hover { border-color:palette(link); }
QPushButton:disabled { background:palette(button); color:palette(placeholder-text);
    border-color:palette(mid); }
'''

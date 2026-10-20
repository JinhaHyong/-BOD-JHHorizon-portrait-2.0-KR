"""A user-initiated browser link; no embedded catalogue or font downloads."""
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

FONT_SITE_URL = 'https://noonnu.cc/'


def font_site_label(parent):
    return '눈누 폰트 찾기 ↗' if parent.context.translations.language == 'kr' else 'Find fonts on Noonnu ↗'


def font_site_tooltip(parent):
    if parent.context.translations.language == 'kr':
        return '브라우저에서 눈누를 엽니다. 다운로드 전 게임 사용·이용 조건을 확인해 주세요.'
    return 'Open Noonnu in your browser. Check the font license, including game use, before downloading.'


def open_font_site(parent):
    if not QDesktopServices.openUrl(QUrl(FONT_SITE_URL)):
        parent.show_warning('브라우저를 열지 못했습니다. https://noonnu.cc/ 에 직접 접속해 주세요.'
                            if parent.context.translations.language == 'kr'
                            else 'Could not open your browser. Visit https://noonnu.cc/ directly.')

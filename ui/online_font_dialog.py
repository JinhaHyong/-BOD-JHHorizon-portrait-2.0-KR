"""Keep the font list; show instant bundled image cards for the selected face."""

import logging

from PySide6.QtCore import QSignalBlocker, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFrame, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QProgressDialog, QPushButton, QSizePolicy,
    QSplitter, QVBoxLayout, QWidget,
)

from core.font_previews import preview_complete, preview_record
from core.online_fonts import bundled_catalog, catalog_cache, font_storage, parse_catalog
from services.font_preview_service import FontPreviewService
from services.online_font_service import OnlineFontService
from services.ttf_catalog_service import TtfCatalogService
from core.font_formats import is_truetype_file
from ui.font_registry import register_font
from ui.styles import ALIGNMENT_COMBO_STYLE, ALIGNMENT_MENU_STYLE
from ui.font_preview import FontPreview
from ui.ime_search import ImeSearchLineEdit
from ui.font_window_styles import MANAGER_STYLE, LIST_STYLE, PRIMARY_STYLE, SECONDARY_STYLE


WORDS = {
    'kr': {
        'title': '온라인 폰트', 'search': '폰트 이름 검색', 'refresh': '목록 새로고침',
        'all': '모든 폰트', 'saved_filter': '다운로드한 폰트',
        'ttf_all': 'TTF 폰트', 'ttf_checking': 'TTF 제공 여부 확인 중 · {count}개',
        'choose': '왼쪽에서 폰트를 선택해 주세요.', 'download': '다운로드',
        'saved': '다운로드 완료', 'use': '이 폰트 선택', 'close': '닫기',
        'source': '배포처 · 이용 조건', 'reload': '미리보기 다시 불러오기',
        'refreshing': '폰트 목록을 갱신하는 중…', 'count': '{count}개 · 목록 기준 {date}',
        'offline': '최신 목록 확인 실패 · 저장된 목록 표시 중',
        'create_previews': '미리보기 만들기', 'later': '나중에', 'cancel': '취소',
        'new_fonts': '새로운 폰트 {count}개가 추가되었습니다.\n미리보기를 만들까요?',
        'create_hint': '미리보기를 만드는 동안 폰트 데이터를 받아 처리합니다.\n'
                       '완성된 이미지만 저장하며, 다음 실행에도 사용할 수 있습니다.',
        'building': '미리보기 생성 중 · {done}/{total}개\n{name}',
        'build_result': '미리보기 생성 완료 · {count}개 · 실패 {failed}개',
        'build_cancelled': '미리보기 생성 취소 · 완료 {count}개 · 완성된 이미지는 보관됩니다.',
        'unknown': '날짜 미제공', 'metadata': '다운로드 가능한 굵기를 확인하는 중…',
        'fetching': '폰트 파일을 다운로드하는 중…', 'progress': '다운로드 중… {size:.0f}KB',
        'kept': '저장됨 · {size:.1f}MB · 다음 실행에도 사용할 수 있습니다.',
        'error': '폰트를 처리하지 못했습니다. {error}',
        'storage': '미리보기 이미지는 다음 실행에도 유지됩니다.\n'
                   '이 폰트 선택을 누르면 필요한 폰트를 다운로드하여 적용합니다.',
    },
    'en': {
        'title': 'Online fonts', 'search': 'Search font names', 'refresh': 'Refresh catalogue',
        'all': 'All fonts', 'saved_filter': 'Downloaded fonts',
        'ttf_all': 'TTF fonts', 'ttf_checking': 'Checking TTF availability · {count} fonts',
        'choose': 'Select a font on the left.', 'download': 'Download', 'saved': 'Downloaded',
        'use': 'Use this font', 'close': 'Close', 'source': 'Source · License',
        'reload': 'Reload preview', 'refreshing': 'Refreshing font catalogue…',
        'count': '{count} fonts · Catalogue date {date}', 'unknown': 'unavailable',
        'offline': 'Update unavailable · Showing the saved catalogue',
        'create_previews': 'Create previews', 'later': 'Later', 'cancel': 'Cancel',
        'new_fonts': '{count} new fonts have been added.\nCreate their previews?',
        'create_hint': 'Font data will be fetched to create the previews.\n'
                       'Only the finished images are saved for future sessions.',
        'building': 'Creating previews · {done}/{total} fonts\n{name}',
        'build_result': 'Previews created · {count} fonts · {failed} failed',
        'build_cancelled': 'Preview creation cancelled · {count} finished · Completed images are kept.',
        'metadata': 'Checking available download weights…',
        'fetching': 'Downloading font…', 'progress': 'Downloading… {size:.0f} KB',
        'kept': 'Saved · {size:.1f} MB · Available after restarting.',
        'error': 'Could not process the font. {error}',
        'storage': 'Preview images are kept for future sessions.\n'
                   'Use this font downloads the font if needed and applies it.',
    },
}


class OnlineFontPanel(QWidget):
    font_ready = Signal(object)
    use_requested = Signal(object)
    close_requested = Signal()

    def __init__(self, context, parent=None, *, embedded=False, ttf_only=False):
        super().__init__(parent)
        self.context = context
        self.embedded = embedded
        self.ttf_only = ttf_only
        self.ttf_catalog = TtfCatalogService(self) if ttf_only else None
        self.ttf_refresh_timer = QTimer(self)
        self.ttf_refresh_timer.setSingleShot(True)
        self.ttf_refresh_timer.timeout.connect(self.ttf_catalog_changed)
        if self.ttf_catalog is not None:
            self.ttf_catalog.changed.connect(lambda: self.ttf_refresh_timer.start(50))
        self.words = WORDS.get(context.translations.language, WORDS['kr'])
        self.service = OnlineFontService(self)
        self.preview_builder = FontPreviewService(self)
        self.preview_builder.progress.connect(self.preview_build_progress)
        self.preview_builder.preview_ready.connect(self.preview_built)
        self.preview_builder.finished.connect(self.preview_build_finished)
        self.preview_progress = None
        self.preview_prompting = False
        self.offered_previews = set()
        self.fonts = []
        self.current = None
        self.asset = None
        self.selected_path = None
        self.token = 0
        self.closing = False
        self.busy = False
        self.catalog_date = ''
        self.catalog_loading = False
        self.catalog_notice = ''
        self.build_ui()
        self.service.download_progress.connect(self.show_progress)
        try:
            fonts, date = parse_catalog(catalog_cache().read_bytes())
        except (OSError, ValueError, TypeError, KeyError):
            fonts, date = bundled_catalog()
        self.set_catalog(fonts, date)
        self.update_preview()
        # Paint cached image previews immediately, then reconcile with the source.
        self.catalog_timer = QTimer(self)
        self.catalog_timer.setInterval(5 * 60 * 1000)
        self.catalog_timer.timeout.connect(self.refresh_catalog)
        context.translations.changed.connect(self.retranslate)

    def word(self, key, **values):
        return self.words[key].format(**values)

    def build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        self.splitter = split
        left = QFrame()
        left.setObjectName('fontPanel')
        left.setMinimumWidth(270)
        controls = QVBoxLayout(left)
        controls.setContentsMargins(14, 14, 14, 14)
        controls.setSpacing(10)
        self.list_title = QLabel(self.word('title'))
        self.list_title.setObjectName('fontSection')
        controls.addWidget(self.list_title)
        self.search = ImeSearchLineEdit()
        self.search.setPlaceholderText(self.word('search'))
        self.search.query_changed.connect(self.filter_list)
        controls.addWidget(self.search)
        self.mode = QComboBox()
        self.mode.addItems([self.word('ttf_all' if self.ttf_only else 'all'), self.word('saved_filter')])
        self.style_combo(self.mode)
        self.mode.currentIndexChanged.connect(self.filter_list)
        controls.addWidget(self.mode)
        self.list = QListWidget()
        self.list.setStyleSheet(LIST_STYLE)
        self.list.setUniformItemSizes(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.currentItemChanged.connect(self.select_font)
        self.list.itemClicked.connect(self.retry_variants)
        controls.addWidget(self.list, 1)
        self.count = QLabel()
        self.count.setWordWrap(True)
        self.count.setObjectName('fontMuted')
        controls.addWidget(self.count)
        self.refresh = QPushButton(self.word('refresh'))
        self.refresh.setStyleSheet(SECONDARY_STYLE)
        self.refresh.clicked.connect(self.refresh_catalog)
        controls.addWidget(self.refresh)
        split.addWidget(left)
        panel = QFrame()
        panel.setObjectName('fontPanel')
        panel.setMinimumWidth(350)
        right = QVBoxLayout(panel)
        right.setContentsMargins(14, 14, 14, 14)
        right.setSpacing(10)
        self.name = QLabel(self.word('choose'))
        self.name.setObjectName('fontName')
        self.name.setTextFormat(Qt.TextFormat.PlainText)
        self.name.setWordWrap(True)
        right.addWidget(self.name)
        self.variants = QComboBox()
        self.variants.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.style_combo(self.variants)
        self.variants.setEnabled(False)
        self.variants.currentIndexChanged.connect(self.select_variant)
        right.addWidget(self.variants)
        self.preview = FontPreview(self, self.context.translations.language)
        self.preview.setMinimumSize(0, 180)
        self.preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        right.addWidget(self.preview, 1)
        self.status = QLabel()
        self.status.setObjectName('fontMuted')
        self.status.setWordWrap(True)
        right.addWidget(self.status)
        actions = QHBoxLayout()
        self.download = QPushButton(self.word('download'))
        self.download.setStyleSheet(PRIMARY_STYLE)
        self.download.clicked.connect(self.download_font)
        self.download.setEnabled(False)
        self.download.setVisible(self.embedded)
        self.use = QPushButton(self.word('use'))
        self.use.setStyleSheet(PRIMARY_STYLE)
        self.use.clicked.connect(self.use_font)
        self.use.setEnabled(False)
        self.use.setVisible(not self.embedded)
        actions.addWidget(self.download)
        actions.addWidget(self.use)
        right.addLayout(actions)
        links = QHBoxLayout()
        self.source = QPushButton(self.word('source'))
        self.source.setStyleSheet(SECONDARY_STYLE)
        self.source.clicked.connect(self.open_source)
        self.source.setEnabled(False)
        links.addWidget(self.source)
        self.retry = QPushButton(self.word('reload'))
        self.retry.setStyleSheet(SECONDARY_STYLE)
        self.retry.clicked.connect(self.reload_preview)
        links.addWidget(self.retry)
        right.addLayout(links)
        self.create_previews = QPushButton(self.word('create_previews'))
        self.create_previews.setStyleSheet(SECONDARY_STYLE)
        self.create_previews.clicked.connect(lambda: self.offer_preview_generation(manual=True))
        self.create_previews.hide()
        right.addWidget(self.create_previews)
        self.storage_hint = QLabel(self.word('storage'))
        self.storage_hint.setWordWrap(True)
        self.storage_hint.setObjectName('fontMuted')
        self.storage_hint.setVisible(not self.embedded)
        right.addWidget(self.storage_hint)
        split.addWidget(panel)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([310, 650])
        layout.addWidget(split, 1)
        self.close_button = None
        if not self.embedded:
            footer = QHBoxLayout()
            footer.addStretch()
            self.close_button = QPushButton(self.word('close'))
            self.close_button.setStyleSheet(SECONDARY_STYLE)
            self.close_button.clicked.connect(lambda _checked=False: self.close_requested.emit())
            footer.addWidget(self.close_button)
            layout.addLayout(footer)

    @staticmethod
    def style_combo(combo):
        combo.setStyleSheet(ALIGNMENT_COMBO_STYLE)
        combo.view().setStyleSheet(ALIGNMENT_MENU_STYLE)

    def set_catalog(self, fonts, date):
        self.fonts = sorted(fonts, key=lambda font: font.name.casefold())
        self.catalog_date = date
        if self.ttf_catalog is not None:
            self.ttf_catalog.set_fonts(self.fonts)
        self.filter_list()
        # Rebind selected metadata if the source changed an existing entry.
        item = self.list.currentItem()
        if item is not None and self.current != item.data(Qt.ItemDataRole.UserRole):
            self.select_font(item)
        self.update_preview_creation_button()

    def filter_list(self, *_args):
        query = self.search.search_text().strip().casefold()
        folder = font_storage()
        saved_repos = ({p.name.split('--', 1)[0].casefold() for p in folder.iterdir()
                        if p.is_file() and (p.suffix.lower() == '.ttf' if self.ttf_only
                                            else p.suffix.lower() in ('.ttf', '.otf'))}
                       if folder.is_dir() else set())
        selected_repo = self.current.repo if self.current else None
        selected = None
        with QSignalBlocker(self.list):
            self.list.clear()
            for font in self.fonts:
                if self.ttf_catalog is not None and not self.ttf_catalog.assets_for(font.repo):
                    continue
                saved = font.repo.casefold() in saved_repos
                if self.mode.currentIndex() == 1 and not saved:
                    continue
                if query and query not in f'{font.name} {font.repo}'.casefold():
                    continue
                item = QListWidgetItem(('✓ ' if saved else '') + font.name)
                item.setData(Qt.ItemDataRole.UserRole, font)
                self.list.addItem(item)
                if font.repo == selected_repo:
                    selected = item
            if selected is not None:
                self.list.setCurrentItem(selected)
        self.update_count()
        if selected is None and self.current is not None:
            self.select_font(None)

    def ttf_catalog_changed(self):
        if not self.closing:
            self.filter_list()
            self.update_preview_creation_button()
            if not self.ttf_catalog.pending_count:
                QTimer.singleShot(0, self.offer_preview_generation)

    def update_count(self):
        text = self.word('count', count=self.list.count(),
                         date=self.catalog_date or self.word('unknown'))
        notice = self.word('refreshing') if self.catalog_loading else self.catalog_notice
        if self.ttf_catalog is not None and self.ttf_catalog.pending_count:
            checking = self.word('ttf_checking', count=self.ttf_catalog.pending_count)
            notice = f'{notice} · {checking}' if notice else checking
        self.count.setText(text + (' · ' + notice if notice else ''))

    def refresh_catalog(self):
        if self.closing or self.catalog_loading or not self.isVisible():
            return
        self.catalog_loading = True
        self.catalog_notice = ''
        self.refresh.setEnabled(False)
        self.update_count()

        def loaded(fonts, date):
            if self.closing:
                return
            self.catalog_loading = False
            self.refresh.setEnabled(True)
            self.set_catalog(fonts, date)
            QTimer.singleShot(0, self.offer_preview_generation)

        def failed(message):
            if self.closing:
                return
            self.catalog_loading = False
            self.catalog_notice = self.word('offline')
            self.refresh.setEnabled(True)
            self.update_count()
            logging.info('Keeping saved font catalogue: %s', message)
        self.service.refresh_catalog(loaded, failed)

    def missing_preview_fonts(self):
        return [font for font in self.fonts if not preview_complete(font.repo)
                and (self.ttf_catalog is None or self.ttf_catalog.assets_for(font.repo))]

    def update_preview_creation_button(self):
        self.create_previews.setVisible(bool(self.missing_preview_fonts()))
        self.create_previews.setEnabled(not self.preview_builder.running)

    def offer_preview_generation(self, manual=False):
        if self.closing or not self.isVisible() or self.preview_builder.running or self.preview_prompting:
            return
        fonts = self.missing_preview_fonts()
        if not manual:
            fonts = [font for font in fonts if font.repo not in self.offered_previews]
        if not fonts:
            return
        self.offered_previews.update(font.repo for font in fonts)
        self.preview_prompting = True
        prompt = QMessageBox(self)
        prompt.setWindowTitle(self.word('create_previews'))
        prompt.setIcon(QMessageBox.Icon.Question)
        prompt.setText(self.word('new_fonts', count=len(fonts)))
        prompt.setInformativeText(self.word('create_hint'))
        accept = prompt.addButton(self.word('create_previews'), QMessageBox.ButtonRole.AcceptRole)
        prompt.addButton(self.word('later'), QMessageBox.ButtonRole.RejectRole)
        prompt.setDefaultButton(accept)
        try:
            prompt.exec()
            accepted = prompt.clickedButton() is accept
        finally:
            self.preview_prompting = False
            prompt.deleteLater()
        if not accepted or self.closing:
            return
        # The catalogue may have changed while the question was open.
        active = {font.repo for font in self.fonts}
        fonts = [font for font in fonts if font.repo in active and not preview_complete(font.repo)]
        if not fonts:
            return
        self.preview_progress = QProgressDialog('', self.word('cancel'), 0, len(fonts), self)
        self.preview_progress.setWindowTitle(self.word('create_previews'))
        self.preview_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.preview_progress.setMinimumDuration(0)
        self.preview_progress.setMinimumWidth(420)
        self.preview_progress.setAutoClose(False)
        self.preview_progress.setAutoReset(False)
        self.preview_progress.canceled.connect(self.preview_builder.cancel)
        self.preview_progress.show()
        self.preview_builder.start(fonts)
        self.update_preview_creation_button()

    def preview_build_progress(self, done, total, name):
        if self.closing or self.preview_progress is None:
            return
        self.preview_progress.setLabelText(self.word('building', done=done, total=total, name=name))
        self.preview_progress.setMaximum(total)
        self.preview_progress.setValue(done)

    def preview_built(self, repo):
        if not self.closing and self.current is not None and self.current.repo == repo:
            self.preview.reload()

    def preview_build_finished(self, count, failed, cancelled):
        if self.preview_progress is not None:
            self.preview_progress.close()
            self.preview_progress.deleteLater()
            self.preview_progress = None
        if self.closing:
            return
        self.catalog_notice = self.word('build_cancelled' if cancelled else 'build_result',
                                        count=count, failed=failed)
        self.update_count()
        self.update_preview_creation_button()
        self.preview.reload()
        # Include fonts discovered by a periodic update during the previous batch.
        QTimer.singleShot(0, self.offer_preview_generation)

    def select_font(self, item, _previous=None):
        self.token += 1
        self.service.cancel_preview()
        self.busy = False
        self.asset = None
        self.font_ready.emit(None)
        self.current = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        self.source.setEnabled(self.current is not None)
        self.download.setEnabled(False)
        self.download.setText(self.word('download'))
        self.use.setEnabled(False)
        with QSignalBlocker(self.variants):
            self.variants.clear()
        self.variants.setEnabled(False)
        self.name.setText(self.current.name if self.current else self.word('choose'))
        self.status.clear()
        self.update_preview()
        if self.current is not None:
            self.status.setText(self.word('metadata'))
            self.load_variants()

    def retry_variants(self, _item):
        if self.current and self.asset is None and not self.service.pending:
            self.load_variants()

    def load_variants(self):
        if not self.current or self.closing:
            return
        token = self.token

        def ready(assets):
            if self.closing or token != self.token:
                return
            with QSignalBlocker(self.variants):
                self.variants.clear()
                for asset in assets:
                    self.variants.addItem(asset.label, asset)
                index = next((i for i, a in enumerate(assets)
                              if a.label in ('400', 'normal') or 'regular' in a.label.casefold()), 0)
                self.variants.setCurrentIndex(index)
            self.variants.setEnabled(True)
            self.select_variant()
        try:
            if self.ttf_catalog is not None:
                ready(self.ttf_catalog.assets_for(self.current.repo))
            else:
                self.service.resolve(self.current, ready, lambda message: self.failed(token, message))
        except Exception as error:
            logging.exception('Could not resolve font download files')
            self.failed(self.token, self.word('error', error=error))

    def select_variant(self, *_args):
        self.token += 1
        self.service.cancel_preview()
        self.busy = False
        self.asset = self.variants.currentData()
        self.status.clear()
        self.update_download_buttons()
        self.update_preview()

    def update_download_buttons(self):
        saved = self.saved_asset_available()
        self.download.setText(self.word('saved' if saved else 'download'))
        self.download.setEnabled(self.asset is not None and not saved and not self.busy)
        self.use.setEnabled(self.asset is not None and not self.busy)
        if saved:
            self.status.setText(self.word('kept', size=self.asset.saved_path.stat().st_size / 1048576))
        self.font_ready.emit(self.available_path())

    def update_preview(self, *_args):
        repo = self.current.repo if self.current else None
        url = self.asset.url if self.asset else None
        if self.ttf_only and repo and url and not preview_record(repo, url):
            # Existing family images stay instant if TTF was discovered after OTF.
            url = None
        self.preview.show_font(repo, url)

    def reload_preview(self):
        self.preview.reload()
        if self.current and self.asset is None:
            self.load_variants()

    def download_font(self, *, use_on_ready=False):
        if self.closing or not self.current or not self.asset or self.busy:
            return
        token = self.token
        asset = self.asset
        self.busy = True
        self.update_download_buttons()
        self.status.setText(self.word('fetching'))

        def ready(path):
            if token != self.token or self.closing:
                return
            try:
                register_font(str(path))
                self.busy = False
                self.update_download_buttons()
                self.update_preview()
                self.filter_list()
                if (use_on_ready and not self.closing and token == self.token
                        and self.asset == asset and self.saved_asset_available()):
                    self.selected_path = path
                    self.use_requested.emit(path)
            except Exception as error:
                logging.exception('Could not register downloaded font')
                self.failed(token, self.word('error', error=error))
        try:
            self.service.download_asset(self.current, self.asset, ready,
                                        lambda message: self.failed(token, message),
                                        ttf_only=self.ttf_only)
        except Exception as error:
            logging.exception('Could not start font download')
            self.failed(token, self.word('error', error=error))

    def show_progress(self, received, _total):
        if self.busy and not self.closing:
            self.status.setText(self.word('progress', size=received / 1024))

    def failed(self, token, message):
        if token != self.token or self.closing:
            return
        self.busy = False
        self.update_download_buttons()
        self.status.setText(message)

    def use_font(self):
        if self.closing or self.busy or self.asset is None:
            return
        if self.saved_asset_available():
            self.selected_path = self.asset.saved_path
            self.use_requested.emit(self.selected_path)
        else:
            self.download_font(use_on_ready=True)

    def open_source(self):
        if self.current is not None:
            QDesktopServices.openUrl(QUrl(self.current.page + '#라이선스'))

    def available_path(self):
        if not self.busy and self.saved_asset_available():
            return self.asset.saved_path
        return None

    def saved_asset_available(self):
        if self.asset is None or not self.asset.saved_path.is_file():
            return False
        return not self.ttf_only or is_truetype_file(self.asset.saved_path)

    def retranslate(self, _language=None):
        self.words = WORDS.get(self.context.translations.language, WORDS['kr'])
        self.search.setPlaceholderText(self.word('search'))
        self.list_title.setText(self.word('title'))
        with QSignalBlocker(self.mode):
            self.mode.setItemText(0, self.word('ttf_all' if self.ttf_only else 'all'))
            self.mode.setItemText(1, self.word('saved_filter'))
        for button, key in ((self.refresh, 'refresh'), (self.use, 'use'), (self.source, 'source'),
                            (self.retry, 'reload'), (self.create_previews, 'create_previews')):
            button.setText(self.word(key))
        if self.close_button is not None:
            self.close_button.setText(self.word('close'))
        self.name.setText(self.current.name if self.current else self.word('choose'))
        self.storage_hint.setText(self.word('storage'))
        self.preview.language = self.context.translations.language
        self.preview.update()
        self.update_download_buttons()
        self.update_count()

    def showEvent(self, event):
        super().showEvent(event)
        if not self.closing:
            self.catalog_timer.start()
            if self.ttf_catalog is not None:
                self.ttf_catalog.set_enabled(True)
            QTimer.singleShot(0, self.refresh_catalog)

    def hideEvent(self, event):
        self.catalog_timer.stop()
        if self.ttf_catalog is not None:
            self.ttf_catalog.set_enabled(False)
        super().hideEvent(event)

    def shutdown(self):
        if self.closing:
            return
        self.closing = True
        self.catalog_timer.stop()
        self.ttf_refresh_timer.stop()
        if self.ttf_catalog is not None:
            self.ttf_catalog.stop()
        self.preview_builder.cancel()
        if self.preview_progress is not None:
            self.preview_progress.close()
            self.preview_progress.deleteLater()
            self.preview_progress = None
        self.service.stop()
        self.preview.release()


class OnlineFontDialog(QDialog):
    """Modal wrapper retained for the portrait editor's font chooser."""
    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.selected_path = None
        self.setObjectName('fontManager')
        self.setStyleSheet(MANAGER_STYLE)
        self.panel = OnlineFontPanel(context, self)
        self.setWindowTitle(self.panel.word('title'))
        self.resize(980, 700)
        self.setMinimumSize(800, 560)
        layout = QVBoxLayout(self)
        layout.addWidget(self.panel)
        self.panel.use_requested.connect(self.use_font)
        self.panel.close_requested.connect(self.reject)
        context.translations.changed.connect(self.update_title)

    def update_title(self, _language=None):
        self.setWindowTitle(self.panel.word('title'))

    def use_font(self, path):
        self.selected_path = path
        self.accept()

    def done(self, result):
        self.panel.shutdown()
        super().done(result)

"""Asynchronous metadata/font downloads using Qt's existing network module."""

import json
import logging
from pathlib import Path
from urllib.parse import quote, urlparse

from PySide6.QtCore import QObject, QIODevice, QSaveFile, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from core.online_fonts import (
    CATALOG_URL, FONT_LIMIT, CatalogFont, FontAsset, archive_url, catalog_cache,
    css_assets, font_storage, is_font, parse_catalog,
)
from core.paths import settings_file
from core.font_previews import bundled_assets
from core.font_formats import is_truetype


def atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    target = QSaveFile(str(path))
    if not target.open(QIODevice.OpenModeFlag.WriteOnly):
        raise OSError(target.errorString())
    if target.write(data) != len(data):
        target.cancelWriting()
        raise OSError(target.errorString())
    if not target.commit():
        raise OSError(target.errorString())


class OnlineFontService(QObject):
    download_progress = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        self.pending = {}
        self.resolved = {}
        self.ttf_resolved = {}
        self.stopped = False
        self.index_path = settings_file().parent / 'online-font-assets.json'
        try:
            cached = json.loads(self.index_path.read_text(encoding='utf-8'))
            for repo, records in cached.items():
                assets = [FontAsset(repo, row['url'], row['label']) for row in records
                          if archive_url(row['url'], repo)
                          and row['url'].lower().endswith(('.ttf', '.otf'))]
                if assets:
                    self.resolved[repo] = assets
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            self.resolved = {}

    def cancel_preview(self):
        for reply, state in list(self.pending.items()):
            if state['group'] == 'preview':
                state['cancelled'] = True
                reply.abort()

    def stop(self):
        self.stopped = True
        for reply, state in list(self.pending.items()):
            state['cancelled'] = True
            reply.abort()

    def get(self, url, callback, failed, *, group='preview', limit=3 * 1024 * 1024,
            progress_callback=None):
        if self.stopped:
            return
        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(b'User-Agent', b'JHnode-PortraitManager/1.0')
        request.setTransferTimeout(12000)
        # Some CDN/proxy combinations stall binary responses over HTTP/2.
        request.setAttribute(QNetworkRequest.Attribute.Http2AllowedAttribute, False)
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        reply = self.manager.get(request)
        state = {'group': group, 'cancelled': False, 'large': False, 'data': bytearray(),
                 'finished': False, 'timed_out': False}
        self.pending[reply] = state
        deadline = QTimer(self)
        deadline.setSingleShot(True)

        def timeout():
            if not state['finished'] and not state['cancelled']:
                state['timed_out'] = True
                reply.abort()
        deadline.timeout.connect(timeout)
        deadline.start(18000)

        def consume():
            if state['cancelled']:
                return
            state['data'].extend(bytes(reply.readAll()))
            if len(state['data']) > limit:
                state['large'] = True
                reply.abort()

        def progress(received, total):
            if received > limit or total > limit:
                state['large'] = True
                reply.abort()
            elif progress_callback and not state['cancelled'] and not self.stopped:
                progress_callback(received, total)

        def finished():
            if state['finished']:
                return
            state['finished'] = True
            deadline.stop()
            deadline.deleteLater()
            consume()
            self.pending.pop(reply, None)
            try:
                if state['cancelled'] or self.stopped:
                    return
                if state['large']:
                    failed('이 파일은 미리보기 용량 제한을 초과합니다. 배포처에서 받아 주세요.')
                elif state['timed_out']:
                    failed('폰트 서버의 응답 시간이 초과되었습니다. 다시 선택해 주세요.')
                elif reply.error() != QNetworkReply.NetworkError.NoError:
                    failed('다운로드하지 못했습니다. 인터넷 연결을 확인하고 다시 선택해 주세요.')
                else:
                    callback(bytes(state['data']))
            except Exception as error:
                logging.exception('Online font response failed: %s', url)
                failed(f'폰트 정보를 처리하지 못했습니다. {error}')
            finally:
                reply.deleteLater()

        reply.readyRead.connect(consume)
        reply.downloadProgress.connect(progress)
        reply.finished.connect(finished)

    def refresh_catalog(self, ready, failed):
        def loaded(data):
            fonts, date = parse_catalog(data)
            try:
                atomic_write(catalog_cache(), data)
            except OSError:
                # A cache write failure must not keep removed entries visible.
                logging.warning('Could not save updated font catalogue', exc_info=True)
            ready(fonts, date)
        self.get(CATALOG_URL, loaded, failed, group='catalog')

    def resolve(self, font: CatalogFont, ready, failed, *, ttf_only=False):
        def supported(assets):
            return [a for a in assets if not ttf_only or a.saved_path.suffix.lower() == '.ttf']

        if ttf_only and font.repo in self.ttf_resolved:
            ready(self.ttf_resolved[font.repo])
            return
        assets = supported(bundled_assets(font.repo))
        if assets:
            ready(assets)
            return
        assets = supported(self.resolved.get(font.repo, []))
        if assets:
            ready(assets)
            return

        def remember(assets):
            if ttf_only:
                assets = supported(assets)
                self.ttf_resolved[font.repo] = assets
                ready(assets)  # An empty, successful result means no TTF is provided.
                return
            if not assets:
                failed('TTF·OTF 파일이 제공되지 않는 폰트입니다. 배포처에서 확인해 주세요.')
                return
            self.resolved[font.repo] = assets
            try:
                index = {repo: [{'url': a.url, 'label': a.label} for a in items]
                         for repo, items in self.resolved.items()}
                atomic_write(self.index_path, json.dumps(index, ensure_ascii=False).encode('utf-8'))
            except OSError:
                pass  # Previewing remains available when metadata cannot be cached.
            ready(assets)

        def fallback(_error=None):
            url = f'https://data.jsdelivr.com/v1/package/gh/fonts-archive/{font.repo}@main/flat'

            def listed(data):
                assets = []
                document = json.loads(data)
                if not isinstance(document, dict) or not isinstance(document.get('files'), list):
                    raise ValueError('Invalid archive file listing')
                for item in document['files']:
                    if not isinstance(item, dict):
                        continue
                    name = item.get('name', '')
                    if not isinstance(name, str) or not name.startswith('/'):
                        continue
                    if Path(name).suffix.lower() not in ('.ttf', '.otf'):
                        continue
                    if ttf_only and Path(name).suffix.lower() != '.ttf':
                        continue
                    if item.get('size', 0) > FONT_LIMIT:
                        continue
                    url = f'https://cdn.jsdelivr.net/gh/fonts-archive/{font.repo}@main{quote(name)}'
                    if archive_url(url, font.repo):
                        assets.append(FontAsset(font.repo, url, Path(name).stem))
                # Prefer TTF when the archive has the same face in both formats.
                chosen = {}
                for asset in sorted(assets, key=lambda a: not a.url.lower().endswith('.ttf')):
                    chosen.setdefault(asset.label.casefold(), asset)
                remember(list(chosen.values()))
            self.get(url, listed, failed)

        def css_loaded(data):
            assets = css_assets(font, data.decode('utf-8-sig'), ttf_only=ttf_only)
            remember(assets) if assets else fallback()
        self.get(font.css, css_loaded, fallback)

    def download_asset(self, font: CatalogFont, asset: FontAsset, ready, failed, *, ttf_only=False):
        if not archive_url(asset.url, asset.repo):
            failed('잘못된 폰트 주소입니다.')
            return
        if ttf_only and asset.saved_path.suffix.lower() != '.ttf':
            failed('게임용으로는 TTF 파일만 다운로드할 수 있습니다.')
            return
        if asset.saved_path.is_file():
            try:
                data = asset.saved_path.read_bytes()
                if (len(data) <= FONT_LIMIT and is_font(data)
                        and (not ttf_only or is_truetype(data))):
                    ready(asset.saved_path)
                    return
            except OSError:
                pass

        def loaded(data):
            if ttf_only and not is_truetype(data):
                failed('실제 TTF 형식의 폰트가 아니므로 저장하지 않았습니다.')
                return
            atomic_write(asset.saved_path, data)
            metadata = {'repo': font.repo, 'name': font.name, 'variant': asset.label,
                        'url': asset.url, 'archive': font.page,
                        'source': font.source, 'license': font.license}
            atomic_write(font_storage() / (asset.filename + '.json'),
                         json.dumps(metadata, ensure_ascii=False, indent=2).encode('utf-8'))
            ready(asset.saved_path)
        self.fetch_asset_data(asset, loaded, failed, progress_callback=self.download_progress.emit)

    def fetch_asset_data(self, asset: FontAsset, ready, failed, *, progress_callback=None):
        """Fetch a validated font in memory; only download_asset writes font files."""
        if not archive_url(asset.url, asset.repo):
            failed('잘못된 폰트 주소입니다.')
            return

        def loaded(data):
            if not is_font(data):
                failed('사용 가능한 TTF·OTF 폰트 파일이 아닙니다.')
                return
            ready(data)

        # Keep the CDN URL as the file identity; a mirror never creates a duplicate.
        # The same public repository file is also available directly from GitHub.
        prefix = f'/gh/fonts-archive/{asset.repo}'
        relative = urlparse(asset.url).path[len(prefix):]
        if relative.startswith('@main/'):
            relative = relative[len('@main'):]
        github = f'https://raw.githubusercontent.com/fonts-archive/{asset.repo}/main{relative}'

        def fallback(_message):
            self.get(asset.url, loaded, failed, limit=FONT_LIMIT,
                     progress_callback=progress_callback)
        self.get(github, loaded, fallback, limit=FONT_LIMIT,
                 progress_callback=progress_callback)

"""Online font metadata and user-owned storage; no font binaries are bundled."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlparse

from core.paths import resource_path, settings_file


CATALOG_URL = ('https://raw.githubusercontent.com/seulkikaang/'
               'korean-vibe-fonts/main/references/fonts_archive_commercial.json')
FONT_LIMIT = 40 * 1024 * 1024


def font_storage() -> Path:
    return settings_file().parent / 'fonts'


def catalog_cache() -> Path:
    return settings_file().parent / 'online-font-catalog.json'


def downloaded_font_label(path: Path) -> str:
    if path.parent == font_storage():
        try:
            info = json.loads(path.with_suffix(path.suffix + '.json').read_text(encoding='utf-8'))
            return f"{info['name']} · {info['variant']}"
        except (OSError, ValueError, TypeError, KeyError):
            pass
    return path.name


@dataclass(frozen=True)
class CatalogFont:
    repo: str
    name: str
    category: str
    css: str
    source: str
    license: str
    preview_css: str = ''
    preview_family: str = ''

    @property
    def page(self):
        return f'https://github.com/fonts-archive/{self.repo}'


@dataclass(frozen=True)
class FontAsset:
    repo: str
    url: str
    label: str

    @property
    def filename(self):
        # Neither catalogue values nor remote paths become local directories.
        stem = re.sub(r'[^a-zA-Z0-9_-]', '_', self.repo)[:70]
        digest = hashlib.sha256(self.url.encode()).hexdigest()[:20]
        suffix = Path(urlparse(self.url).path).suffix.lower()
        return f'{stem}--{digest}{suffix}'

    @property
    def saved_path(self):
        return font_storage() / self.filename

def archive_url(url: str, repo: str) -> bool:
    parsed = urlparse(url)
    prefix = f'/gh/fonts-archive/{repo}'
    return (parsed.scheme == 'https' and parsed.netloc == 'cdn.jsdelivr.net'
            and (parsed.path.startswith(prefix + '/')
                 or parsed.path.startswith(prefix + '@main/'))
            and '..' not in unquote(parsed.path).split('/'))


def parse_catalog(data: bytes):
    document = json.loads(data.decode('utf-8-sig'))
    if not isinstance(document, dict) or not isinstance(document.get('fonts'), list):
        raise ValueError('Invalid font catalogue')
    fonts, seen = [], set()
    for raw in document.get('fonts', []):
        if not isinstance(raw, dict):
            continue
        repo = raw.get('repo', '')
        if not isinstance(repo, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]+', repo):
            continue
        css = raw.get('css', raw.get('full_stylesheet_url', ''))
        if repo in seen or not isinstance(css, str) or not archive_url(css, repo):
            continue
        seen.add(repo)
        preview_css = raw.get('preview_css', raw.get('stylesheet_url', css))
        if not isinstance(preview_css, str) or not archive_url(preview_css, repo):
            preview_css = css
        application = raw.get('application', {})
        family = raw.get('preview_family', application.get('heading_family', repo)
                         if isinstance(application, dict) else repo)
        family = str(family).split(',')[0].strip().strip('\"\'')
        fonts.append(CatalogFont(repo, str(raw.get('name', repo)),
                                 str(raw.get('category', '')), css,
                                 str(raw.get('source', raw.get('upstream_page', ''))),
                                 str(raw.get('license_page', raw.get('license', ''))),
                                 preview_css, family))
    # An explicitly empty source list is authoritative; malformed entries are not.
    if not fonts and document['fonts']:
        raise ValueError('Empty font catalogue')
    return fonts, str(document.get('verified_on', ''))


def bundled_catalog():
    return parse_catalog(resource_path('online_font_catalog.json').read_bytes())


def css_assets(font: CatalogFont, text: str, *, ttf_only=False) -> list[FontAsset]:
    result = []
    for block in re.findall(r'@font-face\s*\{([^}]+)\}', text, re.I):
        urls = re.findall(r'url\(\s*[\'\"]?([^\s\)\'\"]+)', block, re.I)
        native = [url for url in urls if archive_url(url, font.repo)
                  and Path(urlparse(url).path).suffix.lower() in ('.ttf', '.otf')]
        if ttf_only:
            native = [url for url in native if Path(urlparse(url).path).suffix.lower() == '.ttf']
        if not native:
            continue
        url = next((url for url in native if url.lower().endswith('.ttf')), native[0])
        weight = re.search(r'font-weight\s*:\s*([^;]+)', block, re.I)
        style = re.search(r'font-style\s*:\s*([^;]+)', block, re.I)
        label = (weight.group(1).strip() if weight else '400')
        if style and style.group(1).strip() != 'normal':
            label += ' · ' + style.group(1).strip()
        if url not in {asset.url for asset in result}:
            result.append(FontAsset(font.repo, url, label))
    return result


def is_font(data: bytes) -> bool:
    return len(data) >= 12 and data[:4] in (b'\x00\x01\x00\x00', b'OTTO', b'true', b'ttcf')

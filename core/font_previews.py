"""Read bundled/user preview images and persist generated image metadata."""

from functools import lru_cache
import json
import os
from pathlib import Path
import tempfile

from core.online_fonts import FontAsset, archive_url
from core.paths import resource_path, settings_file


PREVIEW_TEXT = '검은사막 너무 좋아!'


def preview_storage():
    return settings_file().parent / 'font-previews'


@lru_cache(maxsize=1)
def preview_catalog():
    try:
        data = json.loads(resource_path('font_previews.json').read_text(encoding='utf-8'))
        return data.get('families', {})
    except (OSError, ValueError, AttributeError):
        return {}


def bundled_assets(repo):
    return [FontAsset(repo, row['url'], row['label'])
            for row in preview_catalog().get(repo, {}).get('variants', [])
            if archive_url(row['url'], repo)]


@lru_cache(maxsize=1)
def generated_catalog():
    try:
        data = json.loads((preview_storage() / 'index.json').read_text(encoding='utf-8'))
        return data.get('families', {}) if data.get('text') == PREVIEW_TEXT else {}
    except (OSError, ValueError, AttributeError):
        return {}


def save_generated_preview(font, record=None, *, complete=None):
    families = dict(generated_catalog())
    family = dict(families.get(font.repo, {'name': font.name, 'variants': []}))
    variants = list(family['variants'])
    if record is not None:
        variants = [row for row in variants if row['url'] != record['url']]
        variants.append(record)
    family.update(name=font.name, variants=variants)
    if complete is not None:
        family['complete'] = complete
    families[font.repo] = family
    storage = preview_storage()
    storage.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=storage,
                                         prefix='index-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({'text': PREVIEW_TEXT, 'families': families}, stream, ensure_ascii=False)
        os.replace(temporary, storage / 'index.json')
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    generated_catalog.cache_clear()


def preview_complete(repo):
    bundled = preview_catalog().get(repo, {})
    generated = generated_catalog().get(repo, {})
    family = bundled or generated
    if not bundled and not generated.get('complete', False):
        return False
    variants = family.get('variants', [])
    return bool(variants) and all(preview_images_exist(row) for row in variants)


def preview_images_exist(row):
    filenames = [row.get('image', '')]
    if row.get('example_image') is not None:
        filenames.append(row['example_image'])
    for filename in filenames:
        path = preview_image_path(filename)
        if path is None or not path.is_file():
            return False
    return True


def preview_record(repo, url=None):
    variants = (generated_catalog().get(repo, {}).get('variants', [])
                + preview_catalog().get(repo, {}).get('variants', []))
    variants = [row for row in variants if preview_images_exist(row)]
    if url:
        key = url.replace('@main/', '/')
        return next((row for row in variants if row['url'].replace('@main/', '/') == key), None)
    return next((row for row in variants if row['label'].casefold() in ('400', 'normal')
                 or 'regular' in row['label'].casefold()), variants[0] if variants else None)


def preview_image_path(filename):
    if not isinstance(filename, str) or Path(filename).name != filename or not filename.endswith('.png'):
        return None
    if filename.startswith('user-'):
        return preview_storage() / 'images' / filename
    return resource_path('font_previews', filename)

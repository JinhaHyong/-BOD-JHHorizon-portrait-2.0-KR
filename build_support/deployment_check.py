"""Exercise the packaged app without reading user settings or real game files."""

import json
import os
from pathlib import Path
import sys
import tempfile
import time
import traceback


def run(report_path):
    report_path = Path(report_path).absolute()
    result = {'application': 'JHnode', 'frozen': bool(getattr(sys, 'frozen', False)),
              'checks': [], 'success': False, 'executable': sys.executable}

    def check(name, action):
        try:
            detail = action()
            result['checks'].append({'name': name, 'passed': True, 'detail': detail})
        except Exception:
            result['checks'].append({'name': name, 'passed': False, 'error': traceback.format_exc()})

    def require(value, message):
        if not value:
            raise AssertionError(message)

    try:
        with tempfile.TemporaryDirectory(prefix='JHnode-deployment-') as temporary:
            root = Path(temporary)
            # Set the storage location before importing any application code.
            os.environ['LOCALAPPDATA'] = str(root / 'appdata')
            os.environ['APPDATA'] = str(root / 'roaming')
            os.environ['QT_QPA_PLATFORM'] = 'windows'

            import PIL
            from PIL import Image, _imaging
            import PySide6
            from PySide6.QtCore import QCoreApplication
            from PySide6.QtGui import QColor, QImage, QRawFont
            from PySide6.QtNetwork import QSslSocket
            from PySide6.QtWidgets import QApplication
            from core.context import AppContext
            from core.paths import APP_ROOT, resource_path, settings_file
            from core.settings import Settings
            from core.portrait_edit import TextOverlay
            from ui.font_registry import set_layer_font_file
            from ui.text_canvas import render_portrait, text_document
            from ui.text_editor import TextEditorDialog
            from ui.portrait_window import PortraitWindow
            from ui.font_window import FontWindow
            from ui.theme import install_theme
            from services.font_service import FontService
            from services.single_instance import SingleInstance

            app = QApplication.instance() or QApplication([])
            app.setStyle('Fusion')
            bundle = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])).resolve()

            def bundled_dependencies():
                require(result['frozen'], 'Run the packaged EXE for this check')
                paths = {'PySide6': PySide6.__file__, 'Pillow': PIL.__file__, 'Pillow imaging': _imaging.__file__}
                for name, value in paths.items():
                    require(Path(value).resolve().is_relative_to(bundle), f'{name} was loaded outside the bundle')
                require(app.platformName() == 'windows', 'Windows Qt plugin was not loaded')
                require(APP_ROOT == Path(sys.executable).resolve().parent,
                        'User folder root must be beside the EXE')
                return {'paths': paths, 'platform': app.platformName(),
                        'app_root': str(APP_ROOT), 'bundle': str(bundle)}
            check('bundled Python, Qt, Pillow and Windows plugin', bundled_dependencies)

            def resources():
                require(resource_path('아이콘.ico').is_file(), 'Missing icon')
                require(resource_path('fonts', 'NanumGothic-Bold.ttf').is_file(), 'Missing bundled font')
                license_path = resource_path('font_licenses', 'NanumGothic-OFL.txt')
                require(b'SIL OPEN FONT LICENSE' in license_path.read_bytes(), 'Missing OFL license')
                require(not resource_path('online_font_catalog.json').exists(), 'Old online catalogue is bundled')
                return {'bundled_font': 'NanumGothic Bold', 'OFL_license': True, 'online_catalogue': False}
            check('bundled OFL font, license and translations', resources)

            def tls():
                backends = QSslSocket.availableBackends()
                require(QSslSocket.supportsSsl(), 'TLS is not available')
                require('schannel' in backends, 'Windows TLS backend is not bundled')
                return backends
            check('Windows TLS backend for online fonts', tls)

            current, new = root / 'current', root / 'new'
            current.mkdir()
            new.mkdir()
            Image.new('RGB', (320, 400), 'red').save(current / 'character.bmp')
            Image.new('RGB', (320, 400), 'blue').save(new / 'portrait.bmp')
            game = root / 'test-game'
            (game / 'bin64').mkdir(parents=True)
            (game / 'bin64/BlackDesert64.exe').write_bytes(b'JHnode test marker; never executed')
            settings = Settings(settings_file())
            settings.update(portrait_folder=str(current), new_portrait_folder=str(new),
                            font_folder=str(game / 'prestringtable/font'),
                            extra_font_folders=[str(resource_path('fonts'))])
            context = AppContext.create(settings)
            install_theme(app, settings)
            sample = resource_path('fonts', 'NanumGothic-Bold.ttf')

            def text_rendering():
                image = QImage(320, 400, QImage.Format.Format_RGB32)
                image.fill(QColor('blue'))
                layer = TextOverlay(text='검은사막 너무 좋아!', x=15, y=20, width=290, height=100)
                set_layer_font_file(layer, sample)
                actual = QRawFont.fromFont(text_document(layer).defaultFont())
                expected = QRawFont(str(sample), 32)
                # DirectWrite normalizes family/style names differently from
                # QRawFont(file). Compare the loaded face's binary tables.
                require(actual.isValid() and expected.isValid(), 'Invalid font face')
                for table in ('head', 'hhea', 'maxp'):
                    require(actual.fontTable(table) == expected.fontTable(table),
                            'Font face mismatch: ' + table)
                require(actual.weight() == expected.weight(), 'Font weight mismatch')
                rendered = render_portrait(image, [layer])
                require(rendered != image, 'Text was not rendered')
                editor = TextEditorDialog(context, image, [layer])
                require(editor.layers()[0].font_style == layer.font_style, 'Editor lost the font style')
                editor.reject()
                editor.deleteLater()
                return {'font': layer.font_family, 'style': layer.font_style, 'weight': layer.font_weight}
            check('Korean text, chosen font face and text editor', text_rendering)

            def font_window():
                window = FontWindow(context)
                try:
                    require(window.preview_font(sample), 'Local preview failed')
                    require(not hasattr(window, 'selected_label'), 'Old apply caption is present')
                    require(hasattr(window, 'font_site_button'), 'External font-site link is missing')
                    require(not hasattr(window, 'tabs'), 'Old online tab is present')
                    return {'local_fonts': True, 'external_font_site_link': True, 'automatic_downloads': False}
                finally:
                    window.close()
                    window.deleteLater()
            check('PC font window and external font-site link', font_window)

            def replacement():
                window = PortraitWindow(context)
                window.show_info = lambda *_args: None
                window.show_warning = lambda message: require(False, message)
                def wait(predicate):
                    deadline = time.monotonic() + 12
                    while not predicate() and time.monotonic() < deadline:
                        app.processEvents()
                        time.sleep(0.01)
                    require(predicate(), 'Timed out waiting for a portrait operation')
                try:
                    wait(lambda: len(window.current_tiles.tiles) == len(window.new_tiles.tiles) == 1)
                    window.thumbnail_clicked(window.current_tiles.tiles[0], True)
                    window.thumbnail_clicked(window.new_tiles.tiles[0], False)
                    wait(lambda: len(window.preview_snapshots) == 2 and not window.pending_previews)
                    original = (current / 'character.bmp').read_bytes()
                    window.replace_photo()
                    require((current / 'character.bmp').read_bytes() == (new / 'portrait.bmp').read_bytes(), 'Portrait copy mismatch')
                    backups = list((current / 'backup').glob('*.bmp'))
                    require(len(backups) == 1 and backups[0].read_bytes() == original, 'Portrait backup mismatch')
                    return {'portrait_copy': True, 'backup': True}
                finally:
                    window.loader.stop()
                    window.loader.pool.waitForDone(15000)
                    app.processEvents()
                    window.close()
                    window.deleteLater()
            check('asynchronous portraits, replacement and backup', replacement)

            def font_install():
                target = game / 'prestringtable/font'
                service = FontService()
                service.apply(sample, target)
                backup = service.apply(sample, target)
                require((target / 'pearl.ttf').read_bytes() == sample.read_bytes(), 'Font copy mismatch')
                require(backup.read_bytes() == sample.read_bytes(), 'Font backup mismatch')
                return True
            check('TTF copy into a temporary game location and backup', font_install)

            def storage_and_ipc():
                stale = Settings(settings.path)
                settings.update(portrait_text_drafts={'example': {'layers': []}})
                stale.update(theme_mode='dark')
                require('example' in Settings(settings.path).get('portrait_text_drafts'), 'Stale writer lost a draft')
                require(settings.backup_path.is_file(), 'Settings backup missing')
                guard = SingleInstance(root / 'instance-settings.json', app)
                try:
                    require(guard.start(), 'Could not create the instance lock/local pipe')
                finally:
                    guard.close()
                return {'settings_backup': True, 'local_pipe': True}
            check('settings protection and single-instance Windows IPC', storage_and_ipc)
            QCoreApplication.sendPostedEvents()
            app.processEvents()
            result['success'] = all(row['passed'] for row in result['checks'])
    except Exception:
        result['fatal_error'] = traceback.format_exc()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result['success'] else 1

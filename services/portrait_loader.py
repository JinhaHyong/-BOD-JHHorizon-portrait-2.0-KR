"""Bounded background portrait loading, persistent thumbnails, and stale-result guards."""

from collections import deque
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import logging
import os
from pathlib import Path
from threading import Event, Lock

from PySide6.QtCore import QObject, QRunnable, QSaveFile, QIODevice, QThreadPool, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QImage, QPainter

from core.text_presets import decode_layers
from services.portrait_service import PortraitService


THUMBNAIL_EDGE = 96
PREVIEW_EDGE = 342


def stamp_for(path):
    stat = Path(path).stat()
    return stat.st_size, stat.st_mtime_ns


def to_qimage(image):
    if image.mode != 'RGB':
        image = image.convert('RGB')
    data = image.tobytes()
    return QImage(data, image.width, image.height, image.width * 3, QImage.Format.Format_RGB888).copy()


def fit_image(image, edge):
    scaled = image.scaled(edge, edge, Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
    canvas = QImage(edge, edge, QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(Qt.GlobalColor.transparent)
    x, y = (edge - scaled.width()) // 2, (edge - scaled.height()) // 2
    painter = QPainter(canvas)
    try:
        painter.drawImage(x, y, scaled)
    finally:
        painter.end()
    return canvas, (x, y, x + scaled.width(), y + scaled.height())


class ThumbnailCache:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.trim_lock = Lock()

    def path_for(self, path, stamp, layers):
        identity = {'version': 2, 'path': os.path.normcase(os.path.abspath(path)),
                    'stamp': stamp, 'edge': THUMBNAIL_EDGE,
                    'layers': [asdict(layer) for layer in layers] if layers is not None else None}
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        return self.folder / (digest + '.png')

    def read(self, path):
        image = QImage(str(path))
        return image if image.size().width() == THUMBNAIL_EDGE and image.height() == THUMBNAIL_EDGE else None

    def write(self, path, image):
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            target = QSaveFile(str(path))
            if not target.open(QIODevice.OpenModeFlag.WriteOnly):
                return
            if not image.save(target, 'PNG'):
                target.cancelWriting()
            else:
                target.commit()
        except OSError:
            logging.info('Portrait thumbnail cache unavailable', exc_info=True)

    def trim(self):
        if not self.trim_lock.acquire(blocking=False):
            return
        try:
            if not self.folder.is_dir():
                return
            files = []
            for path in self.folder.glob('*.png'):
                try:
                    stat = path.stat()
                    files.append((stat.st_mtime_ns, stat.st_size, path))
                except OSError:
                    pass
            total = sum(size for _time, size, _path in files)
            for _time, size, path in sorted(files):
                if total <= 128 * 1024 * 1024:
                    break
                try:
                    path.unlink()
                    total -= size
                except OSError:
                    pass
        finally:
            self.trim_lock.release()


class TaskSignals(QObject):
    done = Signal(int, object)


class BackgroundTask(QRunnable):
    def __init__(self, number, callback):
        super().__init__()
        self.number, self.callback = number, callback
        self.signals = TaskSignals()

    def run(self):
        try:
            result = self.callback()
        except Exception as error:
            result = {'error': str(error)}
        self.signals.done.emit(self.number, result)
        self.callback = None


class PortraitLoader(QObject):
    inventory_ready = Signal(str, object)
    thumbnails_ready = Signal(str, object)
    preview_ready = Signal(str, object)
    invalid = Signal(str, object)
    failed = Signal(str, str, str)

    def __init__(self, cache_folder, renderer, restore_fonts, parent=None):
        super().__init__(parent)
        self.cache = ThumbnailCache(cache_folder)
        self.renderer, self.restore_fonts = renderer, restore_fonts
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(3)
        self.states = {}
        self.jobs = {}
        self.number = 0
        self.active_thumbnails = 0
        self.next_side = 0
        self.stopped = False
        self.write_count = 0
        self.flush_timer = QTimer(self)
        self.flush_timer.setSingleShot(True)
        self.flush_timer.setInterval(16)
        self.flush_timer.timeout.connect(self.flush)
        self.submit({'kind': 'trim'}, self.cache.trim, priority=-10)

    def submit(self, context, callback, priority=0):
        self.number += 1
        task = BackgroundTask(self.number, callback)
        task.signals.done.connect(self.task_done)
        self.jobs[self.number] = (context, task)
        self.pool.start(task, priority)

    def start_folder(self, side, folder, drafts):
        old = self.states.get(side)
        if old is not None:
            old['cancel'].set()
            if old.get('preview_cancel'):
                old['preview_cancel'].set()
        state = {'cancel': Event(), 'records': {}, 'pending': deque(),
                 'drafts': deepcopy(drafts), 'prepared': {}, 'revisions': {},
                 'batch': [], 'priority': [], 'preview_serial': 0, 'preview_cancel': None}
        self.states[side] = state

        def scan():
            records = []
            with os.scandir(folder) as iterator:
                for item in iterator:
                    if state['cancel'].is_set():
                        return {'cancelled': True}
                    if item.name.lower().endswith('.bmp') and item.is_file():
                        try:
                            stat = item.stat()
                            records.append({'path': Path(item.path), 'stamp': (stat.st_size, stat.st_mtime_ns)})
                        except OSError:
                            pass
            records.sort(key=lambda record: record['path'].name.casefold())
            return {'records': records}
        self.submit({'kind': 'scan', 'side': side, 'state': state}, scan, priority=20)

    def layers_for(self, state, record):
        path = record['path']
        if path not in state['prepared']:
            raw = state['drafts'].get(os.path.normcase(os.path.abspath(path)))
            layers = None
            if isinstance(raw, dict) and raw.get('source_stamp') == list(record['stamp']):
                layers = self.restore_fonts(decode_layers(raw.get('layers')))
            state['prepared'][path] = (tuple(record['stamp']), layers)
        return state['prepared'][path]

    def prioritize(self, side, paths):
        state = self.states.get(side)
        if state is None or self.stopped:
            return
        state['priority'] = list(paths)
        pending = set(state['pending'])
        first = [path for path in paths if path in pending]
        chosen = set(first)
        state['pending'] = deque(first + [path for path in state['pending'] if path not in chosen])
        self.pump()

    def pump(self):
        if self.stopped:
            return
        while self.active_thumbnails < 3:
            sides = list(self.states)
            chosen = None
            for offset in range(len(sides)):
                index = (self.next_side + offset) % len(sides)
                state = self.states[sides[index]]
                # Bound completed-but-not-yet-displayed images as well as active jobs.
                if state['pending'] and len(state['batch']) < 64:
                    chosen = sides[index], state
                    self.next_side = index + 1
                    break
            if chosen is None:
                break
            side, state = chosen
            path = state['pending'].popleft()
            record = state['records'].get(path)
            if record is None:
                continue
            self.active_thumbnails += 1
            self.image_task(side, state, record, 'thumbnail')

    def image_task(self, side, state, record, kind, base=None, attempt=0):
        path = record['path']
        expected_stamp, layers = self.layers_for(state, record)
        layers = deepcopy(layers)
        revision = state['revisions'].get(path, 0)
        preview_cancel = state.get('preview_cancel') if kind == 'preview' else None
        serial = state['preview_serial']
        supplied_base = QImage(base) if base is not None else None

        def work():
            if state['cancel'].is_set() or (preview_cancel and preview_cancel.is_set()):
                return {'cancelled': True}
            stamp = stamp_for(path)
            actual_layers = layers if stamp == expected_stamp else None
            cache_path = self.cache.path_for(path, stamp, actual_layers)
            if kind == 'thumbnail':
                cached = self.cache.read(cache_path)
                if cached is not None and stamp_for(path) == stamp:
                    return {'path': path, 'stamp': stamp, 'image': cached}
            # Validation and RGB decoding share one open/read operation.
            image = (QImage(supplied_base) if supplied_base is not None and stamp == expected_stamp
                     else to_qimage(PortraitService().read_image(path)))
            if stamp_for(path) != stamp:
                return {'error': '원본 이미지가 변경되었습니다. 다시 선택해 주세요.', 'changed': True}
            painted = self.renderer(image, actual_layers) if actual_layers is not None else image
            scaled, bounds = fit_image(painted, THUMBNAIL_EDGE if kind == 'thumbnail' else PREVIEW_EDGE)
            if state['cancel'].is_set() or (preview_cancel and preview_cancel.is_set()):
                return {'cancelled': True}
            if kind == 'thumbnail':
                self.cache.write(cache_path, scaled)
            return {'path': path, 'stamp': stamp, 'image': scaled, 'bounds': bounds,
                    'base': image if kind == 'preview' else None,
                    'layers': actual_layers if kind == 'preview' else None}

        self.submit({'kind': kind, 'side': side, 'state': state, 'path': path, 'attempt': attempt,
                     'revision': revision, 'serial': serial}, work, priority=100 if kind == 'preview' else 0)

    def request_preview(self, side, path, base=None):
        state = self.states.get(side)
        if state is None or path not in state['records']:
            return
        if state['preview_cancel'] is not None:
            state['preview_cancel'].set()
        state['preview_cancel'] = Event()
        state['preview_serial'] += 1
        self.image_task(side, state, state['records'][path], 'preview', base)

    def cancel_preview(self, side):
        state = self.states.get(side)
        if state is not None:
            state['preview_serial'] += 1
            if state['preview_cancel'] is not None:
                state['preview_cancel'].set()

    def refresh_path(self, side, path, *, base=None, layers=None, stamp=None):
        state = self.states.get(side)
        if state is None or path not in state['records']:
            return
        state['revisions'][path] = state['revisions'].get(path, 0) + 1
        state['batch'] = [result for result in state['batch'] if result['path'] != path]
        if stamp is not None:
            state['records'][path]['stamp'] = tuple(stamp)
            state['prepared'][path] = (tuple(stamp), deepcopy(layers))
        else:
            state['prepared'].pop(path, None)
        state['pending'] = deque(item for item in state['pending'] if item != path)
        self.active_thumbnails += 1
        self.image_task(side, state, state['records'][path], 'thumbnail', base)

    def run_auxiliary(self, callback):
        self.submit({'kind': 'aux'}, callback, priority=-5)

    def refresh_many(self, side, records):
        """Queue a batch without allocating an active worker for every photo."""
        state = self.states.get(side)
        if state is None or self.stopped:
            return
        paths = []
        for record in records:
            path = record['path']
            if path not in state['records']:
                continue
            paths.append(path)
            state['revisions'][path] = state['revisions'].get(path, 0) + 1
            state['records'][path]['stamp'] = tuple(record['stamp'])
            state['prepared'][path] = (tuple(record['stamp']), deepcopy(record['layers']))
        changed = set(paths)
        state['batch'] = [item for item in state['batch'] if item['path'] not in changed]
        state['pending'] = deque(paths + [path for path in state['pending'] if path not in changed])
        self.prioritize(side, state['priority'])

    @Slot(int, object)
    def task_done(self, number, result):
        job = self.jobs.pop(number, None)
        if job is None:
            return
        context, _task = job
        kind = context['kind']
        if kind in ('aux', 'trim'):
            if isinstance(result, dict) and result.get('error'):
                logging.info('Background portrait task: %s', result['error'])
            return
        if kind == 'thumbnail':
            self.active_thumbnails -= 1
        side, state = context['side'], context['state']
        if self.stopped or self.states.get(side) is not state or state['cancel'].is_set():
            self.pump()
            return
        if kind == 'scan':
            if result.get('error'):
                self.failed.emit(side, kind, result['error'])
            else:
                records = result.get('records', [])
                state['records'] = {record['path']: record for record in records}
                state['pending'] = deque(state['records'])
                self.inventory_ready.emit(side, records)
        else:
            path = context['path']
            current = path in state['records'] and context['revision'] == state['revisions'].get(path, 0)
            if kind == 'preview':
                current = current and context['serial'] == state['preview_serial']
            if current and not result.get('cancelled'):
                if result.get('error'):
                    if kind == 'preview':
                        self.failed.emit(side, kind, result['error'])
                    elif result.get('changed') and context['attempt'] == 0:
                        state['prepared'].pop(path, None)
                        self.active_thumbnails += 1
                        self.image_task(side, state, state['records'][path], 'thumbnail', attempt=1)
                    else:
                        state['records'].pop(path, None)
                        state['batch'] = [item for item in state['batch'] if item['path'] != path]
                        self.invalid.emit(side, path)
                else:
                    state['records'][path]['stamp'] = tuple(result['stamp'])
                    if kind == 'preview':
                        self.preview_ready.emit(side, result)
                    else:
                        state['batch'].append(result)
                        if not self.flush_timer.isActive():
                            self.flush_timer.start()
                        self.write_count += 1
                        if self.write_count % 128 == 0:
                            self.submit({'kind': 'trim'}, self.cache.trim, priority=-10)
        self.pump()

    def flush(self):
        for side, state in self.states.items():
            rank = {path: index for index, path in enumerate(state['priority'])}
            state['batch'].sort(key=lambda result: rank.get(result['path'], len(rank)))
            batch, state['batch'] = state['batch'][:8], state['batch'][8:]
            if batch:
                self.thumbnails_ready.emit(side, batch)
        self.pump()
        if any(state['batch'] for state in self.states.values()):
            self.flush_timer.start()

    def stop(self):
        self.stopped = True
        self.flush_timer.stop()
        for state in self.states.values():
            state['cancel'].set()
            if state['preview_cancel'] is not None:
                state['preview_cancel'].set()
        self.pool.clear()

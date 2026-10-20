"""Real local IPC, process races and recovery; all files are temporary."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication, QWidget
from services.single_instance import SingleInstance, instance_key


WORKER = r'''
import json,os,sys
from pathlib import Path
from PySide6.QtCore import QCoreApplication,QTimer
from services.single_instance import SingleInstance
app=QCoreApplication([])
settings=Path(sys.argv[1])
guard=SingleInstance(settings)
primary=guard.start()
if sys.argv[2]=='crash':
    print(json.dumps({'primary':primary}),flush=True)
    os._exit(0)
if primary:
    def activated():
        with settings.with_suffix('.activations').open('a',encoding='utf-8') as output:
            output.write('activated\n')
    guard.activated.connect(activated)
print(json.dumps({'primary':primary}),flush=True)
if primary:
    QTimer.singleShot(1800,app.quit)
    app.exec()
guard.close()
'''


class SingleInstanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='jhnode-instance-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / 'settings.json'
        self.guards = []

    def tearDown(self):
        for guard in reversed(self.guards):
            guard.close()
        self.app.processEvents()

    def guard(self, path=None):
        guard = SingleInstance(path or self.path)
        self.guards.append(guard)
        return guard

    def pump_until(self, predicate):
        deadline = time.monotonic() + 2
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
            time.sleep(0.005)
        self.assertTrue(predicate())

    def child(self, mode='normal'):
        env = os.environ.copy()
        for key, name in (('LOCALAPPDATA', 'appdata'), ('APPDATA', 'roaming'),
                          ('TEMP', 'temp'), ('TMP', 'temp')):
            folder = self.root / name
            folder.mkdir(exist_ok=True)
            env[key] = str(folder)
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        return subprocess.Popen([sys.executable, '-B', '-c', WORKER, str(self.path), mode],
                                cwd=Path(__file__).resolve().parents[1], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def notify_from_another_process(self):
        process = self.child()
        try:
            # Windows accepts the pipe connection on the owner's Qt event loop.
            self.pump_until(lambda: process.poll() is not None)
            stdout, stderr = process.communicate(timeout=3)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertFalse(json.loads(stdout.strip())['primary'])
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    def test_different_settings_locations_can_each_own_a_window(self):
        first = self.guard()
        other = self.guard(self.root / 'other-settings.json')
        self.assertNotEqual(instance_key(self.path), instance_key(self.root / 'other-settings.json'))
        self.assertTrue(first.start())
        self.assertTrue(other.start())

    def test_duplicate_launch_restores_existing_window_and_secondary_cannot_close_owner(self):
        primary = self.guard()
        self.assertTrue(primary.start())
        window = QWidget()
        self.addCleanup(window.close)
        primary.set_window(window)
        window.showMinimized()
        self.app.processEvents()
        activations = []
        primary.activated.connect(lambda: activations.append(True))
        with patch.object(window, 'raise_', wraps=window.raise_) as raised, \
             patch.object(window, 'activateWindow', wraps=window.activateWindow) as activated:
            self.notify_from_another_process()
            self.pump_until(lambda: len(activations) == 1)
            self.assertFalse(window.isMinimized())
            self.assertTrue(window.isVisible())
            self.assertEqual(raised.call_count, 1)
            self.assertEqual(activated.call_count, 1)
            self.notify_from_another_process()
            self.pump_until(lambda: len(activations) == 2)
            self.assertTrue(primary.server.isListening())

    def test_activation_received_before_window_creation_is_retained(self):
        primary = self.guard()
        self.assertTrue(primary.start())
        self.notify_from_another_process()
        self.pump_until(lambda: primary.pending_activation)
        window = QWidget()
        self.addCleanup(window.close)
        primary.set_window(window)
        self.assertTrue(window.isVisible())
        self.assertFalse(primary.pending_activation)

    def test_simultaneous_processes_create_one_owner_and_notify_it(self):
        processes = [self.child() for _ in range(4)]
        try:
            results = []
            for process in processes:
                stdout, stderr = process.communicate(timeout=12)
                self.assertEqual(process.returncode, 0, stderr)
                results.append(json.loads(stdout.strip()))
            self.assertEqual(sum(value['primary'] for value in results), 1, results)
            self.assertEqual(self.path.with_suffix('.activations').read_text(encoding='utf-8').splitlines(),
                             ['activated'] * 3)
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate()

    def test_crashed_owner_lock_and_endpoint_are_reclaimed(self):
        process = self.child('crash')
        stdout, stderr = process.communicate(timeout=8)
        self.assertEqual(process.returncode, 0, stderr)
        self.assertTrue(json.loads(stdout.strip())['primary'])
        replacement = self.guard()
        self.assertTrue(replacement.start())
        self.assertTrue(replacement.server.isListening())


if __name__ == '__main__':
    unittest.main()

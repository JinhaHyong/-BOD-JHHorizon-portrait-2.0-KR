"""One application per user/settings path, with a local activation channel."""

import getpass
import hashlib
import os
from pathlib import Path
import time

from PySide6.QtCore import QLockFile, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstanceError(OSError):
    pass


def instance_key(settings_path):
    location = os.path.normcase(str(Path(settings_path).expanduser().resolve()))
    user = os.path.normcase(str(Path.home())) + '\0' + getpass.getuser()
    return 'JHnode-' + hashlib.sha256((user + '\0' + location).encode('utf-8')).hexdigest()[:32]


class SingleInstance(QObject):
    activated = Signal()

    def __init__(self, settings_path, parent=None):
        super().__init__(parent)
        path = Path(settings_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.name = instance_key(path)
        self.lock = QLockFile(str(path.parent / ('.' + self.name + '.lock')))
        # A running application must never lose ownership because of its age.
        self.lock.setStaleLockTime(0)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._connections_ready)
        self.primary = False
        self.window = None
        self.pending_activation = False

    def start(self, timeout_ms=3000):
        """True owns the window; False has notified the existing owner."""
        if self.primary:
            return True
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            if self.lock.tryLock(0):
                # Only the lock owner may reclaim an abandoned endpoint. Other
                # simultaneous starters cannot remove a newly created server.
                QLocalServer.removeServer(self.name)
                if not self.server.listen(self.name):
                    message = self.server.errorString()
                    self.lock.unlock()
                    raise SingleInstanceError(message)
                self.primary = True
                return True
            if self.lock.error() == QLockFile.LockError.PermissionError:
                raise SingleInstanceError('Cannot access the application lock.')
            if self._notify_owner():
                return False
            if time.monotonic() >= deadline:
                raise SingleInstanceError('The existing application is not responding. Please close it and try again.')
            time.sleep(0.04)

    def _notify_owner(self):
        socket = QLocalSocket()
        try:
            socket.connectToServer(self.name)
            if not socket.waitForConnected(150):
                return False
            message = b'activate\n'
            if socket.write(message) != len(message):
                return False
            socket.flush()
            return socket.bytesToWrite() == 0 or socket.waitForBytesWritten(150)
        finally:
            socket.disconnectFromServer()
            socket.close()

    def _connections_ready(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.setProperty('activation_data', b'')
            socket.readyRead.connect(lambda connection=socket: self._read_request(connection))
            socket.disconnected.connect(socket.deleteLater)
            self._read_request(socket)

    def _read_request(self, socket):
        data = bytes(socket.property('activation_data') or b'') + bytes(socket.readAll())
        if b'\n' not in data and len(data) < 64:
            socket.setProperty('activation_data', data)
            return
        if data.split(b'\n', 1)[0] == b'activate':
            self.pending_activation = True
            self.activated.emit()
            self._show_window()
        socket.disconnectFromServer()

    def set_window(self, window):
        self.window = window
        if self.pending_activation:
            self._show_window()

    def _show_window(self):
        if self.window is None:
            return
        if self.window.isMinimized():
            self.window.showNormal()
        else:
            self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        self.pending_activation = False

    def close(self):
        if self.primary:
            self.server.close()
            self.lock.unlock()
            self.primary = False

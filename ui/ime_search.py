"""Search the visible text, including an unfinished Korean IME composition."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLineEdit


class ImeSearchLineEdit(QLineEdit):
    query_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._preedit = ''
        self._preedit_position = 0
        self._handling_ime = False
        self._last_query = ''
        self.textChanged.connect(self._committed_changed)

    def search_text(self):
        text = self.text()
        if not self._preedit:
            return text
        # Qt cursor positions count UTF-16 units, including in emoji/file names.
        encoded = text.encode('utf-16-le', errors='surrogatepass')
        offset = max(0, min(len(encoded), self._preedit_position * 2))
        composition = self._preedit.encode('utf-16-le', errors='surrogatepass')
        return (encoded[:offset] + composition + encoded[offset:]).decode(
            'utf-16-le', errors='surrogatepass')

    def _publish_query(self):
        query = self.search_text()
        if query != self._last_query:
            self._last_query = query
            self.query_changed.emit(query)

    def _committed_changed(self, _text):
        if not self._handling_ime:
            self._preedit = ''
            self._publish_query()

    def inputMethodEvent(self, event):
        # Let Qt apply commits/replacements and keep its native composition UI.
        # Publish once afterwards, so a commit+preedit event cannot search stale text.
        self._handling_ime = True
        try:
            super().inputMethodEvent(event)
        finally:
            self._handling_ime = False
        self._preedit = event.preeditString()
        self._preedit_position = self.cursorPosition()
        self._publish_query()

    def setText(self, text):
        self._preedit = ''
        super().setText(text)
        self._publish_query()

    def clear(self):
        self._preedit = ''
        super().clear()
        self._publish_query()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if self._preedit:
            self._preedit = ''
            self._publish_query()

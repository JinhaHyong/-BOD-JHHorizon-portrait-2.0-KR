"""Shared message dialog using the original colors and button layout."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ui.styles import DIALOG_STYLE


def show_message(parent, translations, message: str, kind: str = "info"):
    dialog = QDialog(parent)
    dialog.setWindowTitle(translations.text("dialog", kind))
    dialog.setMinimumSize(300, 150)
    dialog.setStyleSheet(DIALOG_STYLE)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(20, 20, 20, 20)
    label = QLabel(str(message))
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(label)
    buttons = QHBoxLayout()
    ok = QPushButton(translations.text("dialog", "ok_btn"))
    ok.setFixedWidth(100)
    ok.clicked.connect(dialog.accept)
    buttons.addWidget(ok, alignment=Qt.AlignmentFlag.AlignCenter)
    layout.addLayout(buttons)
    dialog.exec()

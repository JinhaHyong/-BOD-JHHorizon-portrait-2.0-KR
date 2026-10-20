"""Palette-colored font shortcut icon drawn with Qt."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap


def font_icon(color):
    pixmap = QPixmap(48, 48)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        font = QFont('Segoe UI')
        font.setPixelSize(16)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(QRectF(0, 0, 24, 24), Qt.AlignmentFlag.AlignCenter, 'Aa')
    finally:
        painter.end()
    return QIcon(pixmap)

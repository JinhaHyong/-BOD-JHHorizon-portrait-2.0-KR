"""Shared theme state and vector sun/moon icons for the portrait footer."""

import math

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication

from ui.styles import apply_theme


class ThemeManager(QObject):
    changed = Signal(str)

    def __init__(self, app, mode='light'):
        super().__init__(app)
        self.app = app
        self.mode = 'dark' if mode == 'dark' else 'light'
        apply_theme(app, self.mode)

    def set_mode(self, mode):
        mode = 'dark' if mode == 'dark' else 'light'
        if mode == self.mode:
            return
        self.mode = mode
        apply_theme(self.app, mode)
        # Refresh palette-based styles already installed on open widgets.
        for widget in self.app.allWidgets():
            widget.setPalette(self.app.palette())
            sheet = widget.styleSheet()
            if sheet:
                widget.setStyleSheet(sheet)
            widget.update()
        self.changed.emit(mode)


def install_theme(app, settings):
    manager = getattr(app, '_portrait_theme', None)
    if manager is None:
        manager = ThemeManager(app, settings.get('theme_mode', 'light'))
        app._portrait_theme = manager
    return manager


def theme_manager(settings):
    return install_theme(QApplication.instance(), settings)


def mode_icon(mode):
    pixmap = QPixmap(48, 48)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if mode == 'dark':
            outer, cutout = QPainterPath(), QPainterPath()
            outer.addEllipse(QRectF(3, 3, 18, 18))
            cutout.addEllipse(QRectF(9, 0, 17, 17))
            painter.fillPath(outer.subtracted(cutout), QColor('#f4d06f'))
        else:
            color = QColor('#d78a00')
            pen = QPen(color, 1.7)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            for index in range(8):
                angle = math.pi * index / 4
                painter.drawLine(QPointF(12 + 7 * math.cos(angle), 12 + 7 * math.sin(angle)),
                                 QPointF(12 + 10 * math.cos(angle), 12 + 10 * math.sin(angle)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QRectF(7.5, 7.5, 9, 9))
    finally:
        painter.end()
    return QIcon(pixmap)

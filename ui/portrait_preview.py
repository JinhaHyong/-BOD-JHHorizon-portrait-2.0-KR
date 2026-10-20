"""Portrait preview with a selection-only pencil button inside the photo."""

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QToolButton


def pencil_icon():
    pixmap = QPixmap(48, 48)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor('white'), 1.7)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        path = QPainterPath()
        path.moveTo(4, 16)
        path.lineTo(15, 5)
        path.lineTo(19, 9)
        path.lineTo(8, 20)
        path.lineTo(3, 21)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawLine(QPointF(13, 7), QPointF(17, 11))
    finally:
        painter.end()
    return QIcon(pixmap)


class EditablePreviewLabel(QLabel):
    double_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.photo_bounds = None
        self.edit_button = QToolButton(self)
        self.edit_button.setFixedSize(32, 32)
        self.edit_button.setIconSize(QSize(21, 21))
        self.edit_button.setIcon(pencil_icon())
        self.edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_button.setStyleSheet('''
            QToolButton {
                background-color: rgba(20, 27, 38, 210);
                border: 1px solid rgba(255, 255, 255, 90);
                border-radius: 7px;
                padding: 3px;
            }
            QToolButton:hover { background-color: rgba(30, 61, 89, 245); border-color: white; }
            QToolButton:pressed { background-color: rgba(42, 94, 150, 250); }
            QToolButton:focus { border-color: white; }
        ''')
        self.edit_button.setEnabled(False)
        self.edit_button.hide()

    def set_preview(self, pixmap, source_bounds, source_size):
        super().setPixmap(pixmap)
        self.photo_bounds = None
        if pixmap.isNull() or source_bounds is None:
            self.edit_button.hide()
            self.edit_button.setEnabled(False)
            return
        # The square preview includes transparent padding; anchor to the photo itself.
        ratio = pixmap.devicePixelRatio()
        width, height = pixmap.width() / ratio, pixmap.height() / ratio
        left, top, right, bottom = source_bounds
        self.photo_bounds = QRectF(left * width / source_size[0], top * height / source_size[1],
                                  (right - left) * width / source_size[0],
                                  (bottom - top) * height / source_size[1])
        self.position_edit_button()
        self.edit_button.setEnabled(True)
        self.edit_button.show()
        self.edit_button.raise_()

    def clear(self):
        self.photo_bounds = None
        self.edit_button.hide()
        self.edit_button.setEnabled(False)
        super().clear()

    def position_edit_button(self):
        if self.photo_bounds is None:
            return
        pixmap = self.pixmap()
        if pixmap is None or pixmap.isNull():
            return
        ratio = pixmap.devicePixelRatio()
        bounds = self.photo_bounds.translated(
            (self.width() - pixmap.width() / ratio) / 2,
            (self.height() - pixmap.height() / ratio) / 2)
        x = bounds.right() - self.edit_button.width() - 6
        y = bounds.top() + 6
        self.edit_button.move(round(max(0, min(self.width() - self.edit_button.width(), x))),
                              round(max(0, min(self.height() - self.edit_button.height(), y))))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.position_edit_button()

    def mouseDoubleClickEvent(self, event):
        if self.photo_bounds is not None and event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)

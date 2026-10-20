"""Native single-line local font previews in four color combinations."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPalette, QPen
from PySide6.QtWidgets import QWidget

PREVIEW_COLORS = (('#ffffff', '#172033'), ('#172033', '#ffffff'),
                  ('#172033', '#e7c46a'), ('#172033', '#67d8ef'))


class LocalFontPreview(QWidget):
    def __init__(self, parent=None, language='kr'):
        super().__init__(parent)
        self.language = language
        self.preview_font = None
        self._text = ''
        self.setMinimumSize(0, 240)

    def text(self):
        return self._text

    def set_preview(self, text, font):
        self._text = text
        self.preview_font = QFont(font) if font is not None else None
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        bounds = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        english = self.language != 'kr'
        if self.preview_font is None:
            painter.setPen(self.palette().color(QPalette.ColorRole.PlaceholderText))
            painter.drawText(bounds.adjusted(12, 12, -12, -12),
                             Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                             'Select a font on the left.' if english else '왼쪽에서 폰트를 선택해 주세요.')
            return
        gap = 10
        width, height = (bounds.width() - gap) / 2, (bounds.height() - gap) / 2
        labels = (('Light', 'Dark', 'Gold', 'Cyan') if english
                  else ('밝은 배경', '어두운 배경', '금색', '하늘색'))
        for index, (background, foreground) in enumerate(PREVIEW_COLORS):
            rect = QRectF(bounds.left() + index % 2 * (width + gap),
                          bounds.top() + index // 2 * (height + gap), width, height)
            painter.setPen(QPen(QColor('#d5deeb'), 1))
            painter.setBrush(QColor(background))
            painter.drawRoundedRect(rect, 10, 10)
            painter.setFont(self.font())
            painter.setPen(QColor('#64748b' if index == 0 else '#a5b4c8'))
            painter.drawText(rect.adjusted(12, 8, -12, -8),
                             Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft, labels[index])
            area = rect.adjusted(12, 32, -12, -12)
            font = QFont(self.preview_font)
            font.setPixelSize(30)
            metrics = QFontMetricsF(font)
            scale = min(1.0, max(1, area.width()) / max(1, metrics.horizontalAdvance(self._text)),
                        max(1, area.height()) / max(1, metrics.height()))
            font.setPixelSize(max(1, int(30 * scale)))
            painter.setFont(font)
            painter.setPen(QColor(foreground))
            painter.save()
            painter.setClipRect(area)
            painter.drawText(area, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextSingleLine, self._text)
            painter.restore()

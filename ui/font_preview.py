"""Native preview cards painted from bundled or user-generated text images."""

from collections import OrderedDict

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPalette, QPen
from PySide6.QtWidgets import QWidget

from core.font_previews import preview_image_path, preview_record


class FontPreview(QWidget):
    COLORS = (('#ffffff', '#111827'), ('#192333', '#ffffff'),
              ('#192333', '#f3c66b'), ('#192333', '#67e8f9'))

    def __init__(self, parent=None, language='kr'):
        super().__init__(parent)
        self.language = language
        self.repo = None
        self.url = None
        self.record = None
        self.images = []
        self.examples = []
        self.cache = OrderedDict()

    def colored_images(self, filename):
        if filename in self.cache:
            self.cache.move_to_end(filename)
            return self.cache[filename]
        path = preview_image_path(filename)
        source = QImage(str(path)) if path is not None else QImage()
        if source.isNull():
            return []
        images = []
        for _background, color in self.COLORS:
            tinted = source.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
            painter = QPainter(tinted)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(tinted.rect(), QColor(color))
            painter.end()
            images.append(tinted)
        self.cache[filename] = images
        # Keep only nearby previews in memory; originals remain bundled PNGs.
        while len(self.cache) > 16:
            self.cache.popitem(last=False)
        return images

    def show_font(self, repo, url=None):
        self.repo, self.url = repo, url
        self.record = preview_record(repo, url) if repo else None
        self.images = self.colored_images(self.record['image']) if self.record else []
        example = self.record.get('example_image') if self.record else None
        self.examples = self.colored_images(example) if example else []
        self.setToolTip('')
        self.update()

    @staticmethod
    def draw_image(painter, image, area, max_scale):
        scale = min(max_scale, area.width() / image.width(), area.height() / image.height())
        width, height = image.width() * scale, image.height() * scale
        target = QRectF(area.center().x() - width / 2, area.center().y() - height / 2,
                        width, height)
        painter.drawImage(target, image)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        english = self.language != 'kr'
        bounds = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if not self.images:
            painter.setPen(self.palette().color(QPalette.ColorRole.PlaceholderText))
            text = ('Select a font on the left.' if english else '왼쪽에서 폰트를 선택해 주세요.')
            if self.repo:
                text = ('No preview image for this font yet.' if english
                        else '이 폰트의 미리보기 이미지는 아직 준비되지 않았습니다.')
            painter.drawText(bounds.adjusted(12, 12, -12, -12),
                             Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)
            return
        missing = self.record.get('missing', '')
        note_height = 36 if missing else 0
        cards = bounds.adjusted(0, 0, 0, -note_height)
        gap = 10
        width = (cards.width() - gap) / 2
        height = (cards.height() - gap) / 2
        labels = (('Light', 'Dark', 'Gold', 'Cyan') if english
                  else ('밝은 배경', '어두운 배경', '금색', '하늘색'))
        for index, ((background, _color), image) in enumerate(zip(self.COLORS, self.images)):
            rect = QRectF(cards.left() + (index % 2) * (width + gap),
                          cards.top() + (index // 2) * (height + gap), width, height)
            painter.setPen(QPen(QColor('#d5deeb'), 1))
            painter.setBrush(QColor(background))
            painter.drawRoundedRect(rect, 10, 10)
            painter.setPen(QColor('#64748b' if index == 0 else '#a5b4c8'))
            painter.drawText(rect.adjusted(12, 8, -12, -8),
                             Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft, labels[index])
            area = rect.adjusted(12, 32, -12, -12)
            if self.examples:
                main_area = QRectF(area.left(), area.top(), area.width(), area.height() * .55)
                example_area = QRectF(area.left(), main_area.bottom(), area.width(), area.height() * .45)
                self.draw_image(painter, image, main_area, 30 / self.record.get('font_size', 96))
                self.draw_image(painter, self.examples[index], example_area, 24 / 96)
            else:
                self.draw_image(painter, image, area, 30 / self.record.get('font_size', 96))
        if missing:
            painter.setPen(self.palette().color(QPalette.ColorRole.PlaceholderText))
            note = ('Unsupported characters use a fallback font.' if english
                    else '지원하지 않는 글자는 기본 글꼴로 표시합니다.')
            painter.drawText(QRectF(bounds.left(), cards.bottom() + 6, bounds.width(), note_height - 6),
                             Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, note)

    def reload(self):
        self.cache.clear()
        self.show_font(self.repo, self.url)

    def release(self):
        self.images = []
        self.examples = []
        self.cache.clear()

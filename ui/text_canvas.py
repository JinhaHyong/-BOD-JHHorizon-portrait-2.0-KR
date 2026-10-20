"""Shared text drawing for the draggable preview and full-resolution output."""

from copy import deepcopy
from io import BytesIO

from PIL import Image
from PySide6.QtCore import QByteArray, QBuffer, QEvent, QIODevice, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QAbstractTextDocumentLayout, QColor, QGuiApplication, QImage, QPainter, QPalette,
    QPen, QPixmap, QTextCharFormat, QTextCursor, QTextDocument, QTextOption,
)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject, QGraphicsScene, QGraphicsTextItem, QGraphicsView

from core.portrait_edit import TextOverlay
from ui.font_registry import layer_font


def text_document(layer: TextOverlay) -> QTextDocument:
    document = QTextDocument()
    document.setDefaultFont(layer_font(layer))
    document.setDocumentMargin(0)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    option.setAlignment({"left": Qt.AlignmentFlag.AlignLeft,
                         "center": Qt.AlignmentFlag.AlignHCenter,
                         "right": Qt.AlignmentFlag.AlignRight}[layer.alignment])
    document.setDefaultTextOption(option)
    document.setPlainText(layer.text or " ")
    document.setTextWidth(max(1, layer.width - 2 * layer.padding))
    return document


def box_height(layer: TextOverlay, document: QTextDocument) -> float:
    return layer.height if layer.height is not None else document.size().height() + 2 * layer.padding


def draw_text_document(painter: QPainter, document: QTextDocument,
                       color: QColor, layer: TextOverlay):
    painted_document = document
    if layer.intense:
        # Thicken the actual glyphs even for fonts that have no heavier face.
        # Work on a copy so the cached layout remains plain text for both passes.
        painted_document = document.clone()
        cursor = QTextCursor(painted_document)
        cursor.select(QTextCursor.SelectionType.Document)
        character_format = QTextCharFormat()
        character_format.setForeground(color)
        outline = QPen(color)
        outline.setWidthF(max(.6, layer.font_size * .045))
        outline.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        character_format.setTextOutline(outline)
        cursor.mergeCharFormat(character_format)
    context = QAbstractTextDocumentLayout.PaintContext()
    context.palette.setColor(QPalette.ColorRole.Text, color)
    painted_document.documentLayout().draw(painter, context)


def draw_text_box(painter: QPainter, layer: TextOverlay, document: QTextDocument, render_text=True):
    height = box_height(layer, document)
    painter.save()
    painter.setClipRect(QRectF(0, 0, layer.width, height))
    background = QColor(layer.background_color)
    background.setAlphaF(layer.background_opacity / 100)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(background)
    painter.drawRoundedRect(QRectF(0, 0, layer.width, height), layer.radius, layer.radius)
    if not render_text:
        painter.restore()
        return
    # Keep the full text block centered even when it is taller than the box.
    # A negative offset deliberately clips equal overflow above and below.
    painter.translate(layer.padding, (height - document.size().height()) / 2)
    if layer.shadow:
        painter.save()
        offset = max(1, layer.font_size / 16)
        painter.translate(offset, offset)
        shadow_color = QColor("#000000")
        shadow_color.setAlphaF(.65 * layer.text_opacity / 100)
        draw_text_document(painter, document, shadow_color, layer)
        painter.restore()
    color = QColor(layer.text_color)
    color.setAlphaF(layer.text_opacity / 100)
    draw_text_document(painter, document, color, layer)
    painter.restore()


def render_portrait(base: QImage, layers: list[TextOverlay]) -> QImage:
    result = base.convertToFormat(QImage.Format.Format_RGB32).copy()
    painter = QPainter(result)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        for layer in layers:
            if not layer.text and not layer.background_opacity:
                continue
            painter.save()
            painter.translate(layer.x, layer.y)
            # Empty contents still have a configured box background.
            draw_text_box(painter, layer, text_document(layer), render_text=bool(layer.text))
            painter.restore()
    finally:
        painter.end()
    return result


def to_pillow(image: QImage) -> Image.Image:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise ValueError("Could not render portrait")
    buffer.close()
    with Image.open(BytesIO(bytes(data))) as source:
        return source.convert("RGB")


class InlineTextItem(QGraphicsTextItem):
    """Native text input on the image, including Korean input and selection."""

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.document().contentsChanged.connect(owner.sync_inline_text)
        self.hide()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.owner.finish_inline_edit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.owner.finish_inline_edit(commit=False)
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and (
                event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.owner.finish_inline_edit()
            event.accept()
            return
        super().keyPressEvent(event)


class TextBoxItem(QGraphicsObject):
    moved = Signal(str, float, float)
    resized = Signal(str)
    guides_clear_requested = Signal()
    text_changed = Signal(str, str)

    def __init__(self, layer: TextOverlay, image_size, parent=None):
        super().__init__(parent)
        self.layer = deepcopy(layer)
        self.image_size = image_size
        self.document = text_document(self.layer)
        self._resize_handle = None
        self._resize_start = None
        self._resize_origin = None
        self._dragging = False
        self._shift_snap = False
        self.snapper = None
        self.inline_editor = None
        self.editing = False
        self._original_text = ""
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                      QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges |
                      QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setAcceptHoverEvents(True)
        self.setPos(layer.x, layer.y)

    def boundingRect(self):
        return QRectF(0, 0, self.layer.width,
                      box_height(self.layer, self.document))

    def paint(self, painter, _option, _widget=None):
        draw_text_box(painter, self.layer, self.document, render_text=not self.editing)
        if self.isSelected() and not self.editing:
            pen = QPen(QColor("#1689ff"), 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect().adjusted(.5, .5, -.5, -.5))
            painter.setPen(QPen(QColor("#1689ff"), 0))
            painter.setBrush(QColor("white"))
            for rectangle in self.handle_rectangles().values():
                painter.drawRect(rectangle)

    def handle_rectangles(self):
        # Keep grips about eight screen pixels wide as the photo is scaled.
        views = self.scene().views() if self.scene() else []
        scale = abs(views[0].transform().m11()) if views else 1
        size = min(8 / max(scale, .01), self.boundingRect().width(), self.boundingRect().height())
        bounds = self.boundingRect()
        left, right = size / 2, bounds.width() - size / 2
        top, bottom = size / 2, bounds.height() - size / 2
        middle_x, middle_y = bounds.width() / 2, bounds.height() / 2
        return {name: QRectF(x - size / 2, y - size / 2, size, size)
                for name, x, y in (("tl", left, top), ("t", middle_x, top),
                                   ("tr", right, top), ("r", right, middle_y),
                                   ("br", right, bottom), ("b", middle_x, bottom),
                                   ("bl", left, bottom), ("l", left, middle_y))}

    def handle_at(self, position):
        if self.isSelected() and not self.editing:
            for name, rectangle in self.handle_rectangles().items():
                if rectangle.contains(position):
                    return name
        return None

    @staticmethod
    def handle_cursor(handle):
        if handle in ("tl", "br"):
            return Qt.CursorShape.SizeFDiagCursor
        if handle in ("tr", "bl"):
            return Qt.CursorShape.SizeBDiagCursor
        if handle in ("l", "r"):
            return Qt.CursorShape.SizeHorCursor
        if handle in ("t", "b"):
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.SizeAllCursor

    def hoverMoveEvent(self, event):
        self.setCursor(self.handle_cursor(self.handle_at(event.pos())))
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        self.guides_clear_requested.emit()
        handle = self.handle_at(event.pos())
        if event.button() == Qt.MouseButton.LeftButton and handle:
            self._resize_handle = handle
            self._resize_start = event.scenePos()
            self._resize_origin = self.boundingRect().translated(self.pos())
            self.setCursor(self.handle_cursor(handle))
            event.accept()
            return
        self._dragging = event.button() == Qt.MouseButton.LeftButton
        self._shift_snap = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.begin_inline_edit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def begin_inline_edit(self):
        if self.editing:
            return
        self._dragging = self._shift_snap = False
        self._resize_handle = self._resize_start = self._resize_origin = None
        self.guides_clear_requested.emit()
        self.scene().clearSelection()
        self.setSelected(True)
        self._original_text = self.layer.text
        if self.inline_editor is None:
            self.inline_editor = InlineTextItem(self)
        editor = self.inline_editor
        document = editor.document()
        document.setDefaultFont(self.document.defaultFont())
        document.setDocumentMargin(0)
        document.setDefaultTextOption(self.document.defaultTextOption())
        editor.setTextWidth(max(1, self.layer.width - 2 * self.layer.padding))
        editor.setPlainText(self.layer.text)
        color = QColor(self.layer.text_color)
        color.setAlphaF(self.layer.text_opacity / 100)
        editor.setDefaultTextColor(color)
        self.editing = True
        self.position_inline_editor()
        editor.show()
        editor.setFocus(Qt.FocusReason.MouseFocusReason)
        cursor = editor.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        editor.setTextCursor(cursor)
        self.update()

    def position_inline_editor(self):
        if self.inline_editor is not None:
            self.inline_editor.setPos(
                self.layer.padding,
                (self.boundingRect().height() - self.inline_editor.document().size().height()) / 2)

    def sync_inline_text(self):
        if not self.editing:
            return
        self.apply_inline_text(self.inline_editor.toPlainText())

    def apply_inline_text(self, text):
        self.prepareGeometryChange()
        self.layer.text = text
        self.document = text_document(self.layer)
        self.setPos(self.clamp_position(self.pos()))
        self.position_inline_editor()
        self.update()
        self.text_changed.emit(self.layer.id, text)

    def finish_inline_edit(self, commit=True):
        if not self.editing:
            return
        if commit and self.inline_editor.hasFocus():
            QGuiApplication.inputMethod().commit()
        text = self.inline_editor.toPlainText() if commit else self._original_text
        self.editing = False
        self.inline_editor.hide()
        self.inline_editor.clearFocus()
        self.apply_inline_text(text)
        self.update()

    def mouseMoveEvent(self, event):
        if self._resize_handle is None:
            self._shift_snap = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            if not self._shift_snap:
                self.guides_clear_requested.emit()
            super().mouseMoveEvent(event)
            return
        delta = event.scenePos() - self._resize_start
        rect = QRectF(self._resize_origin)
        minimum_width = min(32, self.image_size.width())
        minimum_height = min(24, self.image_size.height())
        handle = self._resize_handle
        if "l" in handle:
            rect.setLeft(max(0, min(rect.right() - minimum_width, rect.left() + delta.x())))
        if "r" in handle:
            rect.setRight(min(self.image_size.width(), max(rect.left() + minimum_width, rect.right() + delta.x())))
        if "t" in handle:
            rect.setTop(max(0, min(rect.bottom() - minimum_height, rect.top() + delta.y())))
        if "b" in handle:
            rect.setBottom(min(self.image_size.height(), max(rect.top() + minimum_height, rect.bottom() + delta.y())))
        layer = deepcopy(self.layer)
        layer.x, layer.y = rect.left(), rect.top()
        layer.width, layer.height = round(rect.width()), rect.height()
        self.update_layer(layer)
        self.resized.emit(layer.id)
        event.accept()

    def mouseReleaseEvent(self, event):
        self._dragging = False
        self._shift_snap = False
        self.guides_clear_requested.emit()
        if self._resize_handle is not None:
            self._resize_handle = self._resize_start = self._resize_origin = None
            self.setCursor(self.handle_cursor(self.handle_at(event.pos())))
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def update_layer(self, layer):
        self.finish_inline_edit()
        self.prepareGeometryChange()
        self.layer = deepcopy(layer)
        self.document = text_document(self.layer)
        self.setPos(self.layer.x, self.layer.y)
        # Changing size can move the right/bottom edge outside the image.
        self.setPos(self.clamp_position(self.pos()))
        self.update()

    def clamp_position(self, point):
        bounds = self.boundingRect()
        return QPointF(max(0, min(point.x(), self.image_size.width() - bounds.width())),
                       max(0, min(point.y(), self.image_size.height() - bounds.height())))

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            point = self.clamp_position(value)
            if self._dragging and self._shift_snap and self.snapper is not None:
                point = self.snapper(self, point)
            return self.clamp_position(point)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.layer.x, self.layer.y = self.pos().x(), self.pos().y()
            self.moved.emit(self.layer.id, self.layer.x, self.layer.y)
        return super().itemChange(change, value)


class TextCanvas(QGraphicsView):
    selected = Signal(str)
    moved = Signal(str, float, float)
    resized = Signal(str)
    text_changed = Signal(str, str)

    def __init__(self, base: QImage, layers: list[TextOverlay], parent=None):
        super().__init__(parent)
        self.base = base.copy()
        self.items_by_id = {}
        self.snap_guides = []
        self._disposed = False
        scene = QGraphicsScene(self)
        self.setScene(scene)
        scene.setSceneRect(QRectF(0, 0, base.width(), base.height()))
        self.background_item = scene.addPixmap(QPixmap.fromImage(base))
        self.background_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape)
        self.setBackgroundBrush(self.palette().brush(QPalette.ColorRole.AlternateBase))
        self.setRenderHints(QPainter.RenderHint.Antialiasing |
                            QPainter.RenderHint.TextAntialiasing |
                            QPainter.RenderHint.SmoothPixmapTransform)
        self.setMinimumSize(300, 300)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for layer in layers:
            self.add_layer(layer)
        scene.selectionChanged.connect(self.on_selection_changed)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.PaletteChange, QEvent.Type.ApplicationPaletteChange):
            self.setBackgroundBrush(self.palette().brush(QPalette.ColorRole.AlternateBase))

    def add_layer(self, layer):
        item = TextBoxItem(layer, self.base.size(), self.background_item)
        item.setZValue(len(self.items_by_id) + 1)
        item.moved.connect(self.moved)
        item.resized.connect(self.resized)
        item.guides_clear_requested.connect(self.clear_guides)
        item.text_changed.connect(self.text_changed)
        item.snapper = self.snap_position
        self.items_by_id[layer.id] = item
        return item

    def remove_layer(self, layer_id):
        self.clear_guides()
        item = self.items_by_id.pop(layer_id)
        item.finish_inline_edit()
        item.snapper = None
        self.scene().removeItem(item)
        item.deleteLater()
        # Keep visual order identical to the order used by the output renderer.
        for index, remaining in enumerate(self.items_by_id.values()):
            remaining.setZValue(index + 1)

    def select_layer(self, layer_id):
        self.scene().clearSelection()
        if layer_id in self.items_by_id:
            self.items_by_id[layer_id].setSelected(True)

    def on_selection_changed(self):
        items = [item for item in self.scene().selectedItems() if isinstance(item, TextBoxItem)]
        self.selected.emit(items[0].layer.id if items else "")

    @staticmethod
    def snap_axis(position, size, extent, targets, tolerance):
        best = None
        # Center-to-center wins equal-distance ties for balanced placement.
        for offset in (size / 2, 0, size):
            for target in targets:
                candidate = target - offset
                if candidate < -1e-6 or candidate + size > extent + 1e-6:
                    continue
                distance = abs(candidate - position)
                if distance <= tolerance and (best is None or distance < best[0]):
                    best = distance, candidate, target
        return (best[1], best[2]) if best else (position, None)

    def snap_position(self, moving, position):
        self.clear_guides()
        scale = max(abs(self.transform().m11()), .01)
        tolerance = 8 / scale
        horizontal_targets, vertical_targets = [], []
        for other in self.items_by_id.values():
            if other is moving:
                continue
            bounds = other.boundingRect().translated(other.pos())
            horizontal_targets.extend((bounds.center().x(), bounds.left(), bounds.right()))
            vertical_targets.extend((bounds.center().y(), bounds.top(), bounds.bottom()))
        # The photo itself is also a useful alignment reference.
        horizontal_targets.extend((self.base.width() / 2, 0, self.base.width()))
        vertical_targets.extend((self.base.height() / 2, 0, self.base.height()))
        bounds = moving.boundingRect()
        x, guide_x = self.snap_axis(position.x(), bounds.width(), self.base.width(),
                                    horizontal_targets, tolerance)
        y, guide_y = self.snap_axis(position.y(), bounds.height(), self.base.height(),
                                    vertical_targets, tolerance)
        pen = QPen(QColor("#e649b6"), 1, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        lines = []
        if guide_x is not None:
            lines.append((guide_x, 0, guide_x, self.base.height()))
        if guide_y is not None:
            lines.append((0, guide_y, self.base.width(), guide_y))
        for coordinates in lines:
            guide = self.scene().addLine(*coordinates, pen)
            guide.setZValue(1_000_000)
            guide.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.snap_guides.append(guide)
        return QPointF(x, y)

    def clear_guides(self):
        for guide in self.snap_guides:
            self.scene().removeItem(guide)
        self.snap_guides.clear()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def showEvent(self, event):
        super().showEvent(event)
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def keyPressEvent(self, event):
        if isinstance(self.scene().focusItem(), InlineTextItem):
            super().keyPressEvent(event)
            return
        steps = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0),
                 Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1)}
        if event.key() in steps:
            step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
            dx, dy = steps[event.key()]
            for item in self.scene().selectedItems():
                item.moveBy(dx * step, dy * step)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Shift:
            self.clear_guides()
            for item in self.items_by_id.values():
                item._shift_snap = False
        super().keyReleaseEvent(event)

    def layers(self) -> list[TextOverlay]:
        for item in self.items_by_id.values():
            item.finish_inline_edit()
        return [deepcopy(item.layer) for item in self.items_by_id.values()]

    def composed_image(self) -> QImage:
        return render_portrait(self.base, self.layers())

    def dispose(self):
        """Disconnect scene callbacks before Qt destroys the scene's items."""
        if self._disposed:
            return
        self._disposed = True
        self.clear_guides()
        for item in self.items_by_id.values():
            item.finish_inline_edit()
        self.scene().selectionChanged.disconnect(self.on_selection_changed)
        for item in self.items_by_id.values():
            item.moved.disconnect(self.moved)
            item.resized.disconnect(self.resized)
            item.guides_clear_requested.disconnect(self.clear_guides)
            item.text_changed.disconnect(self.text_changed)
            item.snapper = None
        self.scene().clear()
        self.items_by_id.clear()
        self.background_item = None

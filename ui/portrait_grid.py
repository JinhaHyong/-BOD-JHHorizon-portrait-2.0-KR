"""Virtual portrait cards: visible rows are painted without a widget per file."""
from math import ceil
from PySide6.QtCore import QAbstractListModel, QItemSelectionModel, QModelIndex, QObject, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QPalette, QPen, QPixmap, QPainter
from PySide6.QtWidgets import QAbstractItemView, QFrame, QListView, QStyle, QStyledItemDelegate, QStyleOption

THUMBNAIL_IMAGE_SIZE = (96, 96)
CELL_EDGE = 110


class PortraitThumbnail:
    def __init__(self, record, owner):
        self.file_path = record['path']
        self.stamp = tuple(record['stamp'])
        self.search_name = self.file_path.name.casefold()
        self.pixmap = None
        self.owner = owner

    def set_selected(self, selected):
        self.owner.select(self if selected else None)

    def set_pixmap(self, pixmap):
        self.pixmap = pixmap
        self.owner.notify_images([self])


class PortraitModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries = ()
        self.rows = {}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.entries)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.entries):
            return None
        entry = self.entries[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return entry
        if role == Qt.ItemDataRole.ToolTipRole:
            return entry.file_path.name
        if role == Qt.ItemDataRole.DecorationRole:
            return entry.pixmap
        if role == Qt.ItemDataRole.SizeHintRole:
            return QSize(CELL_EDGE, CELL_EDGE)
        return None

    def replace(self, entries):
        self.beginResetModel()
        self.entries = tuple(entries)
        self.rows = {entry.file_path: row for row, entry in enumerate(self.entries)}
        self.endResetModel()


class PortraitDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return QSize(CELL_EDGE, CELL_EDGE)

    def paint(self, painter, option, index):
        entry = index.data(Qt.ItemDataRole.UserRole)
        if entry is None:
            return
        painter.save()
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            card = QRect(option.rect.x() + 4, option.rect.y() + 4, 102, 102)
            active = option.state & (QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_MouseOver)
            role = QPalette.ColorRole.Link if active else QPalette.ColorRole.Mid
            painter.setPen(QPen(option.palette.color(role), 2))
            painter.setBrush(option.palette.brush(QPalette.ColorRole.Base))
            painter.drawRoundedRect(card.adjusted(1, 1, -1, -1), 5, 5)
            if entry.pixmap is not None:
                painter.drawPixmap(card.x() + 3, card.y() + 3, entry.pixmap)
            else:
                painter.setPen(QPen(option.palette.color(QPalette.ColorRole.Mid), 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(card.adjusted(34, 38, -34, -38), 3, 3)
        finally:
            painter.restore()


class PortraitGridView(QListView):
    priority_changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.side_margin = 0
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(True)
        self.setMovement(QListView.Movement.Static)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setLayoutMode(QListView.LayoutMode.Batched)
        self.setBatchSize(64)
        self.setUniformItemSizes(True)
        self.setGridSize(QSize(CELL_EDGE, CELL_EDGE))
        self.setSpacing(0)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet('QListView { background:transparent; border:0; padding:0; }')
        self.setItemDelegate(PortraitDelegate(self))
        self.priority_timer = QTimer(self)
        self.priority_timer.setSingleShot(True)
        self.priority_timer.timeout.connect(self.update_visible)
        self.verticalScrollBar().valueChanged.connect(self.schedule_visible)
        self.verticalScrollBar().rangeChanged.connect(self.schedule_visible)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.schedule_visible()

    def schedule_visible(self, *_args):
        self.priority_timer.start(0)

    def update_visible(self):
        model = self.model()
        if model is None:
            return
        columns = min(3, max(1, model.rowCount()))
        # QListView reserves an AsNeeded scrollbar while laying out icons, even
        # before it is visible. Use that same stable width for centering.
        margins = self.viewportMargins()
        available = self.maximumViewportSize().width() + margins.left() + margins.right()
        style, bar = self.style(), self.verticalScrollBar()
        if (self.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
                and not style.pixelMetric(QStyle.PixelMetric.PM_ScrollView_ScrollBarOverlap, None, bar)):
            available -= style.pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent, None, bar)
            if style.styleHint(QStyle.StyleHint.SH_ScrollView_FrameOnlyAroundContents, None, self):
                option = QStyleOption()
                option.initFrom(self)
                available -= 2 * style.pixelMetric(QStyle.PixelMetric.PM_DefaultFrameWidth, option, self)
        # Icon wrapping compares against QRect.right(), which is inclusive.
        # An exactly 330px layout can therefore wrap the third 110px cell.
        required = columns * CELL_EDGE + 2
        margin = max(0, (available - required) // 2)
        if margin != self.side_margin:
            self.side_margin = margin
            self.setViewportMargins(margin, 0, margin, 0)
        first = max(0, self.verticalScrollBar().value() // CELL_EDGE) * columns
        amount = (ceil(self.viewport().height() / CELL_EDGE) + 2) * columns
        self.priority_changed.emit([entry.file_path for entry in model.entries[first:first + amount]])


class PortraitGrid(QObject):
    selection_changed = Signal(object)
    clicked = Signal(object)
    priority_changed = Signal(object)

    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.model = PortraitModel(view)
        view.setModel(self.model)
        view.clicked.connect(self.on_clicked)
        view.priority_changed.connect(self.priority_changed.emit)
        self.tiles = []
        self.by_path = {}
        self.visible = ()
        self.selected = None
        self.query = ''
        self._changing_selection = False
        view.selectionModel().selectionChanged.connect(self.on_selection_changed)

    def on_clicked(self, index):
        # Retained as a separate activation notification, e.g. to retry a failed
        # preview. Selection itself always comes from the selection model.
        entry = index.data(Qt.ItemDataRole.UserRole)
        if entry is not None:
            self.clicked.emit(entry)

    def selection_in_view(self):
        indexes = self.view.selectionModel().selectedRows()
        if len(indexes) != 1:
            return None
        entry = indexes[0].data(Qt.ItemDataRole.UserRole)
        return entry if entry is not None and self.by_path.get(entry.file_path) is entry else None

    def publish_selection(self, entry):
        if entry is self.selected:
            return False
        self.selected = entry
        self.selection_changed.emit(entry)
        return True

    def on_selection_changed(self, *_args):
        # Batch selection has its own controller and must never be collapsed to
        # one photo by the main window's single-selection behavior.
        if self._changing_selection or self.view.selectionMode() != QAbstractItemView.SelectionMode.SingleSelection:
            return
        self.publish_selection(self.selection_in_view())

    def clear(self):
        self.set_records([])

    def set_records(self, records):
        self.tiles = [PortraitThumbnail(record, self) for record in records]
        self.by_path = {entry.file_path: entry for entry in self.tiles}
        self.visible = ()
        # Reset even for an empty folder so previous model entries disappear.
        self._changing_selection = True
        try:
            self.model.replace(())
        finally:
            self._changing_selection = False
        self.filter(self.query, None)

    def select(self, entry):
        entry = self.by_path.get(entry.file_path) if entry is not None else None
        row = self.model.rows.get(entry.file_path) if entry is not None else None
        if row is None:
            entry = None
        self._changing_selection = True
        try:
            if entry is None:
                self.view.clearSelection()
                self.view.setCurrentIndex(QModelIndex())
            else:
                self.view.selectionModel().setCurrentIndex(
                    self.model.index(row), QItemSelectionModel.SelectionFlag.ClearAndSelect)
        finally:
            self._changing_selection = False
        return self.publish_selection(entry)

    def filter(self, query, selected_path):
        self.query = query.casefold()
        visible = tuple(entry for entry in self.tiles if self.query in entry.search_name)
        selected = self.by_path.get(selected_path)
        if selected is not None and self.query not in selected.search_name:
            selected = None
        if visible != self.visible:
            self.visible = visible
            self._changing_selection = True
            try:
                self.model.replace(visible)
            finally:
                self._changing_selection = False
        self.select(selected)
        self.view.schedule_visible()
        return selected

    def remove(self, path):
        entry = self.by_path.pop(path, None)
        if entry is None:
            return
        selected_path = self.selected.file_path if self.selected is not None else None
        self.tiles.remove(entry)
        self.filter(self.query, selected_path)

    def update_images(self, payloads):
        changed = []
        for payload in payloads:
            entry = self.by_path.get(payload['path'])
            if entry is not None:
                entry.pixmap = QPixmap.fromImage(payload['image'])
                entry.stamp = tuple(payload['stamp'])
                changed.append(entry)
        self.notify_images(changed)

    def notify_images(self, entries):
        rows = [self.model.rows[entry.file_path] for entry in entries if entry.file_path in self.model.rows]
        if rows:
            self.model.dataChanged.emit(self.model.index(min(rows)), self.model.index(max(rows)),
                                        [Qt.ItemDataRole.DecorationRole])

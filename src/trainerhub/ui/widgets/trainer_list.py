"""Virtualised trainer list: model + flat painted rows (v0.2)."""

from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QModelIndex, QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QListView, QStyle, QStyledItemDelegate, QStyleOptionViewItem

from ...core.models import CatalogItem
from .. import theme as theme_tokens

ITEM_ROLE = Qt.ItemDataRole.UserRole + 1
ROW_HEIGHT = theme_tokens.ROW_HEIGHT


class TrainerListModel(QAbstractListModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: list[CatalogItem] = []

    def set_items(self, items: list[CatalogItem]) -> None:
        self.beginResetModel()
        self._items = items
        self.endResetModel()

    def item_at(self, row: int) -> CatalogItem | None:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def row_of(self, key: tuple[str, str]) -> int:
        for index, item in enumerate(self._items):
            if item.key == key:
                return index
        return -1

    def replace_item(self, item: CatalogItem) -> None:
        row = self.row_of(item.key)
        if row < 0:
            return
        self._items[row] = item
        model_index = self.index(row)
        self.dataChanged.emit(model_index, model_index)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self._items[index.row()]
        if role == ITEM_ROLE:
            return item
        if role == Qt.ItemDataRole.DisplayRole:
            return item.game_name
        return None


class TrainerDelegate(QStyledItemDelegate):
    def __init__(self, owner, theme: str = "light", parent=None) -> None:
        super().__init__(parent)
        self.owner = owner
        self.theme = theme
        self._source_names: dict[str, str] = {}
        self._installed_keys: set[tuple[str, str]] = set()
        self._remote_keys: set[tuple[str, str]] = set()

    def set_theme(self, theme: str) -> None:
        self.theme = theme

    def set_source_names(self, names: dict[str, str]) -> None:
        self._source_names = names

    def set_installed_keys(self, keys: set[tuple[str, str]]) -> None:
        self._installed_keys = keys

    def set_remote_keys(self, keys: set[tuple[str, str]]) -> None:
        self._remote_keys = keys

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        return QSize(option.rect.width(), ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        item: CatalogItem | None = index.data(ITEM_ROLE)
        if item is None:
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        rect = QRect(option.rect)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        if selected:
            painter.fillRect(rect, theme_tokens.color(self.theme, "sunken"))
        elif hovered:
            painter.fillRect(rect, theme_tokens.color(self.theme, "hover"))
        else:
            painter.fillRect(rect, theme_tokens.color(self.theme, "surface"))

        # hairline separator, inset like the demo
        painter.setPen(QColor(theme_tokens.token(self.theme, "line")))
        painter.drawLine(rect.left() + 18, rect.bottom(), rect.right() - 18, rect.bottom())

        left = rect.left() + 18
        right = rect.right() - 18

        title_font = QFont(option.font)
        title_font.setPointSizeF(10.5)
        title_font.setWeight(QFont.Weight.Medium)
        painter.setFont(title_font)
        painter.setPen(theme_tokens.color(self.theme, "text"))
        title_metrics = QFontMetrics(title_font)
        title = title_metrics.elidedText(item.game_name or item.title, Qt.TextElideMode.ElideRight, right - left)
        painter.drawText(
            QRect(left, rect.top() + 10, right - left, 20),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            title,
        )

        sub_font = QFont(option.font)
        sub_font.setPointSizeF(8.9)
        painter.setFont(sub_font)
        painter.setPen(theme_tokens.color(self.theme, "dim"))
        source_name = self._source_names.get(item.source_id, item.source_id)
        subtitle = source_name
        if item.key in self._remote_keys:
            subtitle = f"{source_name} · {_live_label()}"
        sub_metrics = QFontMetrics(sub_font)
        subtitle = sub_metrics.elidedText(subtitle, Qt.TextElideMode.ElideRight, right - left)
        painter.drawText(
            QRect(left, rect.top() + 30, right - left, 16),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            subtitle,
        )

        if item.key in self._installed_keys:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme_tokens.color(self.theme, "success"))
            painter.drawEllipse(QPoint(right - 3, rect.center().y()), 3, 3)

        painter.restore()


def _live_label() -> str:
    from ...i18n import tr

    return tr("source.live")


class TrainerListView(QListView):
    """Adds reliable hover tracking on top of QListView."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("TrainerList")
        self.hover_row = -1
        self.setMouseTracking(True)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSpacing(0)
        self.setFrameShape(QListView.Shape.NoFrame)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        index = self.indexAt(event.position().toPoint())
        row = index.row() if index.isValid() else -1
        if row != self.hover_row:
            self.hover_row = row
            self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self.hover_row != -1:
            self.hover_row = -1
            self.viewport().update()
        super().leaveEvent(event)

    def visual_rect_for_row(self, row: int) -> QRect:
        index = self.model().index(row, 0)
        return self.visualRect(index) if index.isValid() else QRect(QPoint(0, 0), QSize(0, 0))

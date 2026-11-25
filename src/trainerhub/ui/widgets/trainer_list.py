"""Virtualised trainer list: model + painted delegate + hover-aware view."""

from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QModelIndex, QPoint, QRect, QSize, Qt
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QListView, QStyle, QStyledItemDelegate, QStyleOptionViewItem

from ...core.models import CatalogItem
from ...core.textutil import human_size
from .. import theme as theme_tokens

ITEM_ROLE = Qt.ItemDataRole.UserRole + 1
ROW_HEIGHT = 68


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
    def __init__(self, owner, theme: str = "dark", parent=None) -> None:
        super().__init__(parent)
        self.owner = owner
        self.theme = theme
        self._source_names: dict[str, str] = {}

    def set_theme(self, theme: str) -> None:
        self.theme = theme

    def set_source_names(self, names: dict[str, str]) -> None:
        self._source_names = names

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        return QSize(option.rect.width(), ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        item: CatalogItem | None = index.data(ITEM_ROLE)
        if item is None:
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRect(option.rect)
        rect.setLeft(rect.left() + 6)
        rect.setRight(rect.right() - 6)
        card = QRect(rect.left(), rect.top() + 3, rect.width(), rect.height() - 7)

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        bg_name = "primary_soft" if selected else ("elevated" if hovered else "surface")
        painter.setBrush(theme_tokens.color(self.theme, bg_name))
        border = "primary" if selected else ("line_strong" if hovered else "line")
        painter.setPen(QPen(theme_tokens.color(self.theme, border), 1))
        painter.drawRoundedRect(card, 10, 10)

        if selected:
            accent = QRect(card.left() + 1, card.top() + 12, 2, card.height() - 24)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme_tokens.color(self.theme, "primary"))
            painter.drawRoundedRect(accent, 1, 1)

        # -- left: title + subtitle -------------------------------------
        text_left = card.left() + (16 if selected else 14)
        right_reserved = 168
        text_width = max(80, card.width() - (text_left - card.left()) - right_reserved)

        title_font = QFont(option.font)
        title_font.setPointSizeF(10.5)
        title_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(title_font)
        painter.setPen(theme_tokens.color(self.theme, "text"))
        title_metrics = QFontMetrics(title_font)
        title = title_metrics.elidedText(item.game_name or item.title, Qt.TextElideMode.ElideRight, text_width)
        painter.drawText(
            QRect(text_left, card.top() + 14, text_width, 20),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            title,
        )

        sub_font = QFont(option.font)
        sub_font.setPointSizeF(8.8)
        painter.setFont(sub_font)
        painter.setPen(theme_tokens.color(self.theme, "muted"))
        source_name = self._source_names.get(item.source_id, item.source_id)
        pieces = [source_name]
        if item.game_alias:
            pieces.append(item.game_alias)
        elif item.game_version and len(item.game_version) <= 24 and any(ch.isdigit() for ch in item.game_version):
            version_text = item.game_version
            pieces.append(version_text if version_text.lower().startswith("v") else f"v{version_text}")
        subtitle = "  ·  ".join(piece for piece in pieces if piece)
        sub_metrics = QFontMetrics(sub_font)
        subtitle = sub_metrics.elidedText(subtitle, Qt.TextElideMode.ElideRight, text_width)
        painter.drawText(
            QRect(text_left, card.top() + 34, text_width, 18),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            subtitle,
        )

        # -- right: version pill on top, meta line underneath -----------
        right = card.right() - 14
        version = item.version or ""
        if version:
            pill_font = QFont(option.font)
            pill_font.setPointSizeF(8.2)
            pill_font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(pill_font)
            pill_metrics = QFontMetrics(pill_font)
            pill_width = min(120, pill_metrics.horizontalAdvance(version) + 16)
            pill = QRect(right - pill_width, card.top() + 13, pill_width, 19)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme_tokens.color(self.theme, "primary_soft"))
            painter.drawRoundedRect(pill, 5, 5)
            painter.setPen(theme_tokens.color(self.theme, "primary"))
            painter.drawText(pill, int(Qt.AlignmentFlag.AlignCenter), version)

        meta_parts = [item.updated_at, human_size(item.file_size) if item.file_size else ""]
        meta_text = "  ·  ".join(part for part in meta_parts if part)
        if meta_text:
            meta_font = QFont(option.font)
            meta_font.setPointSizeF(8.0)
            painter.setFont(meta_font)
            painter.setPen(theme_tokens.color(self.theme, "dim"))
            meta_width = QFontMetrics(meta_font).horizontalAdvance(meta_text)
            painter.drawText(
                QRect(right - meta_width, card.top() + 37, meta_width, 14),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                meta_text,
            )

        painter.restore()


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

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)

    def visual_rect_for_row(self, row: int) -> QRect:
        index = self.model().index(row, 0)
        return self.visualRect(index) if index.isValid() else QRect(QPoint(0, 0), QSize(0, 0))

"""Virtualised trainer list: model + flat painted rows (v0.2)."""

from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QEvent, QModelIndex, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QListView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionButton,
    QStyleOptionViewItem,
)

from ...core.models import CatalogItem, RecommendationEntry
from ...i18n import tr
from .. import theme as theme_tokens

ITEM_ROLE = Qt.ItemDataRole.UserRole + 1
ENTRY_ROLE = Qt.ItemDataRole.UserRole + 2
ROW_HEIGHT = theme_tokens.ROW_HEIGHT
SELECTABLE = {"ready", "failed", "cancelled"}


class TrainerListModel(QAbstractListModel):
    checked_changed = Signal(object, bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: list[CatalogItem] = []
        self._entries: list[RecommendationEntry] = []

    def set_items(self, items: list[CatalogItem]) -> None:
        self.beginResetModel()
        self._items = items
        self._entries = []
        self.endResetModel()

    def set_entries(self, entries: list[RecommendationEntry]) -> None:
        self.beginResetModel()
        self._entries = entries
        self._items = [entry.item for entry in entries]
        self.endResetModel()

    def entry_at(self, row: int) -> RecommendationEntry | None:
        return self._entries[row] if 0 <= row < len(self._entries) else None

    def flags(self, index):
        flags = super().flags(index)
        entry = self.entry_at(index.row()) if index.isValid() else None
        if entry is not None and entry.action == "download" and entry.state in SELECTABLE:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole) -> bool:  # noqa: N802
        entry = self.entry_at(index.row()) if index.isValid() else None
        if role != Qt.ItemDataRole.CheckStateRole or entry is None or not self.flags(index) & Qt.ItemFlag.ItemIsUserCheckable:
            return False
        entry.selected = value == Qt.CheckState.Checked or value == Qt.CheckState.Checked.value
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
        self.checked_changed.emit(entry.item.key, entry.selected)
        return True

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
        entry = self.entry_at(index.row())
        if role == ENTRY_ROLE:
            return entry
        if role == Qt.ItemDataRole.CheckStateRole and entry is not None:
            return Qt.CheckState.Checked if entry.selected else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.DisplayRole:
            return entry.game.name if entry is not None else item.game_name
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return f"{entry.game.name if entry else item.game_name} {item.source_id}"
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
        entry = index.data(ENTRY_ROLE)
        if entry is not None:
            check = QStyleOptionButton()
            check.rect = QRect(left, rect.center().y() - 8, 16, 16)
            check.state = QStyle.StateFlag.State_On if entry.selected else QStyle.StateFlag.State_Off
            if index.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                check.state |= QStyle.StateFlag.State_Enabled
            QApplication.style().drawControl(QStyle.ControlElement.CE_CheckBox, check, painter)
            left += 30
        state = entry.state if entry is not None else ""
        if item.key in self._installed_keys:
            state = "installed"
        if state and state != "ready":
            label = tr("discovery.installed") if state in {"installed", "done"} else tr(f"state.{state}")
            painter.setPen(theme_tokens.color(self.theme, "dim"))
            painter.drawText(QRect(right - 86, rect.top(), 86, rect.height()),
                             int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), label)
            right -= 98

        details_rect = QRect(rect.right() - 142, rect.center().y() - 16, 60, 32)
        download_rect = QRect(rect.right() - 76, rect.center().y() - 16, 60, 32)
        for button_rect, text, primary in ((details_rect, tr("action.details"), False),
                                           (download_rect, tr("action.download_short"), True)):
            painter.setPen(theme_tokens.color(self.theme, "line_strong") if not primary else Qt.PenStyle.NoPen)
            painter.setBrush(theme_tokens.color(self.theme, "primary" if primary else "surface"))
            painter.drawRoundedRect(button_rect, 7, 7)
            painter.setPen(QColor("#FFFFFF") if primary else theme_tokens.color(self.theme, "text"))
            painter.drawText(button_rect, int(Qt.AlignmentFlag.AlignCenter), text)
        right = min(right, details_rect.left() - 12)

        title_font = QFont(option.font)
        title_font.setPointSizeF(10.5)
        title_font.setWeight(QFont.Weight.Medium)
        painter.setFont(title_font)
        painter.setPen(theme_tokens.color(self.theme, "text"))
        title_metrics = QFontMetrics(title_font)
        title = title_metrics.elidedText(entry.game.name if entry else (item.game_name or item.title), Qt.TextElideMode.ElideRight, max(0, right - left))
        painter.drawText(
            QRect(left, rect.top(), right - left, rect.height()),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            title,
        )

        painter.restore()

    def editorEvent(self, event, model, option, index) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            rect = option.rect
            position = event.position().toPoint()
            if QRect(rect.right() - 142, rect.center().y() - 16, 60, 32).contains(position):
                self.owner.view.setCurrentIndex(index)
                return True
            if QRect(rect.right() - 76, rect.center().y() - 16, 60, 32).contains(position):
                item = index.data(ITEM_ROLE)
                entry = index.data(ENTRY_ROLE)
                if item is not None and (entry is None or entry.state in SELECTABLE):
                    if entry is not None and entry.action == "external":
                        self.owner.open_page_requested.emit(item)
                    else:
                        self.owner.download_requested.emit(item)
                return True
        if not index.flags() & Qt.ItemFlag.ItemIsUserCheckable:
            return False
        toggle = False
        if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            toggle = QRect(option.rect.left() + 14, option.rect.top(), 28, option.rect.height()).contains(event.position().toPoint())
        elif event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Space:
            toggle = True
        if toggle:
            checked = index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
            return model.setData(index, Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
        return False


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

    def mousePressEvent(self, event) -> None:  # noqa: N802
        index = self.indexAt(event.position().toPoint())
        if (event.button() == Qt.MouseButton.LeftButton and index.isValid()
                and index.data(ENTRY_ROLE) is not None
                and event.position().x() < 44):
            self._check_press = index
            event.accept()
            return
        self._check_press = None
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        index = getattr(self, "_check_press", None)
        if index is not None:
            self._check_press = None
            if index == self.indexAt(event.position().toPoint()):
                checked = index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
                self.model().setData(index, Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked,
                                     Qt.ItemDataRole.CheckStateRole)
            event.accept()
            return
        super().mouseReleaseEvent(event)

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

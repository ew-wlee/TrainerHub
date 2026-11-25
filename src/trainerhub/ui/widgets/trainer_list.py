"""Virtualised trainer list: model + flat painted rows (v0.2)."""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractListModel,
    QEasingCurve,
    QModelIndex,
    QPoint,
    QRect,
    QSize,
    Qt,
    QVariantAnimation,
    Signal,
)
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
from ..motion import animations_enabled

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
        self._job_states: dict[tuple[str, str], str] = {}
        self._job_progress: dict[tuple[str, str], int] = {}

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
        state = self._job_states.get(item.key, entry.state if entry is not None else "")
        if item.key in self._installed_keys:
            state = "installed"
        active = state in {"queued", "resolving", "downloading", "extracting", "installing"}
        first_text = tr("action.open_short") if state == "installed" else tr("action.details")
        second_text = tr("action.delete") if state == "installed" else tr("action.download_short")
        if active:
            percent = self._job_progress.get(item.key)
            second_text = f"{percent}%" if state == "downloading" and percent is not None else tr(f"state.{state}")
        details_rect, download_rect = self.owner.view.action_rects(rect)
        for button_rect, text, primary in ((details_rect, first_text, False),
                                           (download_rect, second_text, state != "installed")):
            painter.setPen(theme_tokens.color(self.theme, "line_strong") if not primary else Qt.PenStyle.NoPen)
            color = "sunken" if active and primary else ("primary" if primary else "surface")
            pressed = self.owner.view._action_press
            view = self.owner.view
            is_first = button_rect == details_rect
            feedback = view._feedback_key == item.key and (view._feedback_action == "first") == is_first
            if pressed and pressed[0] == index and ((pressed[1] == "first") == is_first):
                color = "primary_deep" if primary else "sunken"
            base = theme_tokens.color(self.theme, color)
            if feedback and not pressed:
                dark = theme_tokens.color(self.theme, "primary_deep" if primary else "sunken")
                amount = float(view._feedback.currentValue() or 0)
                base = QColor.fromRgbF(*(base.getRgbF()[i] * (1 - amount) + dark.getRgbF()[i] * amount
                                         for i in range(3)))
            painter.setBrush(base)
            painter.drawRoundedRect(button_rect, 7, 7)
            painter.setPen(QColor("#FFFFFF") if primary and not active else theme_tokens.color(self.theme, "text"))
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

class TrainerListView(QListView):
    """Adds reliable hover tracking on top of QListView."""

    action_requested = Signal(object, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("TrainerList")
        self.setAccessibleDescription(tr("discover.keyboard_help"))
        self.hover_row = -1
        self.setMouseTracking(True)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSpacing(0)
        self.setFrameShape(QListView.Shape.NoFrame)
        self._action_press = None
        self._feedback_key = None
        self._feedback_action = ""
        self._feedback = QVariantAnimation(self)
        self._feedback.setDuration(120)
        self._feedback.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._feedback.valueChanged.connect(lambda _: self.viewport().update())

    @staticmethod
    def action_rects(rect: QRect) -> tuple[QRect, QRect]:
        return (QRect(rect.right() - 160, rect.center().y() - 16, 68, 32),
                QRect(rect.right() - 84, rect.center().y() - 16, 68, 32))

    def mousePressEvent(self, event) -> None:  # noqa: N802
        index = self.indexAt(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and index.isValid():
            for action, rect in zip(("first", "second"), self.action_rects(self.visualRect(index)), strict=True):
                if rect.contains(event.position().toPoint()):
                    self._feedback.stop()
                    self._feedback_key = None
                    self._action_press = (index, action)
                    self.viewport().update()
                    event.accept()
                    return
        if (event.button() == Qt.MouseButton.LeftButton and index.isValid()
                and index.data(ENTRY_ROLE) is not None
                and event.position().x() < 44):
            self._check_press = index
            event.accept()
            return
        self._check_press = None
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._action_press is not None:
            index, action = self._action_press
            self._action_press = None
            rects = self.action_rects(self.visualRect(index))
            target = rects[0 if action == "first" else 1]
            if index == self.indexAt(event.position().toPoint()) and target.contains(event.position().toPoint()):
                item = index.data(ITEM_ROLE)
                if item is not None and animations_enabled():
                    self._feedback_key = item.key
                    self._feedback_action = action
                    self._feedback.setStartValue(1.0)
                    self._feedback.setEndValue(0.0)
                    self._feedback.start()
                self.action_requested.emit(index, action)
            self.viewport().update()
            event.accept()
            return
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

    def keyPressEvent(self, event) -> None:  # noqa: N802
        index = self.currentIndex()
        if index.isValid() and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Delete, Qt.Key.Key_D):
            action = ("first" if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                      else "delete" if event.key() == Qt.Key.Key_Delete else "download")
            self.action_requested.emit(index, action)
            event.accept()
            return
        super().keyPressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        index = self.indexAt(event.position().toPoint())
        row = index.row() if index.isValid() else -1
        if row != self.hover_row:
            self.hover_row = row
            self.viewport().update()
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        index = self.indexAt(event.position().toPoint())
        if index.isValid() and any(rect.contains(event.position().toPoint())
                                   for rect in self.action_rects(self.visualRect(index))):
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self.hover_row != -1:
            self.hover_row = -1
            self.viewport().update()
        super().leaveEvent(event)

    def visual_rect_for_row(self, row: int) -> QRect:
        index = self.model().index(row, 0)
        return self.visualRect(index) if index.isValid() else QRect(QPoint(0, 0), QSize(0, 0))

"""Library: the games you installed, with actions on hover."""

from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from ...core.models import InstalledItem
from ...i18n import tr
from ..widgets.common import EmptyState, HeaderBar


class InstalledRow(QFrame):
    open_requested = Signal(object)
    run_requested = Signal(object)
    delete_requested = Signal(object)

    def __init__(self, record: InstalledItem, update_to: str = "", parent=None) -> None:
        super().__init__(parent)
        self.record = record
        self.setObjectName("LibraryRow")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setFixedHeight(56)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 0, 12, 0)
        layout.setSpacing(8)

        self.title = QLabel(record.game_name or record.path.rsplit("/", 1)[-1])
        self.title.setObjectName("RowTitle")
        layout.addWidget(self.title, 1)

        self.actions = QWidget()
        actions_layout = QHBoxLayout(self.actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(2)

        open_button = QPushButton(tr("action.open_folder"))
        open_button.setObjectName("LinkButton")
        open_button.setCursor(Qt.CursorShape.PointingHandCursor)
        open_button.clicked.connect(lambda: self.open_requested.emit(self.record))
        actions_layout.addWidget(open_button)

        if sys.platform.startswith("win"):
            run_button = QPushButton(tr("action.run"))
            run_button.setObjectName("LinkButton")
            run_button.setCursor(Qt.CursorShape.PointingHandCursor)
            run_button.clicked.connect(lambda: self.run_requested.emit(self.record))
            actions_layout.addWidget(run_button)

        delete_button = QPushButton(tr("action.delete"))
        delete_button.setObjectName("DangerButton")
        delete_button.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_button.clicked.connect(lambda: self.delete_requested.emit(self.record))
        actions_layout.addWidget(delete_button)

        self._effect = QGraphicsOpacityEffect(self.actions)
        self._effect.setOpacity(0.0)
        self.actions.setGraphicsEffect(self._effect)
        layout.addWidget(self.actions)

        for button in self.actions.findChildren(QPushButton):
            button.installEventFilter(self)

    def _show_actions(self, visible: bool) -> None:
        self._effect.setOpacity(1.0 if visible else 0.0)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._show_actions(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if not self.actions.underMouse() and not self.actions.hasFocus():
            self._show_actions(False)
        super().leaveEvent(event)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched.parent() is self.actions:
            if event.type() == QEvent.Type.FocusIn:
                self._show_actions(True)
            elif event.type() == QEvent.Type.FocusOut:
                QTimer.singleShot(0, self._hide_if_unfocused)
        return super().eventFilter(watched, event)

    def _hide_if_unfocused(self) -> None:
        if not self.actions.hasFocus() and not self.underMouse():
            self._show_actions(False)


class LibraryPage(QWidget):
    import_requested = Signal()
    refresh_requested = Signal()
    update_check_requested = Signal()
    open_requested = Signal(object)
    run_requested = Signal(object)
    delete_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = HeaderBar(tr("library.title"))
        self.update_button = QPushButton(tr("action.check_updates"))
        self.update_button.setObjectName("LinkButton")
        self.update_button.clicked.connect(self.update_check_requested.emit)
        self.import_button = QPushButton(tr("action.import"))
        self.import_button.setObjectName("GhostButton")
        self.import_button.clicked.connect(self.import_requested.emit)
        for button in (self.update_button, self.import_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.add_action(self.update_button)
        self.header.add_action(self.import_button)
        layout.addWidget(self.header)

        host = QWidget()
        self.stack = QStackedLayout(host)
        self.stack.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 0, 0, 16)
        self.container_layout.setSpacing(0)
        self.container_layout.addStretch(1)
        self.scroll.setWidget(self.container)

        self.empty = EmptyState(tr("library.empty.title"), tr("library.empty.body"), tr("action.import"))
        self.empty.action.clicked.connect(self.import_requested.emit)

        self.stack.addWidget(self.scroll)
        self.stack.addWidget(self.empty)
        layout.addWidget(host, 1)

    def set_records(self, records: list[InstalledItem], updates: dict[tuple[str, str], str] | None = None) -> None:
        while self.container_layout.count() > 1:
            entry = self.container_layout.takeAt(0)
            widget = entry.widget()
            if widget is not None:
                widget.deleteLater()

        for record in records:
            row = InstalledRow(record)
            row.open_requested.connect(self.open_requested.emit)
            row.run_requested.connect(self.run_requested.emit)
            row.delete_requested.connect(self.delete_requested.emit)
            self.container_layout.insertWidget(self.container_layout.count() - 1, row)

        self.stack.setCurrentIndex(0 if records else 1)

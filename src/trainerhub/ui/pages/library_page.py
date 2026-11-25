"""Library: the games you installed, with actions on hover."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
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
from ..widgets.common import ElidedLabel, EmptyState, HeaderBar


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

        self.title = ElidedLabel(record.game_name or record.path.rsplit("/", 1)[-1], Qt.TextElideMode.ElideRight)
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
            run_button.setObjectName("RunButton")
            run_button.setCursor(Qt.CursorShape.PointingHandCursor)
            run_button.clicked.connect(lambda: self.run_requested.emit(self.record))
            actions_layout.addWidget(run_button)

        delete_button = QPushButton(tr("action.delete"))
        delete_button.setObjectName("DangerButton")
        delete_button.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_button.clicked.connect(lambda: self.delete_requested.emit(self.record))
        actions_layout.addWidget(delete_button)

        layout.addWidget(self.actions)

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
        self._layout = layout
        self.section_title = QLabel(tr("library.added"))
        self.section_title.setObjectName("SectionTitle")
        self.section_title.setContentsMargins(24, 12, 24, 6)
        layout.addWidget(self.section_title)

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

    def add_downloads(self, downloads: QWidget) -> None:
        self._layout.insertWidget(1, downloads)

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

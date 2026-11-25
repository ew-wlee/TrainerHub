"""Library page: what is installed, how big it is, and what can be updated."""

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
from ...core.textutil import human_size
from ...i18n import tr
from ..widgets.common import Badge, ElidedLabel, EmptyState, HeaderBar, StatCard


class InstalledRow(QFrame):
    open_requested = Signal(object)
    run_requested = Signal(object)
    delete_requested = Signal(object)

    def __init__(self, record: InstalledItem, update_to: str = "", parent=None) -> None:
        super().__init__(parent)
        self.record = record
        self.setObjectName("RowCard")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        title = QLabel(record.game_name or record.path.rsplit("/", 1)[-1])
        title.setObjectName("RowTitle")
        meta = ElidedLabel(
            f"{record.source_id}  ·  {human_size(record.size_bytes)}  ·  {record.path}"
        )
        meta.setObjectName("RowSub")
        meta.setMaximumWidth(560)
        text_col.addWidget(title)
        text_col.addWidget(meta)

        version = Badge(record.version or "—", "primary")
        layout.addLayout(text_col, 1)
        layout.addWidget(version)

        if update_to:
            layout.addWidget(Badge(tr("library.update.available") + f" → {update_to}", "warn"))

        open_button = QPushButton(tr("action.open_folder"))
        open_button.setObjectName("GhostButton")
        open_button.setCursor(Qt.CursorShape.PointingHandCursor)
        open_button.clicked.connect(lambda: self.open_requested.emit(self.record))
        layout.addWidget(open_button)

        if sys.platform.startswith("win"):
            run_button = QPushButton(tr("action.run"))
            run_button.setObjectName("GhostButton")
            run_button.setCursor(Qt.CursorShape.PointingHandCursor)
            run_button.clicked.connect(lambda: self.run_requested.emit(self.record))
            layout.addWidget(run_button)

        delete_button = QPushButton(tr("action.delete"))
        delete_button.setObjectName("DangerButton")
        delete_button.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_button.clicked.connect(lambda: self.delete_requested.emit(self.record))
        layout.addWidget(delete_button)


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

        self.header = HeaderBar(tr("library.title"), tr("library.empty.body"))
        self.update_button = QPushButton(tr("action.check_updates"))
        self.update_button.setObjectName("GhostButton")
        self.update_button.clicked.connect(self.update_check_requested.emit)
        self.import_button = QPushButton(tr("action.import"))
        self.import_button.setObjectName("PrimaryButton")
        self.import_button.clicked.connect(self.import_requested.emit)
        for button in (self.update_button, self.import_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.add_action(self.update_button)
        self.header.add_action(self.import_button)
        layout.addWidget(self.header)

        stats_row = QHBoxLayout()
        stats_row.setContentsMargins(20, 4, 20, 12)
        stats_row.setSpacing(10)
        self.stat_items = StatCard(tr("library.stat.items"))
        self.stat_size = StatCard(tr("library.stat.size"))
        self.stat_sources = StatCard(tr("library.stat.sources"))
        self.stat_updates = StatCard(tr("library.stat.updates"))
        for card in (self.stat_items, self.stat_size, self.stat_sources, self.stat_updates):
            stats_row.addWidget(card, 1)
        layout.addLayout(stats_row)

        host = QWidget()
        self.stack = QStackedLayout(host)
        self.stack.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(20, 0, 20, 20)
        self.container_layout.setSpacing(8)
        self.container_layout.addStretch(1)
        self.scroll.setWidget(self.container)

        self.empty = EmptyState(tr("library.empty.title"), tr("library.empty.body"), tr("action.import"))
        self.empty.action.clicked.connect(self.import_requested.emit)

        self.stack.addWidget(self.scroll)
        self.stack.addWidget(self.empty)
        layout.addWidget(host, 1)

    def set_records(self, records: list[InstalledItem], updates: dict[tuple[str, str], str] | None = None) -> None:
        updates = updates or {}
        while self.container_layout.count() > 1:
            entry = self.container_layout.takeAt(0)
            widget = entry.widget()
            if widget is not None:
                widget.deleteLater()

        for record in records:
            row = InstalledRow(record, updates.get(record.key, ""))
            row.open_requested.connect(self.open_requested.emit)
            row.run_requested.connect(self.run_requested.emit)
            row.delete_requested.connect(self.delete_requested.emit)
            self.container_layout.insertWidget(self.container_layout.count() - 1, row)

        self.stack.setCurrentIndex(0 if records else 1)
        self.stat_items.set_value(str(len(records)))
        total_size = sum(record.size_bytes for record in records)
        self.stat_size.set_value(human_size(total_size) if total_size else "0 B")
        self.stat_sources.set_value(str(len({record.source_id for record in records})))
        self.stat_updates.set_value(str(len(updates)))

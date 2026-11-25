"""Download centre: one row per job with inline progress."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from ...core.models import CatalogItem
from ...core.textutil import human_size
from ...i18n import tr
from ..widgets.common import Badge, EmptyState, HeaderBar


class DownloadRow(QFrame):
    cancel_requested = Signal(str)

    def __init__(self, job_id: str, item: CatalogItem, source_name: str, parent=None) -> None:
        super().__init__(parent)
        self.job_id = job_id
        self.setObjectName("RowCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 12)
        layout.setSpacing(7)

        top = QHBoxLayout()
        top.setSpacing(10)
        self.title = QLabel(item.game_name or item.title)
        self.title.setObjectName("RowTitle")
        self.sub = QLabel(f"{source_name}  ·  {item.version or '—'}")
        self.sub.setObjectName("RowSub")
        self.badge = Badge(tr("state.queued"), "primary")
        self.cancel_button = QPushButton(tr("action.cancel"))
        self.cancel_button.setObjectName("LinkButton")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(lambda: self.cancel_requested.emit(self.job_id))

        top.addWidget(self.title)
        top.addWidget(self.sub)
        top.addStretch(1)
        top.addWidget(self.badge)
        top.addWidget(self.cancel_button)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)

        self.message = QLabel("")
        self.message.setObjectName("RowSub")
        self.message.setVisible(False)

        layout.addLayout(top)
        layout.addWidget(self.progress)
        layout.addWidget(self.message)

    def set_state(self, state: str, message: str = "") -> None:
        level = {
            "queued": "primary",
            "resolving": "primary",
            "downloading": "primary",
            "extracting": "primary",
            "installing": "primary",
            "done": "success",
            "failed": "danger",
            "cancelled": "warn",
        }.get(state, "primary")
        self.badge.setText(tr(f"state.{state}"))
        self.badge.set_level(level)
        self.progress.setProperty("state", "done" if state == "done" else ("failed" if state == "failed" else ""))
        self.progress.style().unpolish(self.progress)
        self.progress.style().polish(self.progress)

        if state in {"done", "failed", "cancelled"}:
            self.cancel_button.setVisible(False)
            if state == "done":
                self.progress.setValue(1000)
        if message:
            self.message.setText(message)
            self.message.setVisible(True)
        if state == "done":
            self.message.setVisible(False)

    def set_progress(self, received: int, total: int) -> None:
        if total > 0:
            self.progress.setValue(int(received / total * 1000))
            self.message.setText(f"{human_size(received)} / {human_size(total)}")
        else:
            self.message.setText(human_size(received))
        self.message.setVisible(True)


class DownloadsPage(QWidget):
    cancel_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: dict[str, DownloadRow] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = HeaderBar(tr("downloads.title"), tr("downloads.empty.body"))
        self.clear_button = QPushButton(tr("action.clear"))
        self.clear_button.setObjectName("GhostButton")
        self.clear_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_button.clicked.connect(self.clear_finished)
        self.header.add_action(self.clear_button)
        layout.addWidget(self.header)

        host = QWidget()
        self.stack = QStackedLayout(host)
        self.stack.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(20, 4, 20, 20)
        self.container_layout.setSpacing(8)
        self.container_layout.addStretch(1)
        self.scroll.setWidget(self.container)

        self.empty = EmptyState(tr("downloads.empty.title"), tr("downloads.empty.body"))
        self.stack.addWidget(self.scroll)
        self.stack.addWidget(self.empty)
        self.stack.setCurrentIndex(1)

        layout.addWidget(host, 1)

    def add_job(self, job_id: str, item: CatalogItem, source_name: str) -> None:
        if job_id in self._rows:
            return
        row = DownloadRow(job_id, item, source_name)
        row.cancel_requested.connect(self.cancel_requested.emit)
        self.container_layout.insertWidget(self.container_layout.count() - 1, row)
        self._rows[job_id] = row
        self.stack.setCurrentIndex(0)

    def update_state(self, job_id: str, state: str, message: str = "") -> None:
        row = self._rows.get(job_id)
        if row:
            row.set_state(state, message)

    def update_progress(self, job_id: str, received: int, total: int) -> None:
        row = self._rows.get(job_id)
        if row:
            row.set_progress(received, total)

    def clear_finished(self) -> None:
        for job_id, row in list(self._rows.items()):
            if row.badge.text() in {tr("state.done"), tr("state.cancelled"), tr("state.failed")}:
                self.container_layout.removeWidget(row)
                row.deleteLater()
                self._rows.pop(job_id, None)
        if not self._rows:
            self.stack.setCurrentIndex(1)

    def active_count(self) -> int:
        active = 0
        for row in self._rows.values():
            if row.badge.text() in {tr("state.queued"), tr("state.downloading"), tr("state.resolving"),
                                    tr("state.extracting"), tr("state.installing")}:
                active += 1
        return active

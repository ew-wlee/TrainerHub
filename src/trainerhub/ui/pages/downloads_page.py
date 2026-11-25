"""Download centre: one flat line per job with inline progress."""

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
from ...i18n import tr
from ..widgets.common import EmptyState, HeaderBar, SegmentedControl, repolish

ACTIVE_STATES = {"queued", "resolving", "downloading", "extracting", "installing"}


class DownloadRow(QFrame):
    cancel_requested = Signal(str)

    def __init__(self, job_id: str, item: CatalogItem, source_name: str, parent=None) -> None:
        super().__init__(parent)
        self.job_id = job_id
        self.state = "queued"
        self.setObjectName("DownloadRow")
        self.setFixedHeight(56)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 0, 12, 0)
        layout.setSpacing(16)

        self.title = QLabel(item.game_name or item.title)
        self.title.setObjectName("RowTitle")

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(200)

        self.percent = QLabel("0%")
        self.percent.setObjectName("TaskPercent")
        self.percent.setFixedWidth(38)
        self.percent.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.status = QLabel(tr("state.queued"))
        self.status.setObjectName("TaskState")
        self.status.setFixedWidth(76)
        self.status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.cancel_button = QPushButton(tr("action.cancel"))
        self.cancel_button.setObjectName("LinkButton")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(lambda: self.cancel_requested.emit(self.job_id))

        layout.addWidget(self.title, 1)
        layout.addWidget(self.progress)
        layout.addWidget(self.percent)
        layout.addWidget(self.status)
        layout.addWidget(self.cancel_button)

    def set_state(self, state: str, message: str = "") -> None:
        self.state = state
        self.status.setText(tr(f"state.{state}"))
        self.status.setProperty(
            "level", "danger" if state == "failed" else ("success" if state == "done" else "normal")
        )
        repolish(self.status)
        self.progress.setProperty("state", "done" if state == "done" else ("failed" if state == "failed" else ""))
        repolish(self.progress)

        if state == "done":
            self.progress.setValue(1000)
            self.percent.setText("100%")
        if state not in ACTIVE_STATES:
            self.cancel_button.hide()
        if message:
            self.setToolTip(message)

    def set_progress(self, received: int, total: int) -> None:
        if total > 0:
            value = int(received / total * 1000)
            self.progress.setValue(value)
            self.percent.setText(f"{value // 10}%")


class DownloadsPage(QWidget):
    cancel_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: dict[str, DownloadRow] = {}
        self._filter = "all"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = HeaderBar(tr("downloads.title"))
        self.filters = SegmentedControl(
            [
                ("all", tr("downloads.filter.all")),
                ("active", tr("downloads.filter.active")),
                ("done", tr("downloads.filter.done")),
            ]
        )
        self.filters.changed.connect(self._on_filter)
        self.header.add_action(self.filters)
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

        self.empty = EmptyState(tr("downloads.empty.title"), tr("downloads.empty.body"))
        self.stack.addWidget(self.scroll)
        self.stack.addWidget(self.empty)
        self.stack.setCurrentIndex(1)

        layout.addWidget(host, 1)

    # -- jobs -------------------------------------------------------------
    def add_job(self, job_id: str, item: CatalogItem, source_name: str) -> None:
        if job_id in self._rows:
            return
        row = DownloadRow(job_id, item, source_name)
        row.cancel_requested.connect(self.cancel_requested.emit)
        self.container_layout.insertWidget(self.container_layout.count() - 1, row)
        self._rows[job_id] = row
        self._apply_filter()

    def update_state(self, job_id: str, state: str, message: str = "") -> None:
        row = self._rows.get(job_id)
        if row:
            row.set_state(state, message)
            self._apply_filter()

    def update_progress(self, job_id: str, received: int, total: int) -> None:
        row = self._rows.get(job_id)
        if row:
            row.set_progress(received, total)

    def _on_filter(self, value: str) -> None:
        self._filter = value
        self._apply_filter()

    def _matches(self, row: DownloadRow) -> bool:
        if self._filter == "active":
            return row.state in ACTIVE_STATES
        if self._filter == "done":
            return row.state == "done"
        return True

    def _apply_filter(self) -> None:
        visible = 0
        for row in self._rows.values():
            matched = self._matches(row)
            row.setVisible(matched)
            visible += 1 if matched else 0
        self.stack.setCurrentIndex(0 if visible else 1)

    def active_count(self) -> int:
        return sum(1 for row in self._rows.values() if row.state in ACTIVE_STATES)

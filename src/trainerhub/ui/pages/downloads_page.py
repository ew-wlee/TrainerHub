"""Download centre: one flat line per job with inline progress."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...core.models import CatalogItem
from ...i18n import tr
from ..motion import animations_enabled
from ..widgets.common import ElidedLabel, repolish

ACTIVE_STATES = {"queued", "resolving", "downloading", "extracting", "installing"}


class DownloadRow(QFrame):
    cancel_requested = Signal(str)
    retry_requested = Signal(object)

    def __init__(self, job_id: str, item: CatalogItem, source_name: str, parent=None) -> None:
        super().__init__(parent)
        self.job_id = job_id
        self.item = item
        self.state = "queued"
        self.setObjectName("DownloadRow")
        self.setFixedHeight(56)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 0, 12, 0)
        layout.setSpacing(16)

        self.title = ElidedLabel(item.game_name or item.title, Qt.TextElideMode.ElideRight)
        self.title.setObjectName("RowTitle")

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(200)
        self._progress_animation = QPropertyAnimation(self.progress, b"value", self)
        self._progress_animation.setDuration(150)
        self._progress_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

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

        self.retry_button = QPushButton(tr("action.retry"))
        self.retry_button.setObjectName("GhostButton")
        self.retry_button.clicked.connect(lambda: self.retry_requested.emit(self.item))
        self.retry_button.hide()

        layout.addWidget(self.title, 1)
        layout.addWidget(self.progress)
        layout.addWidget(self.percent)
        layout.addWidget(self.status)
        layout.addWidget(self.cancel_button)
        layout.addWidget(self.retry_button)

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
            self._set_progress_value(1000)
            self.percent.setText("100%")
        elif state in {"failed", "cancelled"}:
            self._progress_animation.stop()
        self.cancel_button.setVisible(state in ACTIVE_STATES)
        self.retry_button.setVisible(state == "failed")
        self.status.setToolTip(message)
        if message:
            self.setToolTip(message)

    def set_progress(self, received: int, total: int) -> None:
        if total > 0:
            value = max(0, min(1000, int(received / total * 1000)))
            self._set_progress_value(value)
            self.percent.setText(f"{value // 10}%")

    def _set_progress_value(self, value: int) -> None:
        self._progress_animation.stop()
        if not animations_enabled() or not self.isVisible() or value < self.progress.value():
            self.progress.setValue(value)
            return
        self._progress_animation.setStartValue(self.progress.value())
        self._progress_animation.setEndValue(value)
        self._progress_animation.start()


class DownloadsPage(QWidget):
    """Temporary active and failed jobs embedded above the installed library."""

    cancel_requested = Signal(str)
    retry_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: dict[str, DownloadRow] = {}
        self._completion_timers: dict[str, QTimer] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 6, 18, 8)
        layout.setSpacing(4)
        title = QLabel(tr("downloads.active.title"))
        title.setObjectName("SectionTitle")
        layout.addWidget(title)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setMaximumHeight(130)
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(0)
        self.container_layout.addStretch(1)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)
        self.hide()

    def add_job(self, job_id: str, item: CatalogItem, source_name: str) -> None:
        if job_id in self._completion_timers:
            self._completion_timers[job_id].stop()
        row = self._rows.get(job_id)
        if row is None:
            row = DownloadRow(job_id, item, source_name)
            row.cancel_requested.connect(self.cancel_requested.emit)
            row.retry_requested.connect(self.retry_requested.emit)
            self.container_layout.insertWidget(self.container_layout.count() - 1, row)
            self._rows[job_id] = row
        else:
            row.item = item
            row.set_state("queued")
            row.set_progress(0, 1)
        self._apply_filter()

    def update_state(self, job_id: str, state: str, message: str = "") -> None:
        row = self._rows.get(job_id)
        if row:
            timer = self._completion_timers.get(job_id)
            if timer:
                timer.stop()
            row.set_state(state, message)
            if state == "done":
                if timer is None:
                    timer = QTimer(self)
                    timer.setSingleShot(True)
                    timer.timeout.connect(lambda current=job_id: self._finish_completion(current))
                    self._completion_timers[job_id] = timer
                timer.start(650)
            self._apply_filter()

    def _finish_completion(self, job_id: str) -> None:
        row = self._rows.get(job_id)
        if row and row.state == "done":
            row.state = "completed"
            self._apply_filter()

    def update_progress(self, job_id: str, received: int, total: int) -> None:
        row = self._rows.get(job_id)
        if row:
            row.set_progress(received, total)

    def _apply_filter(self) -> None:
        visible = 0
        for row in self._rows.values():
            matched = row.state in ACTIVE_STATES or row.state in {"failed", "done"}
            row.setVisible(matched)
            visible += int(matched)
        self.scroll.setFixedHeight(min(visible * 56 + 2, 130))
        self.setVisible(bool(visible))

    def active_count(self) -> int:
        return sum(1 for row in self._rows.values() if row.state in ACTIVE_STATES)

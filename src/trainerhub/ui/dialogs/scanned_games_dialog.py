"""Manage locally discovered games without uploading library information."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...core.models import ScanReport, SteamGame
from ...i18n import tr


class ScannedGamesDialog(QDialog):
    exclusion_changed = Signal(str, bool)
    search_requested = Signal(str)

    def __init__(self, games: list[SteamGame], excluded: set[str], unmatched: list[SteamGame],
                 report: ScanReport | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("discovery.manage"))
        self.resize(560, 420)
        layout = QVBoxLayout(self)
        heading = QLabel(tr("discovery.manage"))
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        self.rows = QVBoxLayout(body)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.checks: dict[str, QCheckBox] = {}
        unmatched_ids = {game.appid for game in unmatched}
        for game in games:
            row = QHBoxLayout()
            label = QLabel(game.name)
            label.setToolTip(game.install_path)
            row.addWidget(label, 1)
            if game.appid in unmatched_ids:
                search = QPushButton(tr("discovery.search"))
                search.setObjectName("LinkButton")
                search.clicked.connect(lambda _=False, name=game.name: self.search_requested.emit(name))
                row.addWidget(search)
            check = QCheckBox(tr("discovery.exclude"))
            check.setChecked(game.appid in excluded)
            check.toggled.connect(lambda checked, appid=game.appid: self.exclusion_changed.emit(appid, checked))
            self.checks[game.appid] = check
            row.addWidget(check)
            self.rows.addLayout(row)
        if report is not None:
            for path, status in report.library_status.items():
                if status not in {"ok", "success", "scanned"}:
                    message = QLabel(f"{path} · {tr('discovery.library.' + status)}")
                    message.setWordWrap(True)
                    message.setObjectName("FieldHint")
                    self.rows.addWidget(message)
        self.rows.addStretch(1)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        close = QPushButton(tr("action.close"))
        close.setObjectName("GhostButton")
        close.clicked.connect(self.accept)
        layout.addWidget(close)

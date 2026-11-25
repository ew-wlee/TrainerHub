"""Right-hand inspector: game, source, one fact, one action."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.models import CatalogItem, InstalledItem
from ...core.textutil import human_size
from ...i18n import tr


class DetailPanel(QWidget):
    download_requested = Signal(object)
    open_page_requested = Signal(object)
    open_folder_requested = Signal(object)
    close_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DetailPanel")
        self.setFixedWidth(280)
        self._item: CatalogItem | None = None
        self._installed: InstalledItem | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 16)
        outer.setSpacing(0)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addStretch(1)
        self.close_button = QPushButton("✕")
        self.close_button.setObjectName("InspectorClose")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setToolTip(tr("detail.close"))
        self.close_button.clicked.connect(self.close_requested.emit)
        head.addWidget(self.close_button)

        self.title = QLabel("")
        self.title.setObjectName("DetailTitle")
        self.title.setWordWrap(True)

        self.source = QLabel("")
        self.source.setObjectName("DetailSource")

        self.note = QLabel("")
        self.note.setObjectName("DetailNote")
        self.note.setWordWrap(True)

        self.primary_button = QPushButton(tr("action.download"))
        self.primary_button.setObjectName("PrimaryButton")
        self.primary_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.primary_button.setMinimumHeight(34)
        self.primary_button.clicked.connect(self._on_primary)

        self.secondary_button = QPushButton(tr("action.open_page"))
        self.secondary_button.setObjectName("LinkButton")
        self.secondary_button.setStyleSheet("text-align: center;")
        self.secondary_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.secondary_button.clicked.connect(self._on_secondary)

        outer.addLayout(head)
        outer.addSpacing(4)
        outer.addWidget(self.title)
        outer.addSpacing(3)
        outer.addWidget(self.source)
        outer.addSpacing(12)
        outer.addWidget(self.note)
        outer.addSpacing(14)
        outer.addWidget(self.primary_button)
        outer.addWidget(self.secondary_button, 0, Qt.AlignmentFlag.AlignLeft)
        outer.addStretch(1)

        self._reset()

    # -- state ------------------------------------------------------------
    def has_item(self) -> bool:
        return self._item is not None

    def _reset(self) -> None:
        self._item = None
        self._installed = None
        self.title.setText("")
        self.source.setText("")
        self.note.setText("")
        self.primary_button.setEnabled(False)
        self.secondary_button.setVisible(False)

    def show_item(
        self,
        item: CatalogItem,
        installed: InstalledItem | None,
        *,
        source_name: str,
        source_supports_direct: bool,
        remote: bool = False,
    ) -> None:
        self._item = item
        self._installed = installed

        self.title.setText(item.game_name or item.title)
        self.source.setText(f"{source_name} · {tr('source.live')}" if remote else source_name)

        if remote:
            self.note.setText(tr("detail.remote_note"))
        elif installed is not None:
            self.note.setText(tr("detail.installed"))
        else:
            facts = []
            if item.options_count:
                facts.append(tr("detail.fact.options", count=item.options_count))
            if item.file_size:
                facts.append(human_size(item.file_size))
            self.note.setText(" · ".join(facts) if facts else tr("detail.fact.unknown"))

        if installed is not None:
            self.primary_button.setText(tr("action.open_folder"))
        elif source_supports_direct:
            self.primary_button.setText(tr("action.download"))
        else:
            self.primary_button.setText(tr("action.open_page"))
        self.primary_button.setEnabled(True)

        # Only show the browser action when the primary action is not already it.
        self.secondary_button.setVisible(installed is not None or (source_supports_direct and not remote))

    def update_installed(self, installed: InstalledItem | None) -> None:
        if self._item is None:
            return
        self._installed = installed
        if installed is not None:
            self.primary_button.setText(tr("action.open_folder"))
            self.note.setText(tr("detail.installed"))

    # -- actions ----------------------------------------------------------
    def _on_primary(self) -> None:
        if self._item is None:
            return
        if self._installed is not None:
            self.open_folder_requested.emit(self._installed)
        elif not self._item.supports_direct_download:
            self.open_page_requested.emit(self._item)
        else:
            self.download_requested.emit(self._item)

    def _on_secondary(self) -> None:
        if self._item is not None:
            self.open_page_requested.emit(self._item)

"""Left navigation rail: three pages and the source filters. No counts."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from ...i18n import tr
from .common import repolish

NAV_ITEMS = (
    ("discover", "nav.discover"),
    ("downloads", "nav.downloads"),
    ("library", "nav.library"),
)


class SourceRail(QWidget):
    navigate = Signal(str)
    source_changed = Signal(str)

    def __init__(self, sources: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SideRail")
        self.setFixedWidth(188)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 10)
        layout.setSpacing(1)

        self._nav_buttons: dict[str, QPushButton] = {}
        for key, label_key in NAV_ITEMS:
            button = QPushButton(tr(label_key))
            button.setObjectName("NavButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, page=key: self.navigate.emit(page))
            layout.addWidget(button)
            self._nav_buttons[key] = button

        layout.addSpacing(14)
        section = QLabel(tr("nav.section.sources"))
        section.setObjectName("NavSection")
        layout.addWidget(section)

        self._source_buttons: dict[str, QPushButton] = {}
        self._add_source_button("all", tr("source.all"))
        for source_id, display in sources.items():
            self._add_source_button(source_id, display)

        layout.addStretch(1)

        self.set_active_page("discover")
        self.set_active_source("all")

    def _add_source_button(self, source_id: str, display: str) -> None:
        button = QPushButton(display)
        button.setObjectName("SourceButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda _=False, sid=source_id: self._on_source(sid))
        self.layout().addWidget(button)
        self._source_buttons[source_id] = button

    # -- state ------------------------------------------------------------
    def set_active_page(self, page: str) -> None:
        for key, button in self._nav_buttons.items():
            button.setProperty("active", "true" if key == page else "false")
            repolish(button)

    def set_active_source(self, source_id: str) -> None:
        for key, button in self._source_buttons.items():
            button.setProperty("active", "true" if key == source_id else "false")
            repolish(button)

    def _on_source(self, source_id: str) -> None:
        self.set_active_source(source_id)
        self.source_changed.emit(source_id)

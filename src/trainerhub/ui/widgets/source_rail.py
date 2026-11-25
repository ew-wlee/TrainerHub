"""Left navigation rail: pages, source filters, library footer."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QPixmap
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from ... import APP_NAME, VERSION
from ...core.paths import resource_path
from ...i18n import tr
from .common import repolish

NAV_ITEMS = (
    ("discover", "nav.discover", "◈"),
    ("downloads", "nav.downloads", "↓"),
    ("library", "nav.library", "▤"),
    ("settings", "nav.settings", "⚙"),
)


class SourceRail(QWidget):
    navigate = Signal(str)
    source_changed = Signal(str)

    def __init__(self, sources: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SideRail")
        self.setFixedWidth(216)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 16, 10, 12)
        layout.setSpacing(2)

        brand_row = QWidget()
        brand_layout = QVBoxLayout(brand_row)
        brand_layout.setContentsMargins(8, 0, 8, 12)
        brand_layout.setSpacing(2)

        logo = QLabel()
        logo.setPixmap(self._logo())
        logo.setFixedSize(34, 34)
        name = QLabel(APP_NAME)
        name.setObjectName("BrandName")
        tag = QLabel(tr("app.tagline"))
        tag.setObjectName("BrandTag")
        tag.setWordWrap(True)

        from PySide6.QtWidgets import QHBoxLayout

        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(logo)
        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        text_col.addWidget(name)
        top.addLayout(text_col)
        top.addStretch(1)

        brand_layout.addLayout(top)
        brand_layout.addWidget(tag)
        layout.addWidget(brand_row)

        self._nav_buttons: dict[str, QPushButton] = {}
        for key, label_key, glyph in NAV_ITEMS:
            button = QPushButton(f"  {glyph}   {tr(label_key)}")
            button.setObjectName("NavButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setCheckable(False)
            button.clicked.connect(lambda _=False, page=key: self.navigate.emit(page))
            layout.addWidget(button)
            self._nav_buttons[key] = button

        section = QLabel(tr("nav.section.sources"))
        section.setObjectName("NavSection")
        layout.addWidget(section)

        self._source_buttons: dict[str, QPushButton] = {}
        self._add_source_button("all", tr("source.all"))
        for source_id, display in sources.items():
            self._add_source_button(source_id, display)

        layout.addStretch(1)

        self.footer = QLabel("")
        self.footer.setObjectName("RailFooter")
        self.footer.setWordWrap(False)
        layout.addWidget(self.footer)

        version = QLabel(f"v{VERSION}")
        version.setObjectName("RailFooter")
        layout.addWidget(version)

        self.set_active_page("discover")
        self.set_active_source("all")

    def _add_source_button(self, source_id: str, display: str) -> None:
        button = QPushButton(display)
        button.setObjectName("SourceButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda _=False, sid=source_id: self._on_source(sid))
        self.layout().addWidget(button)
        self._source_buttons[source_id] = button

    @staticmethod
    def _logo() -> QPixmap:
        path = resource_path("resources", "app_icon.svg")
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            pixmap = QPixmap(QSize(34, 34))
            pixmap.fill(Qt.GlobalColor.transparent)
            return pixmap
        return pixmap.scaled(
            34, 34, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )

    # -- state ------------------------------------------------------------
    def set_active_page(self, page: str) -> None:
        for key, button in self._nav_buttons.items():
            button.setProperty("active", "true" if key == page else "false")
            repolish(button)

    def set_active_source(self, source_id: str) -> None:
        for key, button in self._source_buttons.items():
            button.setProperty("active", "true" if key == source_id else "false")
            repolish(button)

    def set_counts(self, counts: dict[str, int]) -> None:
        total = sum(counts.values())
        for source_id, button in self._source_buttons.items():
            if source_id == "all":
                label = tr("source.all")
                count = total
            else:
                label = button.text().split("  (")[0]
                count = counts.get(source_id, 0)
            button.setText(f"{label}  ({count})" if count else label)

    def set_footer(self, text: str) -> None:
        metrics = QFontMetrics(self.footer.font())
        self.footer.setText(metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, 186))
        self.footer.setToolTip(text)

    def _on_source(self, source_id: str) -> None:
        self.set_active_source(source_id)
        self.source_changed.emit(source_id)

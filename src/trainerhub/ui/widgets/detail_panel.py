"""Right-hand detail panel: cover, metadata, option list, primary action."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...core.models import CatalogItem, InstalledItem
from ...core.textutil import human_size
from ...i18n import tr
from .. import theme as theme_tokens
from .common import Badge, NoticeBox


class CoverBanner(QWidget):
    """Gradient plate with the game's initials — no network image needed."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._title = ""
        self.theme = "dark"

    def set_title(self, title: str) -> None:
        self._title = title
        self.update()

    def set_theme(self, theme: str) -> None:
        self.theme = theme
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(320, 120)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()

        base = QColor(theme_tokens.token(self.theme, "primary"))
        accent = QColor(theme_tokens.token(self.theme, "success"))
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        base.setAlpha(46)
        accent.setAlpha(20)
        gradient.setColorAt(0.0, base)
        gradient.setColorAt(1.0, accent)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(rect, 10, 10)

        painter.setPen(QColor(255, 255, 255, 26))
        for offset in range(-rect.height(), rect.width(), 22):
            painter.drawLine(rect.left() + offset, rect.bottom(), rect.left() + offset + rect.height(), rect.top())

        initials = "".join(word[0] for word in self._title.split()[:2] if word).upper() or "T"
        if any("\u4e00" <= char <= "\u9fff" for char in self._title[:2]):
            initials = self._title[:2]

        # Monogram watermark rather than a centred avatar: it reads as texture
        # behind the rows instead of looking like a missing cover image.
        font = QFont(self.font())
        font.setPointSize(56)
        font.setWeight(QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        painter.setFont(font)
        painter.setPen(QColor(230, 234, 242, 34))
        painter.drawText(
            rect.adjusted(0, 0, -18, 6),
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom),
            initials,
        )
        painter.end()


class DetailPanel(QWidget):
    download_requested = Signal(object)
    open_page_requested = Signal(object)
    open_folder_requested = Signal(object)
    run_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DetailPanel")
        self.setMinimumWidth(320)
        self.theme = "dark"
        self._item: CatalogItem | None = None
        self._installed: InstalledItem | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 16)
        outer.setSpacing(12)

        self.cover = CoverBanner()
        self.title = QLabel(tr("detail.placeholder"))
        self.title.setObjectName("DetailTitle")
        self.title.setWordWrap(True)
        self.alias = QLabel("")
        self.alias.setObjectName("DetailAlias")
        self.alias.setWordWrap(True)

        self.badges = QHBoxLayout()
        self.badges.setSpacing(6)
        self.source_badge = Badge("", "primary")
        self.mode_badge = Badge("", "success")
        self.badges.addWidget(self.source_badge)
        self.badges.addWidget(self.mode_badge)
        self.badges.addStretch(1)

        self.meta_box = QFrame()
        self.meta_box.setObjectName("Card")
        self.meta_layout = QVBoxLayout(self.meta_box)
        self.meta_layout.setContentsMargins(14, 12, 14, 12)
        self.meta_layout.setSpacing(7)
        self._meta_values: dict[str, QLabel] = {}
        for key in ("version", "game_version", "file_size", "updated", "source"):
            row = QHBoxLayout()
            row.setSpacing(10)
            label = QLabel(tr(f"detail.{key}"))
            label.setObjectName("MetaKey")
            label.setFixedWidth(64)
            value = QLabel("—")
            value.setObjectName("MetaValue")
            value.setWordWrap(True)
            row.addWidget(label)
            row.addWidget(value, 1)
            self.meta_layout.addLayout(row)
            self._meta_values[key] = value

        self.options_title = QLabel(tr("detail.options"))
        self.options_title.setObjectName("SectionTitle")
        self.options_title.setVisible(False)

        # A QFrame owns the border: QSS borders on a scroll area are not part of
        # the viewport rect, which makes content paint over its own frame.
        self.options_frame = QFrame()
        self.options_frame.setObjectName("OptionFrame")
        self.options_frame.setVisible(False)
        self.options_frame.setMinimumHeight(120)
        self.options_frame.setMaximumHeight(380)
        frame_layout = QVBoxLayout(self.options_frame)
        frame_layout.setContentsMargins(8, 8, 4, 8)

        self.options_area = QPlainTextEdit()
        self.options_area.setObjectName("OptionText")
        self.options_area.setReadOnly(True)
        self.options_area.setFrameShape(QPlainTextEdit.Shape.NoFrame)
        self.options_area.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.options_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.options_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.options_area.setFont(theme_tokens.mono_font(10))
        self.options_area.setStyleSheet("background: transparent; border: none;")
        self.options_area.document().setDocumentMargin(2)
        self.options_area.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        frame_layout.addWidget(self.options_area)

        self.notice = NoticeBox("")
        self.notice.setVisible(False)

        self.primary_button = QPushButton(tr("action.download"))
        self.primary_button.setObjectName("PrimaryButton")
        self.primary_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.primary_button.setMinimumHeight(38)
        self.primary_button.clicked.connect(self._on_primary)
        self.primary_button.setEnabled(False)

        self.secondary_button = QPushButton(tr("action.open_page"))
        self.secondary_button.setObjectName("GhostButton")
        self.secondary_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.secondary_button.clicked.connect(self._on_secondary)
        self.secondary_button.setVisible(False)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(self.primary_button, 1)
        actions.addWidget(self.secondary_button)

        outer.addWidget(self.cover)
        outer.addWidget(self.title)
        outer.addWidget(self.alias)
        outer.addLayout(self.badges)
        outer.addWidget(self.meta_box)
        outer.addWidget(self.options_title)
        outer.addWidget(self.options_frame, 1)
        outer.addWidget(self.notice)
        outer.addLayout(actions)

        self._show_placeholder()

    # -- theming ----------------------------------------------------------
    def set_theme(self, theme: str) -> None:
        self.theme = theme
        self.cover.set_theme(theme)

    def _show_placeholder(self) -> None:
        self.cover.set_title("")
        self.alias.setText("")
        self.meta_box.setVisible(False)
        self.options_title.setVisible(False)
        self.options_frame.setVisible(False)
        self.notice.setVisible(False)
        self.secondary_button.setVisible(False)
        self.primary_button.setEnabled(False)
        self.primary_button.setText(tr("action.download"))
        self.source_badge.setVisible(False)
        self.mode_badge.setVisible(False)
        self._item = None
        self._installed = None

    # -- content ----------------------------------------------------------
    def show_item(
        self,
        item: CatalogItem,
        installed: InstalledItem | None,
        *,
        source_name: str,
        source_supports_direct: bool,
    ) -> None:
        self._item = item
        self._installed = installed
        self.cover.set_title(item.game_name or item.title)
        self.title.setText(item.game_name or item.title)
        self.alias.setText(item.game_alias)
        self.alias.setVisible(bool(item.game_alias))

        self.source_badge.setText(source_name)
        self.source_badge.setVisible(True)
        self.mode_badge.setText(tr("source.direct") if source_supports_direct else tr("source.external"))
        self.mode_badge.set_level("success" if source_supports_direct else "warn")
        self.mode_badge.setVisible(True)

        self.meta_box.setVisible(True)
        self._meta_values["version"].setText(item.version or "—")
        self._meta_values["game_version"].setText(item.game_version or "—")
        self._meta_values["file_size"].setText(human_size(item.file_size))
        self._meta_values["updated"].setText(item.updated_at or "—")
        self._meta_values["source"].setText(source_name)

        self.options_area.setPlainText("\n".join(item.options))
        if item.options:
            self.options_title.setText(f"{tr('detail.options')}  ·  {len(item.options)}")
            self.options_title.setVisible(True)
            self.options_frame.setVisible(True)
        else:
            self.options_title.setVisible(False)
            self.options_frame.setVisible(False)

        if installed is not None:
            self.primary_button.setText(tr("action.open_folder"))
            self.notice.setText(tr("detail.installed") + f" · {installed.version or '—'}")
            self.notice.setObjectName("AccentNotice")
            self.notice.setVisible(True)
        elif not source_supports_direct:
            self.primary_button.setText(tr("action.open_page"))
            self.notice.setText(tr("detail.external_hint"))
            self.notice.setStyleSheet("")
            self.notice.setObjectName("NoticeBox")
            self.notice.setVisible(True)
        else:
            self.primary_button.setText(tr("action.download"))
            self.notice.setVisible(False)

        self.notice.style().unpolish(self.notice)
        self.notice.style().polish(self.notice)

        self.primary_button.setEnabled(True)
        # Only offer the secondary browser action when the primary one is not
        # already "open the page".
        self.secondary_button.setVisible(installed is not None or source_supports_direct)
        self.secondary_button.setText(tr("action.open_page"))

    def update_installed(self, installed: InstalledItem | None) -> None:
        if self._item is None:
            return
        if installed is not None:
            self._installed = installed
            self.primary_button.setText(tr("action.open_folder"))
            self.notice.setText(tr("detail.installed") + f" · {installed.version or '—'}")
            self.notice.setObjectName("AccentNotice")
            self.notice.setVisible(True)
            self.notice.style().unpolish(self.notice)
            self.notice.style().polish(self.notice)

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

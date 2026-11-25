"""Small reusable widgets: badges, empty states, stat cards, notices."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


def repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


class Badge(QLabel):
    def __init__(self, text: str = "", level: str = "primary", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("Badge")
        self.setProperty("level", level)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

    def setText(self, text: str) -> None:  # noqa: N802
        super().setText(text)
        # QSS padding is applied after the first sizeHint, so reserve room here.
        width = self.fontMetrics().horizontalAdvance(text) + 18
        self.setMinimumWidth(max(28, width))

    def set_level(self, level: str) -> None:
        self.setProperty("level", level)
        repolish(self)


class ElidedLabel(QLabel):
    """Single-line label that shortens itself instead of being clipped mid-word."""

    def __init__(
        self,
        text: str = "",
        mode: Qt.TextElideMode = Qt.TextElideMode.ElideMiddle,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._full_text = text
        self._mode = mode
        self.setToolTip(text)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._apply(text)

    def setText(self, text: str) -> None:  # noqa: N802
        self._full_text = text
        self.setToolTip(text)
        self._apply(text)

    def resizeEvent(self, event) -> None:  # noqa: ANN001 - Qt signature
        super().resizeEvent(event)
        self._apply(self._full_text)

    def _apply(self, text: str) -> None:
        available = self.width()
        if available <= 0:
            super().setText(text)
            return
        super().setText(self.fontMetrics().elidedText(text, self._mode, available))


class NoticeBox(QLabel):
    def __init__(self, text: str = "", *, accent: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("AccentNotice" if accent else "NoticeBox")
        self.setWordWrap(True)


class EmptyState(QWidget):
    def __init__(
        self,
        title: str = "",
        body: str = "",
        action: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 40, 32, 40)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.glyph = QLabel("◈")
        self.glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        glyph_font = QFont()
        glyph_font.setPointSize(30)
        self.glyph.setFont(glyph_font)
        self.glyph.setStyleSheet("color: rgba(78, 140, 255, 0.55);")

        self.title = QLabel(title)
        self.title.setObjectName("EmptyTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.body = QLabel(body)
        self.body.setObjectName("EmptyBody")
        self.body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body.setWordWrap(True)
        self.body.setMaximumWidth(380)

        self.action = QPushButton(action)
        self.action.setObjectName("GhostButton")
        self.action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action.setVisible(bool(action))

        layout.addWidget(self.glyph, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.title)
        layout.addWidget(self.body, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(6)
        layout.addWidget(self.action, 0, Qt.AlignmentFlag.AlignHCenter)

    def set_text(self, title: str, body: str = "", action: str = "") -> None:
        self.title.setText(title)
        self.body.setText(body)
        self.action.setText(action)
        self.action.setVisible(bool(action))


class StatCard(QFrame):
    def __init__(self, label: str, value: str = "—", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("StatValue")
        self.label = QLabel(label)
        self.label.setObjectName("StatLabel")
        layout.addWidget(self.value_label)
        layout.addWidget(self.label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class SectionTitle(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("SectionTitle")


class Divider(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Divider")
        self.setFixedHeight(1)


class HeaderBar(QWidget):
    """Title + subtitle on the left, optional actions on the right."""

    def __init__(self, title: str = "", subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 10)
        layout.setSpacing(12)

        text_column = QVBoxLayout()
        text_column.setSpacing(2)
        self.title = QLabel(title)
        self.title.setObjectName("PageTitle")
        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("PageSubtitle")
        text_column.addWidget(self.title)
        text_column.addWidget(self.subtitle)

        layout.addLayout(text_column)
        layout.addStretch(1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        layout.addLayout(self.actions)

    def add_action(self, widget: QWidget) -> None:
        self.actions.addWidget(widget)

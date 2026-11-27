"""A native, keyboard-accessible switch whose value changes only after commit."""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton

from ..motion import animations_enabled
from ..theme import token


class ModSwitch(QAbstractButton):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(46, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._position = 0.0
        self.animation = QPropertyAnimation(self, b"position", self)
        self.animation.setDuration(140)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _get_position(self) -> float:
        return self._position

    def _set_position(self, value: float) -> None:
        self._position = value
        self.update()

    position = Property(float, _get_position, _set_position)

    def nextCheckState(self) -> None:  # noqa: N802
        # QAbstractButton emits clicked but must not optimistically change truth.
        pass

    def setChecked(self, checked: bool) -> None:  # noqa: N802
        super().setChecked(checked)
        self.animation.stop()
        target = 1.0 if checked else 0.0
        if animations_enabled() and self.isVisible() and self._position != target:
            self.animation.setStartValue(self._position)
            self.animation.setEndValue(target)
            self.animation.start()
        else:
            self._set_position(target)

    def hideEvent(self, event) -> None:  # noqa: N802
        self.animation.stop()
        self._set_position(1.0 if self.isChecked() else 0.0)
        super().hideEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(1.0 if self.isEnabled() else 0.45)
        track = QColor(token("light", "primary" if self.isChecked() else "line_strong"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(QRectF(2, 3, 42, 22), 11, 11)
        painter.setBrush(QColor(token("light", "surface")))
        painter.drawEllipse(QRectF(5 + 20 * self._position, 6, 16, 16))
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(token("light", "primary")), 1.5))
            painter.drawRoundedRect(QRectF(0.75, 1.75, 44.5, 24.5), 12, 12)

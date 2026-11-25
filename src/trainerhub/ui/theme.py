"""Design tokens and QSS loading.

v0.2 is a single light theme: warm paper, white surfaces, hairlines, black
actions. The dict shape is kept so a dark palette can be added later without
touching every widget.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from ..core.paths import resource_path

TOKENS: dict[str, dict[str, str]] = {
    "light": {
        "bg": "#FAF8F4",
        "surface": "#FFFFFF",
        "elevated": "#FFFFFF",
        "hover": "#F6F3EC",
        "sunken": "#EFEBE2",
        "line": "#E7E2D8",
        "line_strong": "#D6D0C4",
        "text": "#191817",
        "muted": "#4E4B45",
        "dim": "#6F6B62",
        "primary": "#191817",
        "primary_deep": "#2C2A26",
        "primary_soft": "#EFEBE2",
        "success": "#2E6B4E",
        "success_soft": "#E9F0EA",
        "warn": "#8A5A12",
        "warn_soft": "#F6EDDF",
        "danger": "#A63A2C",
        "danger_soft": "#F7E9E6",
        "shadow": "rgba(25, 24, 23, 0.18)",
        "skeleton": "#F1EDE4",
    },
}

BODY_FAMILIES = [
    "SF Pro Text",
    "Segoe UI Variable Text",
    "Segoe UI",
    "PingFang SC",
    "Microsoft YaHei UI",
    "Noto Sans CJK SC",
    "Sans Serif",
]
MONO_FAMILIES = ["SF Mono", "Cascadia Mono", "Consolas", "Menlo", "monospace"]

ROW_HEIGHT = 56
INSPECTOR_WIDTH = 280
RAIL_WIDTH = 188


def token(theme: str, name: str) -> str:
    return TOKENS["light"].get(name, "#000000")


def color(theme: str, name: str) -> QColor:
    return QColor(token(theme, name))


def pick_family(candidates: list[str]) -> str:
    available = set(QFontDatabase.families())
    for family in candidates:
        if family in available:
            return family
    return candidates[-1]


def build_font(point_size: int = 10, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont(pick_family(BODY_FAMILIES), point_size)
    font.setWeight(weight)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return font


def mono_font(point_size: int = 10) -> QFont:
    font = QFont(pick_family(MONO_FAMILIES), point_size)
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


def stylesheet(theme: str = "light") -> str:
    path: Path = resource_path("ui", "qss", "app.qss")
    try:
        template = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    # Longest key first, otherwise "@primary" eats the "@primary_soft" prefix.
    for name, value in sorted(TOKENS["light"].items(), key=lambda kv: -len(kv[0])):
        template = template.replace(f"@{name}", value)
    template = template.replace("@body_font", pick_family(BODY_FAMILIES))
    template = template.replace("@mono_font", pick_family(MONO_FAMILIES))
    return template


def apply(app: QApplication, theme: str = "light") -> None:
    app.setFont(build_font())
    app.setStyleSheet(stylesheet("light"))

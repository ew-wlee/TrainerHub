"""Design tokens and QSS loading.

One token table feeds both the Qt stylesheet and the painted list delegate, so
colours never drift between "styled widgets" and "custom painted widgets".
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from ..core.paths import resource_path

TOKENS: dict[str, dict[str, str]] = {
    "dark": {
        "bg": "#0E1116",
        "surface": "#151A21",
        "elevated": "#1C232C",
        "hover": "#232B36",
        "line": "rgba(255, 255, 255, 0.07)",
        "line_strong": "rgba(255, 255, 255, 0.14)",
        "text": "#E6EAF2",
        "muted": "#98A2B3",
        "dim": "#5C6672",
        "primary": "#4E8CFF",
        "primary_deep": "#3A6FE0",
        "primary_soft": "rgba(78, 140, 255, 0.16)",
        "success": "#2DD4BF",
        "success_soft": "rgba(45, 212, 191, 0.14)",
        "warn": "#F5A524",
        "warn_soft": "rgba(245, 165, 36, 0.14)",
        "danger": "#F0483E",
        "danger_soft": "rgba(240, 72, 62, 0.14)",
        "shadow": "rgba(0, 0, 0, 0.45)",
        "skeleton": "rgba(255, 255, 255, 0.04)",
    },
    "light": {
        "bg": "#F5F7FA",
        "surface": "#FFFFFF",
        "elevated": "#FFFFFF",
        "hover": "#EEF2F8",
        "line": "rgba(16, 24, 40, 0.08)",
        "line_strong": "rgba(16, 24, 40, 0.16)",
        "text": "#101828",
        "muted": "#5C6672",
        "dim": "#98A2B3",
        "primary": "#3A6FE0",
        "primary_deep": "#2C57B8",
        "primary_soft": "rgba(58, 111, 224, 0.10)",
        "success": "#0FA396",
        "success_soft": "rgba(15, 163, 150, 0.10)",
        "warn": "#B54708",
        "warn_soft": "rgba(181, 71, 8, 0.10)",
        "danger": "#D92D20",
        "danger_soft": "rgba(217, 45, 32, 0.10)",
        "shadow": "rgba(16, 24, 40, 0.08)",
        "skeleton": "rgba(16, 24, 40, 0.04)",
    },
}

BODY_FAMILIES = ["Microsoft YaHei UI", "Segoe UI", "PingFang SC", "Noto Sans CJK SC", "Sans Serif"]
MONO_FAMILIES = ["Cascadia Mono", "Consolas", "SF Mono", "Menlo", "monospace"]


def token(theme: str, name: str) -> str:
    return TOKENS.get(theme, TOKENS["dark"]).get(name, "#000000")


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


def stylesheet(theme: str) -> str:
    path: Path = resource_path("ui", "qss", "app.qss")
    try:
        template = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    # Longest key first, otherwise "@primary" eats the "@primary_soft" prefix.
    for name, value in sorted(TOKENS.get(theme, TOKENS["dark"]).items(), key=lambda kv: -len(kv[0])):
        template = template.replace(f"@{name}", value)
    template = template.replace("@body_font", pick_family(BODY_FAMILIES))
    template = template.replace("@mono_font", pick_family(MONO_FAMILIES))
    return template


def apply(app: QApplication, theme: str) -> None:
    app.setFont(build_font())
    app.setStyleSheet(stylesheet(theme))

"""Tiny JSON-backed translation table (no Qt dependency)."""

from __future__ import annotations

import json
from functools import lru_cache

from ..core.paths import resource_path

SUPPORTED = ("zh_CN", "en_US")
_LANGUAGE = "zh_CN"


@lru_cache(maxsize=4)
def _table(language: str) -> dict[str, str]:
    path = resource_path("i18n", f"{language}.json")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def set_language(language: str) -> None:
    global _LANGUAGE
    _LANGUAGE = language if language in SUPPORTED else "zh_CN"


def get_language() -> str:
    return _LANGUAGE


def tr(key: str, **kwargs: object) -> str:
    text = _table(_LANGUAGE).get(key) or _table("zh_CN").get(key) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text

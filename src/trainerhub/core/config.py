"""User configuration: defaults, dotted access and atomic persistence."""

from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .paths import config_file, default_library_dir

CONFIG_VERSION = 1

DEFAULT_SOURCES: dict[str, dict[str, Any]] = {
    "fling": {
        "display_name": "FLiNG Trainer",
        "base_url": "https://flingtrainer.com",
        "enabled": True,
    },
    "xiaoxing": {
        "display_name": "小幸修改器",
        "base_url": "https://www.xiaoxingjie.com",
        "enabled": True,
    },
    "custom": {
        "display_name": "自定义源",
        "index_url": "",
        "enabled": False,
    },
}

DEFAULTS: dict[str, Any] = {
    "version": CONFIG_VERSION,
    "first_run": True,
    "theme": "dark",
    "language": "zh_CN",
    "library_dir": "",
    "sources": DEFAULT_SOURCES,
    "download": {
        "concurrency": 2,
        "timeout": 20,
        "max_retries": 2,
        "auto_update_trainers": True,
        "auto_update_data": False,
        "open_folder_after_download": False,
    },
    "safety": {
        "disclaimer_accepted": False,
        "defender_exclusion_added": False,
    },
    "ui": {
        "window_geometry": "",
        "window_state": "",
        "last_source": "all",
        "detail_width": 380,
        "sync_on_start": True,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class Config:
    """Thin dict wrapper that keeps dotted paths readable at call sites."""

    def __init__(self, path: Path | None = None, data: dict[str, Any] | None = None) -> None:
        self.path = Path(path) if path else config_file()
        self._data = _deep_merge(DEFAULTS, data or {})
        if not self._data.get("library_dir"):
            self._data["library_dir"] = str(default_library_dir())

    # -- io ---------------------------------------------------------------
    @classmethod
    def load(cls, path: Path | None = None) -> Config:
        target = Path(path) if path else config_file()
        data: dict[str, Any] = {}
        if target.exists():
            try:
                data = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
        config = cls(target, data)
        config._migrate()
        return config

    def _migrate(self) -> None:
        if self._data.get("version", 0) < CONFIG_VERSION:
            self._data["version"] = CONFIG_VERSION
        sources = self._data.setdefault("sources", {})
        for key, value in DEFAULT_SOURCES.items():
            sources.setdefault(key, copy.deepcopy(value))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._data, indent=2, ensure_ascii=False)
        handle, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(payload)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    # -- access -----------------------------------------------------------
    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value: Any, *, save: bool = True) -> None:
        parts = dotted.split(".")
        node = self._data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
        if save:
            self.save()

    def as_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)

    # -- shortcuts --------------------------------------------------------
    @property
    def theme(self) -> str:
        return self.get("theme", "dark")

    @property
    def language(self) -> str:
        return self.get("language", "zh_CN")

    @property
    def library_dir(self) -> Path:
        return Path(self.get("library_dir") or default_library_dir())

    @property
    def enabled_sources(self) -> list[str]:
        sources = self.get("sources", {}) or {}
        return [key for key, value in sources.items() if value.get("enabled")]

    def source_enabled(self, source_id: str) -> bool:
        return bool(self.get(f"sources.{source_id}.enabled", False))

    def source_base_url(self, source_id: str) -> str:
        return str(self.get(f"sources.{source_id}.base_url", "")).rstrip("/")

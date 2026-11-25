"""Filesystem locations used by the application (config, cache, logs, library)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from platformdirs import user_cache_dir, user_config_dir, user_log_dir

APP_DIR_NAME = "TrainerHub"
APP_AUTHOR = "ew-wlee"


def config_dir() -> Path:
    path = Path(user_config_dir(APP_DIR_NAME, APP_AUTHOR))
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir() -> Path:
    path = Path(user_cache_dir(APP_DIR_NAME, APP_AUTHOR))
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    path = Path(user_log_dir(APP_DIR_NAME, APP_AUTHOR))
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_file() -> Path:
    return config_dir() / "config.json"


def database_file() -> Path:
    return cache_dir() / "catalog.db"


def default_library_dir() -> Path:
    """Default place where downloaded trainers are unpacked and archived."""
    home = Path.home()
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA")
        root = Path(base) if base else home / "AppData" / "Local"
        return root / APP_DIR_NAME / "Library"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / APP_DIR_NAME / "Library"
    return home / ".local" / "share" / APP_DIR_NAME / "Library"


def resource_path(*parts: str) -> Path:
    """Resolve a bundled resource, both from source and from a PyInstaller bundle."""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        candidate = Path(bundle) / "trainerhub" / Path(*parts)
        if candidate.exists():
            return candidate
        return Path(bundle) / Path(*parts)
    return Path(__file__).resolve().parent.parent / Path(*parts)


def ensure_dir(path: Path | str) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p

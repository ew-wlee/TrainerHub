"""Local trainer library: layout, install, import, delete."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from .db import Database
from .models import CatalogItem, InstalledItem
from .textutil import safe_folder_name

MANIFEST_NAME = "manifest.json"


def open_in_file_manager(path: Path) -> bool:
    """Reveal a path with the platform file manager. Returns success."""
    target = str(path)
    if not Path(target).exists():
        return False
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", target])  # noqa: S603,S607
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])  # noqa: S603,S607
        else:
            subprocess.Popen(["xdg-open", target])  # noqa: S603,S607
    except OSError:
        return False
    return True


def _dir_size(path: Path) -> int:
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except OSError:
                continue
    return total


class LibraryService:
    def __init__(self, root: Path, db: Database) -> None:
        self.root = Path(root)
        self.db = db

    # -- layout -----------------------------------------------------------
    def target_dir(self, item: CatalogItem) -> Path:
        source = safe_folder_name(item.source_id, "local")
        game = safe_folder_name(item.game_name or item.title, "Unknown Game")
        version = safe_folder_name(item.version or "unversioned", "unversioned")
        return self.root / source / game / version

    def ensure_root(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    # -- state ------------------------------------------------------------
    def installed(self, item: CatalogItem) -> InstalledItem | None:
        return self.db.installed_get(item.source_id, item.remote_id)

    def is_same_version_installed(self, item: CatalogItem) -> bool:
        record = self.installed(item)
        if not record:
            return False
        return (record.version or "") == (item.version or "")

    # -- install ----------------------------------------------------------
    def install(
        self,
        item: CatalogItem,
        files: Sequence[Path],
        *,
        source_name: str = "",
    ) -> InstalledItem:
        dest = self.target_dir(item)
        dest.mkdir(parents=True, exist_ok=True)

        moved: list[str] = []
        for file in files:
            source_path = Path(file)
            if not source_path.exists():
                continue
            target = dest / source_path.name
            if source_path.resolve() == target.resolve():
                moved.append(target.name)
                continue
            if target.exists():
                target.unlink()
            shutil.move(str(source_path), str(target))
            moved.append(target.name)

        if not moved:
            raise RuntimeError("nothing to install")

        size = _dir_size(dest)
        manifest = {
            "app": "TrainerHub",
            "source": item.source_id,
            "source_name": source_name,
            "remote_id": item.remote_id,
            "game_name": item.game_name,
            "title": item.title,
            "version": item.version,
            "page_url": item.page_url,
            "options_count": item.options_count,
            "installed_at": datetime.now().isoformat(timespec="seconds"),
            "files": moved,
        }
        (dest / MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        record = InstalledItem(
            source_id=item.source_id,
            remote_id=item.remote_id,
            game_name=item.game_name,
            version=item.version,
            path=str(dest),
            size_bytes=size,
            options_count=item.options_count,
            page_url=item.page_url,
            installed_at=manifest["installed_at"],
        )
        self.db.installed_upsert(record)
        return record

    def delete(self, record: InstalledItem, *, remove_files: bool = True) -> None:
        if remove_files:
            path = Path(record.path)
            if path.exists() and path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
        self.db.installed_delete(record.source_id, record.remote_id)

    # -- import -----------------------------------------------------------
    def import_folder(self, folder: Path) -> InstalledItem:
        """Register an existing trainer folder as a local library entry."""
        directory = Path(folder)
        if not directory.is_dir():
            raise NotADirectoryError(str(directory))
        remote_id = hashlib.sha1(str(directory.resolve()).encode("utf-8")).hexdigest()[:16]
        size = _dir_size(directory)
        record = InstalledItem(
            source_id="local",
            remote_id=remote_id,
            game_name=directory.name,
            version="",
            path=str(directory),
            size_bytes=size,
            options_count=0,
            page_url="",
            installed_at=datetime.now().isoformat(timespec="seconds"),
        )
        self.db.installed_upsert(record)
        return record

    def import_tree(self, folder: Path) -> list[InstalledItem]:
        """Import every immediate sub-folder of *folder* that looks useful."""
        root = Path(folder)
        records: list[InstalledItem] = []
        if not root.exists():
            return records
        candidates = [child for child in sorted(root.iterdir()) if child.is_dir()]
        if not candidates:
            candidates = [root]
        for child in candidates:
            if child.name.startswith("."):
                continue
            try:
                records.append(self.import_folder(child))
            except (OSError, ValueError):
                continue
        return records

    def total_bytes(self) -> int:
        return sum(record.size_bytes for record in self.db.installed_all())

from __future__ import annotations

import json
from pathlib import Path

from trainerhub.core.db import Database
from trainerhub.core.library import MANIFEST_NAME, LibraryService
from trainerhub.core.models import CatalogItem


def _item(version: str = "Plus 11") -> CatalogItem:
    return CatalogItem(
        source_id="fling",
        remote_id="1",
        title="Elden Ring Trainer",
        game_name="Elden Ring",
        version=version,
        page_url="https://example.test/trainer/1/",
        options_count=3,
    )


def test_install_creates_layout_and_manifest(tmp_path: Path, db: Database) -> None:
    service = LibraryService(tmp_path / "library", db)
    source = tmp_path / "download.exe"
    source.write_bytes(b"MZ" * 100)

    record = service.install(_item(), [source], source_name="FLiNG")

    expected = tmp_path / "library" / "fling" / "Elden Ring" / "Plus 11"
    assert Path(record.path) == expected
    assert (expected / "download.exe").exists()
    manifest = json.loads((expected / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["version"] == "Plus 11"
    assert manifest["source_name"] == "FLiNG"
    assert record.size_bytes == 200
    assert service.is_same_version_installed(_item())


def test_new_version_lands_in_its_own_folder(tmp_path: Path, db: Database) -> None:
    service = LibraryService(tmp_path / "library", db)
    first = tmp_path / "a.exe"
    first.write_bytes(b"MZ")
    service.install(_item("Plus 11"), [first])
    assert not service.is_same_version_installed(_item("Plus 12"))

    second = tmp_path / "b.exe"
    second.write_bytes(b"MZ")
    record = service.install(_item("Plus 12"), [second])
    assert record.path.endswith("Plus 12")


def test_delete_removes_files_and_record(tmp_path: Path, db: Database) -> None:
    service = LibraryService(tmp_path / "library", db)
    source = tmp_path / "a.exe"
    source.write_bytes(b"MZ")
    record = service.install(_item(), [source])
    service.delete(record)
    assert not Path(record.path).exists()
    assert db.installed_all() == []


def test_import_tree_registers_subfolders(tmp_path: Path, db: Database) -> None:
    root = tmp_path / "external"
    for name in ("Game A", "Game B"):
        folder = root / name
        folder.mkdir(parents=True)
        (folder / "trainer.exe").write_bytes(b"MZ" * 10)
    service = LibraryService(tmp_path / "library", db)
    records = service.import_tree(root)
    assert {record.game_name for record in records} == {"Game A", "Game B"}
    assert all(record.source_id == "local" for record in records)

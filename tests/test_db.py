from __future__ import annotations

from trainerhub.core.db import Database
from trainerhub.core.models import CatalogItem, InstalledItem


def test_upsert_is_idempotent(db: Database) -> None:
    item = CatalogItem(source_id="fling", remote_id="1", title="A Trainer", game_name="A")
    assert db.upsert_items([item]) == 1
    assert db.upsert_items([item]) == 1
    assert db.item_count() == 1


def test_save_detail_persists_version_and_options(db: Database) -> None:
    item = CatalogItem(source_id="fling", remote_id="1", title="A Trainer", game_name="A")
    db.upsert_items([item])
    detailed = item.clone(
        version="Plus 11", options=("Num 1 - Health",), options_count=1, detail_loaded=True
    )
    db.save_detail(detailed)
    stored = db.get_item("fling", "1")
    assert stored is not None
    assert stored.version == "Plus 11"
    assert stored.options == ("Num 1 - Health",)


def test_list_sync_does_not_erase_known_version(db: Database) -> None:
    item = CatalogItem(source_id="fling", remote_id="1", title="A Trainer", game_name="A")
    db.upsert_items([item])
    db.save_detail(item.clone(version="Plus 11", detail_loaded=True))
    # A later list sync carries no version - it must not wipe the detail one.
    db.upsert_items(
        [CatalogItem(source_id="fling", remote_id="1", title="A Trainer", game_name="A", version="")]
    )
    stored = db.get_item("fling", "1")
    assert stored is not None and stored.version == "Plus 11"


def test_detail_rows_from_list_payload_are_persisted(db: Database) -> None:
    item = CatalogItem(
        source_id="xiaoxing",
        remote_id="65",
        title="黑神话：悟空 多功能修改器 V1.7.0",
        game_name="黑神话：悟空",
        version="v1.7.0",
        options=("无限生命(Alt+1)",),
        options_count=1,
        detail_loaded=True,
    )
    db.upsert_items([item])
    stored = db.get_item("xiaoxing", "65")
    assert stored is not None
    assert stored.options == ("无限生命(Alt+1)",)
    assert db.count_by_source() == {"xiaoxing": 1}


def test_installed_roundtrip(db: Database) -> None:
    record = InstalledItem(
        source_id="fling",
        remote_id="1",
        game_name="A",
        version="Plus 1",
        path="/tmp/a",
        size_bytes=10,
    )
    db.installed_upsert(record)
    records = db.installed_all()
    assert len(records) == 1
    assert records[0].version == "Plus 1"
    db.installed_delete("fling", "1")
    assert db.installed_all() == []

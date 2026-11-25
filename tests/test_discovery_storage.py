from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from trainerhub.core.config import DEFAULTS, Config
from trainerhub.core.db import Database
from trainerhub.core.models import (
    CatalogItem,
    GameMatch,
    InstalledItem,
    RecommendationEntry,
    RecommendationPlan,
    ScanReport,
    SteamGame,
)

LIBRARY_A = "/steam/main"
LIBRARY_B = "/steam/external"
SCANNED_AT = "2026-11-25T10:00:00+00:00"


def game(appid: str = "10", library: str = LIBRARY_A, **changes: object) -> SteamGame:
    values = {
        "appid": appid,
        "name": f"Game {appid}",
        "library_path": library,
        "install_path": f"{library}/steamapps/common/Game {appid}",
    }
    values.update(changes)
    return SteamGame(**values)


def scan(*games: SteamGame, **changes: object) -> ScanReport:
    values = {
        "games": list(games),
        "library_status": {record.library_path: "ok" for record in games},
        "scanned_at": SCANNED_AT,
    }
    values.update(changes)
    return ScanReport(**values)


def discovery_meta(db: Database) -> dict[str, str]:
    return {
        key: db.meta_get(f"discovery.{key}")
        for key in ("scanned_at", "library_status", "skipped", "snapshot_version")
    }


def test_discovery_models_have_independent_defaults_and_slots() -> None:
    first, second = ScanReport(), ScanReport()
    first.games.append(game())
    first.library_status[LIBRARY_A] = "ok"
    first.skipped.append("invalid_manifest")
    assert second.games == []
    assert second.library_status == {}
    assert second.skipped == []
    assert not second.cancelled

    item = CatalogItem("fling", "10", "Game 10 Trainer", "Game 10")
    record = game()
    match = GameMatch(record, item, "high", "exact_name")
    entry = RecommendationEntry(record, item, "high", "exact_name")
    plan, other = RecommendationPlan(), RecommendationPlan()
    plan.entries.append(entry)
    plan.unmatched.append(record)
    assert other.entries == []
    assert other.unmatched == []
    assert other.generation == 0
    assert other.generated_at == other.snapshot_version == ""
    assert entry.selected and entry.state == "ready" and entry.action == "download"
    assert record.state_flags == 4 and record.build_id == record.scanned_at == ""
    assert match.game is record and match.item is item
    for model in (record, first, match, entry, plan):
        assert not hasattr(model, "__dict__")


def test_scan_and_preferences_survive_reopening(tmp_path: Path) -> None:
    path = tmp_path / "discovery.db"
    record = game(name="中文 Game '10'", state_flags=6, build_id="123", scanned_at=SCANNED_AT)
    db = Database(path)
    try:
        db.save_steam_scan(scan(record, skipped=["invalid_manifest"]))
        db.set_steam_excluded("10", True)
        version = db.meta_get("discovery.snapshot_version")
    finally:
        db.close()

    reopened = Database(path)
    try:
        assert reopened.steam_games() == [record]
        assert reopened.steam_excluded() == {"10"}
        assert reopened.meta_get("discovery.scanned_at") == SCANNED_AT
        assert json.loads(reopened.meta_get("discovery.library_status")) == {LIBRARY_A: "ok"}
        assert json.loads(reopened.meta_get("discovery.skipped")) == ["invalid_manifest"]
        assert reopened.meta_get("discovery.snapshot_version") == version != ""
    finally:
        reopened.close()


def test_duplicate_games_and_repeated_scans_are_idempotent(db: Database) -> None:
    report = scan(game(name="Old name"), game(name="Updated name"))
    db.save_steam_scan(report)
    first_version = db.meta_get("discovery.snapshot_version")
    db.save_steam_scan(report)
    assert len(db.steam_games()) == 1
    assert db.steam_games()[0].name == "Updated name"
    assert db.steam_games()[0].scanned_at == SCANNED_AT
    assert db.meta_get("discovery.snapshot_version") != first_version


def test_cross_library_duplicates_do_not_destroy_unavailable_snapshot(db: Database) -> None:
    db.save_steam_scan(scan(game(library=LIBRARY_B)))
    db.save_steam_scan(
        scan(
            game(),
            library_status={LIBRARY_A: "ok", LIBRARY_B: "unavailable"},
            scanned_at="2026-11-25T11:00:00+00:00",
        )
    )
    assert len(db.steam_games()) == 1
    assert db.steam_games()[0].library_path == LIBRARY_A
    db.save_steam_scan(scan(library_status={LIBRARY_A: "ok", LIBRARY_B: "unavailable"}))
    assert len(db.steam_games()) == 1
    assert db.steam_games()[0].library_path == LIBRARY_B


@pytest.mark.parametrize("status", ["unavailable", "invalid"])
def test_failed_and_unmentioned_libraries_keep_previous_games(db: Database, status: str) -> None:
    db.save_steam_scan(scan(game(), game("20", LIBRARY_B), game("30", "/steam/omitted")))
    db.save_steam_scan(
        scan(game("40"), game("99", LIBRARY_B), library_status={LIBRARY_A: "ok", LIBRARY_B: status})
    )
    assert [record.appid for record in db.steam_games()] == ["20", "30", "40"]
    assert json.loads(db.meta_get("discovery.library_status"))[LIBRARY_B] == status


def test_pure_failure_updates_status_without_changing_snapshot_version(db: Database) -> None:
    db.save_steam_scan(scan(game()))
    previous = db.steam_games()
    version = db.meta_get("discovery.snapshot_version")
    db.save_steam_scan(
        scan(library_status={LIBRARY_A: "unavailable"}, scanned_at="2026-11-25T12:00:00+00:00")
    )
    assert db.steam_games() == previous
    assert db.meta_get("discovery.snapshot_version") == version
    assert db.meta_get("discovery.scanned_at") == "2026-11-25T12:00:00+00:00"


def test_successful_empty_library_clears_only_that_library(db: Database) -> None:
    db.save_steam_scan(scan(game(), game("20", LIBRARY_B)))
    db.save_steam_scan(scan(library_status={LIBRARY_A: "ok"}))
    assert [record.appid for record in db.steam_games()] == ["20"]


def test_unreported_games_are_not_saved(db: Database) -> None:
    db.save_steam_scan(scan(game(), library_status={}))
    assert db.steam_games() == []
    assert db.meta_get("discovery.snapshot_version") == ""


def test_cancelled_scan_changes_nothing(db: Database) -> None:
    db.save_steam_scan(scan(game()))
    db.set_steam_excluded("10", True)
    previous_games, previous_meta = db.steam_games(), discovery_meta(db)
    db.save_steam_scan(
        scan(game("20"), cancelled=True, library_status={LIBRARY_A: "unknown"}, scanned_at="later")
    )
    assert db.steam_games() == previous_games
    assert discovery_meta(db) == previous_meta
    assert db.steam_excluded() == {"10"}


def test_first_cancelled_scan_writes_no_metadata(db: Database) -> None:
    db.save_steam_scan(scan(game(), cancelled=True))
    assert db.steam_games() == []
    assert all(value == "" for value in discovery_meta(db).values())


def test_invalid_library_status_is_rejected_without_writes(db: Database) -> None:
    db.save_steam_scan(scan(game()))
    previous_games, previous_meta = db.steam_games(), discovery_meta(db)
    with pytest.raises(ValueError, match="Invalid Steam library scan status"):
        db.save_steam_scan(scan(game("20"), library_status={LIBRARY_A: "unknown"}))
    assert db.steam_games() == previous_games
    assert discovery_meta(db) == previous_meta


def test_scan_insert_failure_rolls_back_games_and_metadata(db: Database) -> None:
    db.save_steam_scan(scan(game(), game("30", LIBRARY_B)))
    previous_games, previous_meta = db.steam_games(), discovery_meta(db)
    db._conn.execute(
        "CREATE TRIGGER fail_scan BEFORE INSERT ON steam_games WHEN NEW.appid='20' "
        "BEGIN SELECT RAISE(ABORT, 'scan insert failure'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="scan insert failure"):
        db.save_steam_scan(scan(game("40"), game("20"), game("50", LIBRARY_B)))
    assert not db._conn.in_transaction
    assert db.steam_games() == previous_games
    assert discovery_meta(db) == previous_meta
    db._conn.execute("DROP TRIGGER fail_scan")
    db.save_steam_scan(scan(game("20")))
    assert [record.appid for record in db.steam_games()] == ["20", "30"]


def test_scan_metadata_failure_rolls_back_new_snapshot(db: Database) -> None:
    db.save_steam_scan(scan(game()))
    previous_games, previous_meta = db.steam_games(), discovery_meta(db)
    db._conn.execute(
        "CREATE TRIGGER fail_scan_meta BEFORE INSERT ON meta "
        "WHEN NEW.key='discovery.snapshot_version' "
        "BEGIN SELECT RAISE(ABORT, 'scan metadata failure'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="scan metadata failure"):
        db.save_steam_scan(scan(game("20"), scanned_at="later"))
    assert not db._conn.in_transaction
    assert db.steam_games() == previous_games
    assert discovery_meta(db) == previous_meta


def test_exclusion_is_idempotent_and_can_be_removed(db: Database) -> None:
    db.set_steam_excluded("10", True)
    db.set_steam_excluded("10", True)
    db.set_steam_excluded("20", True)
    assert db.steam_excluded() == {"10", "20"}
    db.set_steam_excluded("10", False)
    db.set_steam_excluded("missing", False)
    assert db.steam_excluded() == {"20"}


def test_clear_discovery_preserves_catalog_installed_and_other_meta(db: Database) -> None:
    item = CatalogItem("fling", "10", "Game 10 Trainer", "Game 10")
    installed = InstalledItem("fling", "10", "Game 10", "1.0", "/trainers/game10")
    db.upsert_items([item])
    db.installed_upsert(installed)
    db.meta_set("sync.fling", "complete")
    db.meta_set("discovery", "not-prefixed")
    db.save_steam_scan(scan(game()))
    db.set_steam_excluded("10", True)
    db.clear_discovery()
    db.clear_discovery()
    assert db.steam_games() == []
    assert db.steam_excluded() == set()
    assert all(value == "" for value in discovery_meta(db).values())
    assert db.all_items() == [item]
    assert db.installed_all() == [installed]
    assert db.meta_get("sync.fling") == "complete"
    assert db.meta_get("discovery") == "not-prefixed"


def test_clear_discovery_failure_rolls_back_all_tables(db: Database) -> None:
    db.save_steam_scan(scan(game()))
    db.set_steam_excluded("10", True)
    previous_games, previous_meta = db.steam_games(), discovery_meta(db)
    db._conn.execute(
        "CREATE TRIGGER fail_clear BEFORE DELETE ON meta WHEN OLD.key GLOB 'discovery.*' "
        "BEGIN SELECT RAISE(ABORT, 'clear failure'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="clear failure"):
        db.clear_discovery()
    assert not db._conn.in_transaction
    assert db.steam_games() == previous_games
    assert db.steam_excluded() == {"10"}
    assert discovery_meta(db) == previous_meta


def test_discovery_defaults_are_disabled_and_independent(tmp_path: Path) -> None:
    first = Config(tmp_path / "first.json")
    second = Config(tmp_path / "second.json")
    assert first.get("discovery") == {"enabled": False, "scan_on_start": False, "steam_paths": []}
    first.get("discovery.steam_paths").append(LIBRARY_A)
    assert second.get("discovery.steam_paths") == []
    assert DEFAULTS["discovery"]["steam_paths"] == []


def test_old_config_deep_merges_discovery_and_preserves_existing_settings(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"theme": "dark", "sources": {"fling": {"enabled": False}}, "ui": {"sync_on_start": False}}),
        encoding="utf-8",
    )
    config = Config.load(path)
    assert config.theme == "dark"
    assert not config.source_enabled("fling")
    assert config.source_enabled("xiaoxing")
    assert not config.get("ui.sync_on_start")
    assert config.get("discovery") == DEFAULTS["discovery"]


def test_partial_discovery_config_roundtrip_deep_merges_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    config = Config(path, {"discovery": {"enabled": True, "steam_paths": [LIBRARY_A]}})
    assert config.get("discovery.scan_on_start") is False
    config.save()
    loaded = Config.load(path)
    assert loaded.get("discovery") == {"enabled": True, "scan_on_start": False, "steam_paths": [LIBRARY_A]}
    assert loaded.get("download.concurrency") == 2

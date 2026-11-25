"""SQLite persistence for the catalogue and the installed library."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .models import CatalogItem, InstalledItem, ScanReport, SteamGame

SCHEMA = """
CREATE TABLE IF NOT EXISTS catalog (
    source_id               TEXT NOT NULL,
    remote_id               TEXT NOT NULL,
    title                   TEXT NOT NULL DEFAULT '',
    game_name               TEXT NOT NULL DEFAULT '',
    game_alias              TEXT NOT NULL DEFAULT '',
    version                 TEXT NOT NULL DEFAULT '',
    page_url                TEXT NOT NULL DEFAULT '',
    image_url               TEXT NOT NULL DEFAULT '',
    options_count           INTEGER NOT NULL DEFAULT 0,
    game_version            TEXT NOT NULL DEFAULT '',
    file_size               INTEGER NOT NULL DEFAULT 0,
    updated_at              TEXT NOT NULL DEFAULT '',
    published_at            TEXT NOT NULL DEFAULT '',
    summary                 TEXT NOT NULL DEFAULT '',
    options_json            TEXT NOT NULL DEFAULT '[]',
    supports_direct_download INTEGER NOT NULL DEFAULT 0,
    detail_loaded           INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (source_id, remote_id)
);
CREATE INDEX IF NOT EXISTS idx_catalog_updated ON catalog(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_catalog_source  ON catalog(source_id);

CREATE TABLE IF NOT EXISTS installed (
    source_id     TEXT NOT NULL,
    remote_id     TEXT NOT NULL,
    game_name     TEXT NOT NULL DEFAULT '',
    version       TEXT NOT NULL DEFAULT '',
    path          TEXT NOT NULL DEFAULT '',
    size_bytes    INTEGER NOT NULL DEFAULT 0,
    options_count INTEGER NOT NULL DEFAULT 0,
    page_url      TEXT NOT NULL DEFAULT '',
    installed_at  TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (source_id, remote_id)
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS steam_games (
    appid        TEXT NOT NULL,
    name         TEXT NOT NULL DEFAULT '',
    library_path TEXT NOT NULL,
    install_path TEXT NOT NULL DEFAULT '',
    state_flags  INTEGER NOT NULL DEFAULT 4,
    build_id     TEXT NOT NULL DEFAULT '',
    scanned_at   TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (library_path, appid)
);
CREATE INDEX IF NOT EXISTS idx_steam_games_appid ON steam_games(appid);

CREATE TABLE IF NOT EXISTS steam_preferences (
    appid    TEXT PRIMARY KEY,
    excluded INTEGER NOT NULL DEFAULT 0
);
"""

_LIST_COLUMNS = (
    "source_id",
    "remote_id",
    "title",
    "game_name",
    "game_alias",
    "version",
    "page_url",
    "published_at",
    "updated_at",
    "summary",
)

_DETAIL_COLUMNS = (
    "image_url",
    "options_count",
    "game_version",
    "file_size",
    "options_json",
    "supports_direct_download",
    "detail_loaded",
)


class Database:
    """Small thread-safe wrapper around a single SQLite connection."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.commit()

    # -- catalogue --------------------------------------------------------
    def upsert_items(self, items: Iterable[CatalogItem]) -> int:
        rows = []
        detailed: list[tuple[tuple, str, str]] = []
        for item in items:
            row = item.to_row()
            rows.append(tuple(row[column] for column in _LIST_COLUMNS))
            if item.detail_loaded:
                # Sources that ship full content in the list payload (小幸) must
                # persist their detail columns too, otherwise options are lost.
                detailed.append(
                    (tuple(row[column] for column in _DETAIL_COLUMNS), item.source_id, item.remote_id)
                )
        if not rows:
            return 0
        placeholders = ", ".join("?" for _ in _LIST_COLUMNS)
        # `version` is usually only known after the detail pass, so a later list
        # sync must not clobber it with an empty value.
        assignments = ", ".join(
            f"{column}=CASE WHEN excluded.{column}='' THEN catalog.{column} ELSE excluded.{column} END"
            if column == "version"
            else f"{column}=excluded.{column}"
            for column in _LIST_COLUMNS
            if column not in ("source_id", "remote_id")
        )
        sql = (
            f"INSERT INTO catalog ({', '.join(_LIST_COLUMNS)}) VALUES ({placeholders}) "
            f"ON CONFLICT(source_id, remote_id) DO UPDATE SET {assignments}"
        )
        with self._lock:
            self._conn.executemany(sql, rows)
            if detailed:
                assignments = ", ".join(f"{column}=?" for column in _DETAIL_COLUMNS)
                self._conn.executemany(
                    f"UPDATE catalog SET {assignments} WHERE source_id=? AND remote_id=?",
                    [(*values, source_id, remote_id) for values, source_id, remote_id in detailed],
                )
            self._conn.commit()
        return len(rows)

    def save_detail(self, item: CatalogItem) -> None:
        row = item.to_row()
        values = tuple(row[column] for column in _DETAIL_COLUMNS)
        assignments = ", ".join(f"{column}=?" for column in _DETAIL_COLUMNS)
        # `version` is often only discoverable from the detail page, so fold it
        # into this update without letting an empty value wipe a known one.
        sql = (
            f"UPDATE catalog SET version=CASE WHEN ?='' THEN version ELSE ? END, "
            f"{assignments} WHERE source_id=? AND remote_id=?"
        )
        with self._lock:
            self._conn.execute(
                sql, (item.version, item.version, *values, item.source_id, item.remote_id)
            )
            self._conn.commit()

    def all_items(self) -> list[CatalogItem]:
        with self._lock:
            cursor = self._conn.execute("SELECT * FROM catalog ORDER BY updated_at DESC")
            return [CatalogItem.from_row(dict(row)) for row in cursor.fetchall()]

    def get_item(self, source_id: str, remote_id: str) -> CatalogItem | None:
        with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM catalog WHERE source_id=? AND remote_id=?", (source_id, remote_id)
            )
            row = cursor.fetchone()
        return CatalogItem.from_row(dict(row)) if row else None

    def count_by_source(self) -> dict[str, int]:
        with self._lock:
            cursor = self._conn.execute("SELECT source_id, COUNT(*) AS n FROM catalog GROUP BY source_id")
            return {row["source_id"]: int(row["n"]) for row in cursor.fetchall()}

    def delete_source(self, source_id: str) -> int:
        with self._lock:
            cursor = self._conn.execute("DELETE FROM catalog WHERE source_id=?", (source_id,))
            self._conn.commit()
            return cursor.rowcount or 0

    def item_count(self) -> int:
        with self._lock:
            cursor = self._conn.execute("SELECT COUNT(*) FROM catalog")
            return int(cursor.fetchone()[0])

    # -- installed library ------------------------------------------------
    def installed_all(self) -> list[InstalledItem]:
        with self._lock:
            cursor = self._conn.execute("SELECT * FROM installed ORDER BY installed_at DESC")
            return [InstalledItem(**dict(row)) for row in cursor.fetchall()]

    def installed_get(self, source_id: str, remote_id: str) -> InstalledItem | None:
        with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM installed WHERE source_id=? AND remote_id=?", (source_id, remote_id)
            )
            row = cursor.fetchone()
        return InstalledItem(**dict(row)) if row else None

    def installed_upsert(self, record: InstalledItem) -> None:
        if not record.installed_at:
            record.installed_at = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            self._conn.execute(
                "INSERT INTO installed (source_id, remote_id, game_name, version, path, size_bytes,"
                " options_count, page_url, installed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(source_id, remote_id) DO UPDATE SET game_name=excluded.game_name,"
                " version=excluded.version, path=excluded.path, size_bytes=excluded.size_bytes,"
                " options_count=excluded.options_count, page_url=excluded.page_url,"
                " installed_at=excluded.installed_at",
                (
                    record.source_id,
                    record.remote_id,
                    record.game_name,
                    record.version,
                    record.path,
                    int(record.size_bytes),
                    int(record.options_count),
                    record.page_url,
                    record.installed_at,
                ),
            )
            self._conn.commit()

    def installed_delete(self, source_id: str, remote_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM installed WHERE source_id=? AND remote_id=?", (source_id, remote_id)
            )
            self._conn.commit()

    # -- Steam discovery --------------------------------------------------
    def steam_games(self) -> list[SteamGame]:
        """Return one game per appid without discarding its other library snapshots."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM steam_games ORDER BY scanned_at DESC, library_path, appid"
            ).fetchall()
        games: dict[str, SteamGame] = {}
        for row in rows:
            games.setdefault(row["appid"], SteamGame(**dict(row)))
        return [games[appid] for appid in sorted(games)]

    def save_steam_scan(self, report: ScanReport) -> None:
        """Atomically replace only complete libraries; cancellation never writes."""
        if report.cancelled:
            return
        if any(status not in {"ok", "unavailable", "invalid"} for status in report.library_status.values()):
            raise ValueError("Invalid Steam library scan status")
        successful = {path for path, status in report.library_status.items() if status == "ok"}
        scanned_at = report.scanned_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows: dict[tuple[str, str], tuple] = {}
        for game in report.games:
            if game.library_path not in successful:
                continue
            rows[(game.library_path, game.appid)] = (
                game.appid,
                game.name,
                game.library_path,
                game.install_path,
                int(game.state_flags),
                game.build_id,
                game.scanned_at or scanned_at,
            )
        metadata = [
            ("discovery.scanned_at", scanned_at),
            ("discovery.library_status", json.dumps(report.library_status, ensure_ascii=False)),
            ("discovery.skipped", json.dumps(report.skipped, ensure_ascii=False)),
        ]
        if successful:
            metadata.append(("discovery.snapshot_version", uuid4().hex))
        # The connection context rolls back deletes, inserts and metadata together.
        with self._lock, self._conn:
            self._conn.executemany(
                "DELETE FROM steam_games WHERE library_path=?", [(path,) for path in successful]
            )
            self._conn.executemany(
                "INSERT INTO steam_games (appid, name, library_path, install_path, state_flags,"
                " build_id, scanned_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows.values(),
            )
            self._conn.executemany(
                "INSERT INTO meta (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                metadata,
            )

    def steam_excluded(self) -> set[str]:
        with self._lock:
            rows = self._conn.execute("SELECT appid FROM steam_preferences WHERE excluded=1").fetchall()
        return {row["appid"] for row in rows}

    def set_steam_excluded(self, appid: str, excluded: bool) -> None:
        with self._lock, self._conn:
            if excluded:
                self._conn.execute(
                    "INSERT INTO steam_preferences (appid, excluded) VALUES (?, 1)"
                    " ON CONFLICT(appid) DO UPDATE SET excluded=1",
                    (appid,),
                )
            else:
                self._conn.execute("DELETE FROM steam_preferences WHERE appid=?", (appid,))

    def clear_discovery(self) -> None:
        """Forget discovery data without touching catalogue or installed trainers."""
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM steam_games")
            self._conn.execute("DELETE FROM steam_preferences")
            self._conn.execute("DELETE FROM meta WHERE key GLOB 'discovery.*'")

    # -- meta -------------------------------------------------------------
    def meta_get(self, key: str, default: str = "") -> str:
        with self._lock:
            cursor = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,))
            row = cursor.fetchone()
        return str(row["value"]) if row else default

    def meta_set(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

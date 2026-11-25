from __future__ import annotations

import json
import sys
import types
from contextlib import closing
from pathlib import Path

import pytest

from trainerhub.core import steam_scan
from trainerhub.core.steam_scan import VDFError, discover_steam_paths, parse_vdf, scan_steam

_STATES = json.loads((Path(__file__).parent / "fixtures/discovery_cases.json").read_text(encoding="utf-8"))["manifest_states"]


def library(path: Path) -> Path:
    (path / "steamapps/common").mkdir(parents=True)
    return path


def manifest(
    root: Path,
    appid: str = "123",
    name: str = "Hades",
    directory: str = "Hades",
    flags: int = 4,
    *,
    filename_id: str | None = None,
    make_install: bool = True,
) -> Path:
    if make_install:
        (root / "steamapps/common" / directory).mkdir(parents=True, exist_ok=True)
    path = root / "steamapps" / f"appmanifest_{filename_id or appid}.acf"
    path.write_text(
        json.dumps("AppState")
        + "\n{\n"
        + "\n".join(
            f"{json.dumps(key)} {json.dumps(str(value))}"
            for key, value in {
                "appid": appid,
                "name": name,
                "installdir": directory,
                "StateFlags": flags,
                "buildid": "987",
            }.items()
        )
        + "\n}",
        encoding="utf-8",
    )
    return path


def folders(root: Path, paths: list[Path], old_format: bool = False) -> None:
    values = []
    for index, path in enumerate(paths):
        if old_format:
            values.append(f'"{index}" {json.dumps(str(path))}')
        else:
            values.append(f'"{index}" {{ "path" {json.dumps(str(path))} "apps" {{ "123" "100" }} }}')
    (root / "steamapps/libraryfolders.vdf").write_text('"libraryfolders" {\n' + "\n".join(values) + "\n}")


def test_vdf_quotes_escapes_comments_and_nested_objects():
    parsed = parse_vdf(
        '\ufeff// outside\n"Root" { /* inside */ "path" "C:\\\\Games\\\\Steam" "name" "A \\"quoted\\" game // literal" "nested" { "key" "value" } }'
    )
    assert parsed["root"]["path"] == r"C:\Games\Steam"
    assert parsed["root"]["name"] == 'A "quoted" game // literal'
    assert parsed["root"]["nested"] == {"key": "value"}


def test_vdf_unknown_escape_preserves_windows_path():
    assert parse_vdf('"path" "C:\\Games"')["path"] == r"C:\Games"


@pytest.mark.parametrize(
    "text",
    [
        '"root" {',
        '"root" }',
        '"root" { "a" }',
        '"unclosed',
        "/* unclosed",
        '"a" "1" "A" "2"',
        '{ "a" "1" }',
        "}",
    ],
)
def test_malformed_vdf_is_rejected(text):
    with pytest.raises(VDFError):
        parse_vdf(text)


def test_vdf_depth_size_and_token_limits(monkeypatch):
    with pytest.raises(VDFError):
        parse_vdf('"a" {' * 33 + '"b" "c"' + "}" * 33)
    monkeypatch.setattr(steam_scan, "MAX_VDF_BYTES", 20)
    with pytest.raises(VDFError):
        parse_vdf('"x" "' + "y" * 30 + '"')
    monkeypatch.setattr(steam_scan, "MAX_VDF_BYTES", 1000)
    monkeypatch.setattr(steam_scan, "MAX_VDF_TOKENS", 2)
    with pytest.raises(VDFError):
        parse_vdf('"a" "b" "c" "d"')


@pytest.mark.parametrize("old_format", [False, True])
def test_multiple_libraries_and_manual_steamapps_path(tmp_path, old_format):
    first, second = library(tmp_path / "Steam"), library(tmp_path / "Other")
    manifest(first)
    manifest(second, "456", "Control", "Control")
    folders(first, [first, second], old_format)
    report = scan_steam([str(first / "steamapps")])
    assert {game.appid for game in report.games} == {"123", "456"}
    assert report.library_status == {str(first): "ok", str(second): "ok"}
    assert all(game.scanned_at == report.scanned_at and game.build_id == "987" for game in report.games)


@pytest.mark.parametrize("row", _STATES, ids=lambda row: str(row["flags"]))
def test_installed_state_flags(tmp_path, row):
    root = library(tmp_path / "Steam")
    manifest(root, flags=row["flags"])
    report = scan_steam([str(root)])
    assert bool(report.games) == row["installed"]


def test_bad_manifest_does_not_block_valid_game(tmp_path):
    root = library(tmp_path / "Steam")
    manifest(root)
    (root / "steamapps/appmanifest_456.acf").write_text('"AppState" {')
    manifest(root, "789", "Control", "Control", filename_id="999")
    report = scan_steam([str(root)])
    assert [game.appid for game in report.games] == ["123"] and len(report.skipped) == 2


@pytest.mark.parametrize(
    "directory",
    [
        "../escape",
        "..",
        ".",
        "/tmp/escape",
        "C:\\outside",
        "sub/game",
        "sub\\game",
        "game\x00",
        " trailing",
        "trailing.",
    ],
)
def test_unsafe_installdir_rejected(tmp_path, directory):
    root = library(tmp_path / "Steam")
    manifest(root, directory=directory, make_install=False)
    assert scan_steam([str(root)]).games == []


def test_missing_install_and_symlink_escape_rejected(tmp_path):
    root = library(tmp_path / "Steam")
    manifest(root, make_install=False)
    assert not scan_steam([str(root)]).games
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "steamapps/common/Hades").symlink_to(outside, target_is_directory=True)
    assert not scan_steam([str(root)]).games


def test_symlink_manifest_outside_library_rejected(tmp_path):
    root, other = library(tmp_path / "Steam"), library(tmp_path / "Other")
    external = manifest(other)
    (root / "steamapps/appmanifest_123.acf").symlink_to(external)
    assert not scan_steam([str(root)]).games


def test_library_status_unavailable_and_invalid(tmp_path):
    root, missing = library(tmp_path / "Steam"), tmp_path / "Missing"
    (root / "steamapps/libraryfolders.vdf").write_text('"libraryfolders" {')
    report = scan_steam([str(root), str(missing)])
    assert report.library_status == {str(root): "invalid", str(missing): "unavailable"}


def test_unavailable_linked_library_reported(tmp_path):
    root, missing = library(tmp_path / "Steam"), tmp_path / "offline"
    folders(root, [missing])
    assert scan_steam([str(root)]).library_status[str(missing)] == "unavailable"


def test_cancel_discards_partial_results(tmp_path):
    root = library(tmp_path / "Steam")
    manifest(root)
    manifest(root, "456", "Control", "Control")
    checks = 0

    def cancelled():
        nonlocal checks
        checks += 1
        return checks >= 3

    report = scan_steam([str(root)], cancelled)
    assert report.cancelled and report.games == []


def test_duplicate_paths_are_deduplicated_but_per_library_snapshots_are_preserved(tmp_path):
    from trainerhub.core.db import Database

    first, second = library(tmp_path / "Steam"), library(tmp_path / "Other")
    manifest(first)
    manifest(second)
    report = scan_steam([str(first), str(first / "steamapps"), str(second)])
    assert len(report.games) == 2
    with closing(Database(tmp_path / "catalog.db")) as db:
        db.save_steam_scan(report)
        assert len(db.steam_games()) == 1
        db._conn.execute("DELETE FROM steam_games WHERE library_path=?", (str(first),))
        db._conn.commit()
        assert db.steam_games()[0].library_path == str(second)


def test_transient_manifest_failure_keeps_previous_snapshot(tmp_path):
    from trainerhub.core.db import Database

    root = library(tmp_path / "Steam")
    metadata = manifest(root)
    with closing(Database(tmp_path / "catalog.db")) as db:
        db.save_steam_scan(scan_steam([str(root)]))
        metadata.write_text('"AppState" {', encoding="utf-8")
        report = scan_steam([str(root)])
        assert report.library_status[str(root)] == "invalid"
        db.save_steam_scan(report)
        assert db.steam_games()[0].appid == "123"


def test_confirmed_uninstalled_manifest_removes_previous_snapshot(tmp_path):
    from trainerhub.core.db import Database

    root = library(tmp_path / "Steam")
    manifest(root)
    with closing(Database(tmp_path / "catalog.db")) as db:
        db.save_steam_scan(scan_steam([str(root)]))
        manifest(root, flags=0)
        report = scan_steam([str(root)])
        assert report.library_status[str(root)] == "ok"
        db.save_steam_scan(report)
        assert db.steam_games() == []


def test_scanner_does_not_open_game_content_or_write_metadata(tmp_path, monkeypatch):
    root = library(tmp_path / "Steam")
    metadata = manifest(root)
    binary = root / "steamapps/common/Hades/Hades.exe"
    binary.write_bytes(b"game content")
    before = metadata.read_bytes()
    original = Path.open
    opened = []

    def checked_open(path, mode="r", *args, **kwargs):
        opened.append((path, mode))
        assert path.name == "libraryfolders.vdf" or path.name.startswith("appmanifest_")
        assert mode == "rb"
        return original(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", checked_open)
    assert scan_steam([str(root)]).games
    monkeypatch.setattr(Path, "open", original)
    assert metadata.read_bytes() == before and len(opened) == 1


@pytest.mark.parametrize(
    "platform,relative",
    [
        ("darwin", "Library/Application Support/Steam"),
        ("linux", ".local/share/Steam"),
        ("linux", ".steam/steam"),
        ("linux", ".var/app/com.valvesoftware.Steam/.local/share/Steam"),
    ],
)
def test_platform_default_discovery(tmp_path, monkeypatch, platform, relative):
    root = library(tmp_path / relative)
    monkeypatch.setattr(steam_scan.sys, "platform", platform)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert str(root) in discover_steam_paths()


def test_windows_registry_read_only_discovery(tmp_path, monkeypatch):
    root = library(tmp_path / "Steam")
    access = []

    class Handle:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    def open_key(hive, key, reserved, mode):
        access.append(mode)
        return Handle()

    registry = types.SimpleNamespace(
        HKEY_CURRENT_USER=1,
        HKEY_LOCAL_MACHINE=2,
        KEY_READ=7,
        OpenKey=open_key,
        QueryValueEx=lambda handle, name: (str(root), 1),
    )
    monkeypatch.setitem(sys.modules, "winreg", registry)
    monkeypatch.setattr(steam_scan.sys, "platform", "win32")
    assert str(root) in discover_steam_paths()
    assert access == [registry.KEY_READ] * 3


def test_empty_paths_disable_automatic_discovery():
    assert scan_steam([]).games == []


def test_automatic_scan_uses_discovered_roots(tmp_path, monkeypatch):
    root = library(tmp_path / "Steam")
    manifest(root)
    monkeypatch.setattr(steam_scan, "discover_steam_paths", lambda: [str(root)])
    assert scan_steam().games[0].appid == "123"


def test_unreadable_library_is_unavailable(tmp_path, monkeypatch):
    root = library(tmp_path / "Steam")
    original = steam_scan.os.scandir

    def denied(path):
        if Path(path) == root / "steamapps":
            raise PermissionError("Unavailable volume")
        return original(path)

    monkeypatch.setattr(steam_scan.os, "scandir", denied)
    report = scan_steam([str(root)])
    assert report.library_status[str(root)] == "unavailable" and not report.games


def test_library_metadata_symlink_is_invalid_without_reading_target(tmp_path):
    root = library(tmp_path / "Steam")
    outside = tmp_path / "metadata"
    outside.write_text('"libraryfolders" {}')
    (root / "steamapps/libraryfolders.vdf").symlink_to(outside)
    report = scan_steam([str(root)])
    assert report.library_status[str(root)] == "invalid"
    assert "symlink" in report.skipped[0]


def test_common_directory_symlink_escape_is_rejected(tmp_path):
    root = tmp_path / "Steam"
    (root / "steamapps").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "steamapps/common").symlink_to(outside, target_is_directory=True)
    manifest(root)
    assert not scan_steam([str(root)]).games


def test_oversized_manifest_read_is_bounded(tmp_path, monkeypatch):
    root = library(tmp_path / "Steam")
    manifest(root)
    monkeypatch.setattr(steam_scan, "MAX_VDF_BYTES", 30)
    report = scan_steam([str(root)])
    assert not report.games and "too large" in report.skipped[0]


def test_steamapps_symlink_escape_rejected_before_manifest_read(tmp_path, monkeypatch):
    root, other = tmp_path / "Steam", library(tmp_path / "Other")
    root.mkdir()
    manifest(other)
    (root / "steamapps").symlink_to(other / "steamapps", target_is_directory=True)

    def forbidden(path):
        raise AssertionError("Escaped metadata must not be read")

    monkeypatch.setattr(steam_scan, "_read_vdf", forbidden)
    report = scan_steam([str(root)])
    assert report.library_status[str(root)] == "invalid" and not report.games


def test_scan_logs_only_stage_counts_duration_and_error_types(tmp_path, caplog):
    root = library(tmp_path / "private-steam-location")
    manifest(root, name="Private Game Name")
    (root / "steamapps/appmanifest_456.acf").write_text('"AppState" {')
    with caplog.at_level("INFO", logger="trainerhub.core.steam_scan"):
        report = scan_steam([str(root)])
    assert len(report.games) == 1
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "stage=start" in messages and "stage=complete" in messages
    assert "games_count=1" in messages and "elapsed_ms=" in messages and "error_type=VDFError" in messages
    assert "Private Game Name" not in messages and str(tmp_path) not in messages
    assert "appmanifest" not in messages and "Missing closing brace" not in messages


def test_cancelled_scan_has_count_only_completion_log(tmp_path, caplog):
    root = library(tmp_path / "Steam")
    with caplog.at_level("INFO", logger="trainerhub.core.steam_scan"):
        report = scan_steam([str(root)], lambda: True)
    assert report.cancelled and not report.games
    assert "stage=cancelled" in caplog.text and "elapsed_ms=" in caplog.text
    assert str(root) not in caplog.text


def test_three_roots_stateflags_escape_symlink_errors_do_not_hide_valid_game(tmp_path):
    first, second, third = (library(tmp_path / name) for name in ("Steam", "Second", "Third"))
    manifest(first)
    manifest(second, "456", "Updating", "Updating", flags=1048580)
    manifest(third, "789", "Escaping", "../escape", make_install=False)
    target = first / "steamapps/appmanifest_123.acf"
    (third / "steamapps/appmanifest_123.acf").symlink_to(target)
    folders(first, [first, second, third])
    report = scan_steam([str(first)])
    assert [game.appid for game in report.games] == ["123"]
    assert len(report.library_status) == 3 and len(report.skipped) == 3

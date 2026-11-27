from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from trainerhub.core.models import SteamGame
from trainerhub.core.mods import ModError, ModService, ScanCancelled, files
from trainerhub.core.mods.models import installation_key


@pytest.fixture
def installation(tmp_path):
    root = tmp_path / "Steam"
    game_root = root / "steamapps/common/测试游戏"
    game_root.mkdir(parents=True)
    (game_root / "Data").mkdir()
    (game_root / "Data/base.pak").write_bytes(b"original game data")
    return SteamGame("123", "测试游戏", str(root), str(game_root))


@pytest.fixture
def service(tmp_path):
    return ModService(tmp_path / "state", running=lambda _: False)


def folder(game, name="modExample", metadata=True):
    root = Path(game.install_path) / "Mods" / name
    root.mkdir(parents=True)
    (root / "content.bin").write_bytes(b"mod payload")
    if metadata:
        (root / "manifest.json").write_text(json.dumps({"Name": "示例模组", "Version": "1.2.3"}), encoding="utf-8")
    return root


def confirmed(service, game):
    record = service.scan([game]).records[0]
    return service.confirm(record.id).records[0]


def test_scan_is_read_only_and_never_treats_base_packages_as_mods(service, installation):
    root = folder(installation)
    report = service.scan([installation])
    assert len(report.records) == 1
    record = report.records[0]
    assert (record.name, record.version) == ("示例模组", "1.2.3")
    assert not record.manageable and record.reason == "unconfirmed"
    assert (root / "content.bin").read_bytes() == b"mod payload"
    assert not (Path(installation.library_path) / ".trainerhub-mods").exists()
    assert (Path(installation.install_path) / "Data/base.pak").read_bytes() == b"original game data"


def test_round_trip_survives_process_restart_and_preserves_every_byte(service, installation):
    root = folder(installation)
    (root / "空文件夹").mkdir()
    record = confirmed(service, installation)
    before = files.snapshot(root.parent, record.entries)
    service.toggle([record.id], False)
    assert not root.exists()
    restarted = ModService(service.store.directory, running=lambda _: False)
    disabled = restarted.scan([installation]).records[0]
    assert disabled.id == record.id and disabled.state == "disabled" and disabled.manageable
    assert files.snapshot(restarted._vault(disabled), disabled.entries) == before
    restarted.toggle([record.id], True)
    assert files.snapshot(root.parent, record.entries) == before
    assert restarted.read().records[0].state == "enabled"


def test_no_metadata_falls_back_to_directory_name(service, installation):
    folder(installation, "NoMetadata", metadata=False)
    record = service.scan([installation]).records[0]
    assert record.name == "NoMetadata" and record.version == ""


def test_user_rule_applies_to_other_games_without_per_game_code(service, installation):
    root = Path(installation.install_path) / "ExtraAddons/One"
    root.mkdir(parents=True)
    (root / "texture.bin").write_bytes(b"custom")
    assert service.scan([installation]).records == []
    service.add_rule(installation, "ExtraAddons", "folders")
    record = service.scan([installation]).records[0]
    assert record.manageable and record.evidence == "user"
    service.toggle([record.id], False)
    assert not root.exists()
    service.toggle([record.id], True)
    assert (root / "texture.bin").read_bytes() == b"custom"


def test_package_sidecars_are_one_atomic_mod(service, installation):
    root = Path(installation.install_path) / "Project/Content/Paks/~mods"
    root.mkdir(parents=True)
    for extension in ("pak", "utoc", "ucas"):
        (root / f"Outfit.{extension}").write_bytes(extension.encode())
    candidate = service.scan([installation]).records[0]
    assert len(candidate.entries) == 3 and candidate.reason == "unconfirmed"
    record = service.confirm(candidate.id).records[0]
    service.toggle([record.id], False)
    assert list(root.iterdir()) == []
    service.toggle([record.id], True)
    assert len(list(root.iterdir())) == 3


def test_incomplete_package_cannot_be_confirmed(service, installation):
    root = Path(installation.install_path) / "Content/Paks/~mods"
    root.mkdir(parents=True)
    (root / "Broken.ucas").write_bytes(b"payload")
    record = service.scan([installation]).records[0]
    assert record.reason == "incomplete_package"
    with pytest.raises(ModError, match="not_manageable"):
        service.confirm(record.id)


def test_reenable_never_overwrites_a_new_download(service, installation):
    root = folder(installation)
    record = confirmed(service, installation)
    service.toggle([record.id], False)
    root.mkdir()
    (root / "new.bin").write_bytes(b"new version")
    with pytest.raises(ModError, match="destination_exists"):
        service.toggle([record.id], True)
    assert (root / "new.bin").read_bytes() == b"new version"
    report = service.scan([installation])
    assert len(report.records) == 1
    assert report.records[0].state == "disabled" and report.records[0].reason == "destination_exists"


def test_changed_files_require_explicit_reconfirmation_even_after_two_scans(service, installation):
    root = folder(installation)
    record = confirmed(service, installation)
    (root / "content.bin").write_bytes(b"externally updated")
    with pytest.raises(ModError, match="files_changed"):
        service.toggle([record.id], False)
    for _ in range(2):
        record = service.scan([installation]).records[0]
        assert not record.manageable and record.reason == "files_changed"
    record = service.confirm(record.id).records[0]
    assert record.manageable


def test_batch_failure_rolls_back_already_moved_mods(service, installation, monkeypatch):
    first = folder(installation, "First")
    second = folder(installation, "Second")
    service.add_rule(installation, "Mods", "folders")
    records = service.scan([installation]).records
    original_move = files.move
    calls = 0

    def failing_move(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise PermissionError("locked file")
        original_move(source, target)

    monkeypatch.setattr(files, "move", failing_move)
    with pytest.raises(ModError, match="operation_failed"):
        service.toggle([record.id for record in records], False)
    assert first.exists() and second.exists()
    assert all(record.state == "enabled" for record in service.read().records)
    assert service.store.load()["journal"] is None


def test_crash_after_a_move_is_recovered_on_restart(service, installation, monkeypatch):
    root = folder(installation)
    record = confirmed(service, installation)
    original_move = files.move

    class ProcessDied(BaseException):
        pass

    def crash(source, target):
        original_move(source, target)
        raise ProcessDied()

    monkeypatch.setattr(files, "move", crash)
    with pytest.raises(ProcessDied):
        service.toggle([record.id], False)
    assert not root.exists() and service.store.load()["journal"] is not None
    monkeypatch.setattr(files, "move", original_move)
    restarted = ModService(service.store.directory, running=lambda _: False)
    restarted.recover()
    assert root.exists() and restarted.read().records[0].state == "enabled"


def test_recovery_collision_preserves_both_copies_and_journal(service, installation, monkeypatch):
    root = folder(installation)
    record = confirmed(service, installation)
    original_move = files.move

    def crash(source, target):
        original_move(source, target)
        raise KeyboardInterrupt()

    monkeypatch.setattr(files, "move", crash)
    with pytest.raises(KeyboardInterrupt):
        service.toggle([record.id], False)
    root.mkdir()
    (root / "other").write_bytes(b"do not overwrite")
    monkeypatch.setattr(files, "move", original_move)
    with pytest.raises(ModError, match="recovery_required"):
        service.recover()
    assert (root / "other").read_bytes() == b"do not overwrite"
    assert service._vault(record).joinpath(record.entries[0]).exists()
    assert service.store.load()["journal"] is not None


def test_cancelled_scan_does_not_save_partial_records(service, installation):
    folder(installation)
    with pytest.raises(ScanCancelled):
        service.scan([installation], cancelled=lambda: True)
    assert service.read().records == []


def test_unavailable_game_retains_disabled_mod(service, installation):
    folder(installation)
    record = confirmed(service, installation)
    service.toggle([record.id], False)
    missing = service.scan([], library_status={installation.library_path: "unavailable"}).records[0]
    assert missing.state == "disabled" and missing.reason == "game_unavailable"
    assert not missing.manageable
    assert service.scan([installation]).records[0].manageable


def test_game_running_blocks_file_moves(service, installation):
    root = folder(installation)
    record = confirmed(service, installation)
    service.running = lambda _: True
    with pytest.raises(ModError, match="game_running"):
        service.toggle([record.id], False)
    assert root.exists()


def test_hardlinks_are_read_only_candidates(service, installation, tmp_path, monkeypatch):
    root = folder(installation)
    try:
        os.link(root / "content.bin", tmp_path / "external.bin")
    except PermissionError:
        # Some Windows sandboxes prohibit creating hardlinks. Still exercise the
        # rejection against the same stat information a shared file returns.
        original_stat = Path.stat

        def shared_stat(path, *args, **kwargs):
            result = original_stat(path, *args, **kwargs)
            if path.name == "content.bin":
                values = list(result)
                values[3] = 2
                return os.stat_result(values)
            return result

        monkeypatch.setattr(Path, "stat", shared_stat)
    record = service.scan([installation]).records[0]
    assert not record.manageable and record.reason == "linked_files"


@pytest.mark.parametrize("root", ["../Windows", "Data", "Data/Textures", "Content/Paks", "Engine/Assets", "/", "C:/Windows", "."])
def test_unsafe_roots_cannot_be_adopted(service, installation, root):
    with pytest.raises(ModError):
        service.add_rule(installation, root, "folders")


def test_kcd_manifest_provides_identity_but_load_order_requires_special_handling(service, installation):
    installation.appid = "1771300"
    root = folder(installation, metadata=False)
    (root / "mod.manifest").write_text("<kcd_mod><info><name>Clean Armour</name><version>2</version></info></kcd_mod>")
    record = service.scan([installation]).records[0]
    assert record.name == "Clean Armour" and record.manageable
    (root.parent / "mod_order.txt").write_text("modExample")
    record = service.scan([installation]).records[0]
    assert record.reason == "configuration_required" and not record.manageable


def test_witcher_script_and_shared_output_are_never_plain_folder_toggles(service, installation):
    installation.appid = "292030"
    root = folder(installation)
    (root / "content/scripts").mkdir(parents=True)
    (root / "content/scripts/player.ws").write_text("some script")
    service.add_rule(installation, "Mods", "folders")
    record = service.scan([installation]).records[0]
    assert not record.manageable and record.reason == "special_handling"


def test_corrupt_store_is_not_silently_reset(service):
    service.store.directory.mkdir()
    service.store.path.write_text("not JSON")
    with pytest.raises(ModError, match="store_corrupt"):
        service.read()
    assert service.store.path.read_text() == "not JSON"


def test_same_appid_in_two_libraries_has_distinct_identity(installation, tmp_path):
    other = SteamGame(installation.appid, installation.name, str(tmp_path / "other"), str(tmp_path / "other/steamapps/common/game"))
    assert installation_key(installation) != installation_key(other)


def test_nested_rules_cannot_double_claim_an_existing_candidate(service, installation):
    root = folder(installation)
    (root / "Nested").mkdir()
    with pytest.raises(ModError, match="overlapping_rules"):
        service.add_rule(installation, "Mods/modExample", "folders")


def test_cancel_mid_scan_retains_previous_successful_snapshot(service, installation):
    folder(installation)
    previous = service.scan([installation])
    before = service.store.path.read_bytes()
    calls = 0

    def cancel_later():
        nonlocal calls
        calls += 1
        return calls >= 5

    with pytest.raises(ScanCancelled):
        service.scan([installation], cancelled=cancel_later)
    assert service.store.path.read_bytes() == before
    assert service.read().records[0].id == previous.records[0].id


def test_game_file_changed_after_scan_never_moves(service, installation):
    root = folder(installation)
    record = confirmed(service, installation)
    (root / "new.txt").write_text("external new file")
    with pytest.raises(ModError, match="files_changed"):
        service.toggle([record.id], False)
    assert (root / "new.txt").exists()
    assert not service._vault(record).exists()


def test_committed_journal_cleanup_failure_does_not_report_move_as_failed(service, installation, monkeypatch):
    root = folder(installation)
    record = confirmed(service, installation)
    save = service.store.save
    calls = 0

    def fail_final_save(data):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("disk temporarily busy")
        save(data)

    monkeypatch.setattr(service.store, "save", fail_final_save)
    report = service.toggle([record.id], False)
    assert report.records[0].state == "disabled" and not root.exists()
    assert service.store.load()["journal"]["phase"] == "committed"
    monkeypatch.setattr(service.store, "save", save)
    service.recover()
    assert service.store.load()["journal"] is None
    assert service.read().records[0].state == "disabled"


def test_junction_candidates_are_rejected_without_traversing_target(service, installation, monkeypatch):
    root = folder(installation)
    is_link = files.is_link
    visited = []
    original_open = Path.open

    def junction(path):
        return path.name == root.name or is_link(path)

    def guarded_open(path, *args, **kwargs):
        if path.name == "content.bin":
            visited.append(path)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(files, "is_link", junction)
    monkeypatch.setattr(Path, "open", guarded_open)
    record = service.scan([installation]).records[0]
    assert record.reason == "linked_files" and not record.manageable
    assert visited == []


@pytest.mark.parametrize("name", ["vortex.deployment.json", "vortex.deployment.mods.json"])
def test_manager_manifest_at_game_root_keeps_mods_read_only(service, installation, name):
    folder(installation)
    (Path(installation.install_path) / name).write_text("{}")
    service.add_rule(installation, "Mods", "folders")
    record = service.scan([installation]).records[0]
    assert not record.manageable and record.reason == "external_manager"


def test_game_started_during_preflight_prevents_any_move(service, installation):
    root = folder(installation)
    record = confirmed(service, installation)
    checks = 0

    def started(_):
        nonlocal checks
        checks += 1
        return checks >= 2

    service.running = started
    with pytest.raises(ModError, match="game_running"):
        service.toggle([record.id], False)
    assert root.exists() and service.store.load()["journal"] is None


def test_recovery_waits_until_game_exits(service, installation, monkeypatch):
    root = folder(installation)
    record = confirmed(service, installation)
    original_move = files.move

    def crash(source, target):
        original_move(source, target)
        raise KeyboardInterrupt()

    monkeypatch.setattr(files, "move", crash)
    with pytest.raises(KeyboardInterrupt):
        service.toggle([record.id], False)
    monkeypatch.setattr(files, "move", original_move)
    service.running = lambda _: True
    with pytest.raises(ModError, match="game_running"):
        service.recover()
    assert not root.exists() and service.store.load()["journal"] is not None
    service.running = lambda _: False
    service.recover()
    assert root.exists() and service.read().records[0].state == "enabled"

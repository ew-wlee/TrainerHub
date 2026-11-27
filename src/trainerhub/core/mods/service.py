"""Read existing installations; move only explicitly owned file-presence Mods.

Scanning never writes to a game. A write-ahead journal covers every member of a
batch, and recovery returns interrupted operations to their previous state.
"""

from __future__ import annotations

import copy
import hashlib
import logging
import os
from collections.abc import Callable
from dataclasses import asdict
from itertools import islice
from pathlib import Path

from ..models import SteamGame
from . import files
from .models import DetectionRule, ModError, ModRecord, ModScanReport, installation_key
from .storage import ModStore

MAX_GROUPS = 1000
_PACKAGES = {".pak", ".ucas", ".utoc"}
_SHARED = {"shared", "ue4ss", "scripts", "core", "mod0000_mergedfiles"}
_MANAGER_MARKERS = {"vortex.deployment", "vortex.deployment.json", ".vortex_deployment.json", "__folder_managed_by_vortex", "__vortex_staging_folder"}


class ModService:
    def __init__(self, directory: Path, *, running: Callable[[Path], bool] = files.game_running) -> None:
        self.store = ModStore(directory)
        self.running = running

    @staticmethod
    def _game_root(game: SteamGame) -> Path:
        library = Path(game.library_path)
        game_path = Path(game.install_path)
        try:
            rel = game_path.relative_to(library / "steamapps" / "common")
        except ValueError as exc:
            raise ModError("unsafe_path", str(game_path)) from exc
        if len(rel.parts) != 1:
            raise ModError("unsafe_path", str(game_path))
        return files.checked(library, (Path("steamapps/common") / rel).as_posix())

    def _root(self, game: SteamGame, root: str) -> Path:
        rel = files.relative(root)
        # Selecting a game root, engine folder, Bin or Data is not an ownership rule.
        if rel.parts[-1].casefold() in {"engine", "bin", "binaries", "data", "content", "paks", "plugins", "platform", "steam"}:
            raise ModError("unsafe_root", root)
        protected = {"engine", "bin", "binaries", "data", "content", "paks", "plugins", "platform", "steam"}
        if rel.parts[0].casefold() in protected and not any(part.casefold() in {"mods", "~mods", "usermods", "addons"} for part in rel.parts):
            raise ModError("unsafe_root", root)
        return files.checked(self._game_root(game), root)

    def _vault(self, record: ModRecord) -> Path:
        suffix = f".trainerhub-mods/{record.game_key}/{record.id}/{record.root}"
        return files.checked(Path(record.game.library_path), suffix)

    def _record(self, value: dict) -> ModRecord:
        try:
            record = ModRecord.from_dict(value)
            if len(record.id) != 24 or any(c not in "0123456789abcdef" for c in record.id):
                raise ValueError("Invalid identity")
            self._root(record.game, record.root)
            if not record.entries or len(set(record.entries)) != len(record.entries):
                raise ValueError("Invalid members")
            for entry in record.entries:
                if len(files.relative(entry).parts) != 1:
                    raise ValueError("Members must be direct children")
            return record
        except (KeyError, TypeError, ValueError) as exc:
            raise ModError("store_corrupt", str(self.store.path)) from exc

    def _paths(self, record: ModRecord) -> tuple[Path, Path]:
        return self._root(record.game, record.root), self._vault(record)

    @staticmethod
    def _special(game: SteamGame, root: Path, entries: list[str], inventory: dict[str, str]) -> str:
        names = {path.name.casefold() for path in root.iterdir()}
        game_names = {path.name.casefold() for path in files.native(Path(game.install_path)).iterdir()}
        manager_names = names | game_names
        if manager_names & _MANAGER_MARKERS or any(name.startswith("vortex.deployment") and name.endswith(".json") for name in manager_names):
            return "external_manager"
        if any(Path(entry).stem.casefold() in _SHARED for entry in entries):
            return "shared_files"
        if any(name in names for name in ("mod_order.txt", "modsettings.lsx", "mods.settings")):
            return "configuration_required"
        if game.appid == "292030":
            # Script Merger output is shared by the whole loadout; moving one input
            # would leave stale compiled results behind. Never offer that as a toggle.
            if any("/scripts/" in path.casefold() or path.casefold().endswith(".ws") for path in inventory):
                return "special_handling"
            if (root / "mod0000_MergedFiles").exists():
                return "special_handling"
            settings = Path.home() / "Documents/The Witcher 3/mods.settings"
            if settings.exists():
                return "configuration_required"
        return ""

    def _rules(self, game: SteamGame, data: dict) -> list[DetectionRule]:
        key, root = installation_key(game), self._game_root(game)
        result: dict[str, DetectionRule] = {}
        candidates = [root / "Mods", root / "mods", root / "Content/Paks/~mods"]
        # Bounded project-directory discovery. Never crawl base-game Paks looking
        # for .pak files, which are also used by unmodified games.
        projects = list(islice(root.iterdir(), MAX_GROUPS + 1))
        if len(projects) > MAX_GROUPS:
            raise ModError("scan_limit", str(root))
        for project in projects:
            if project.is_dir() and not files.is_link(project):
                candidates.append(project / "Content/Paks/~mods")
        for candidate in candidates:
            if candidate.exists():
                relative = candidate.relative_to(root).as_posix()
                mode = "packages" if candidate.name == "~mods" else "folders"
                rule = DetectionRule(key, relative, mode, "candidate")
                result[relative.casefold()] = rule
        for value in data["rules"].values():
            rule = DetectionRule(**value)
            if rule.game_key == key:
                result[rule.root.casefold()] = rule
        return list(result.values())

    @staticmethod
    def _groups(root: Path, mode: str) -> list[tuple[str, list[str]]]:
        children = sorted(islice(root.iterdir(), MAX_GROUPS + 1))
        if len(children) > MAX_GROUPS:
            raise ModError("scan_limit", str(root))
        if mode == "folders":
            return [(path.name, [path.name]) for path in children if path.is_dir() and not path.name.startswith(".")]
        if mode != "packages":
            raise ModError("unsafe_root", mode)
        groups: dict[str, list[str]] = {}
        for path in children:
            if path.suffix.lower() in _PACKAGES:
                groups.setdefault(path.stem, []).append(path.name)
        return sorted(groups.items())

    def _detect(self, game: SteamGame, rule: DetectionRule, data: dict, cancelled) -> list[ModRecord]:
        root = self._root(game, rule.root)
        result = []
        for group, entries in self._groups(root, rule.mode):
            files.checkpoint(cancelled)
            identity = f"{rule.game_key}:{rule.root.casefold()}:{rule.mode}:{group.casefold()}"
            identifier = hashlib.sha256(identity.encode()).hexdigest()[:24]
            record = ModRecord(identifier, game, rule.root, entries, group)
            previous = self._record(data["records"][identifier]) if identifier in data["records"] else None
            # A disabled record can have a new download at its old path. Its vault
            # remains authoritative and must not be overwritten or re-adopted.
            if previous is not None and previous.state == "disabled":
                continue
            try:
                record.inventory = files.snapshot(root, entries, cancelled)
                if not any(not key.endswith("/") for key in record.inventory):
                    continue
                if rule.mode == "folders":
                    name, version = files.metadata(root / entries[0])
                    record.name, record.version = name or group, version
                extensions = {Path(entry).suffix.lower() for entry in entries}
                incomplete = (".ucas" in extensions) != (".utoc" in extensions)
                record.reason = "incomplete_package" if incomplete else self._special(game, root, entries, record.inventory)
                # KCD2's manifest is documented evidence for an independent Mod.
                # A custom load-order file requires a separate configuration rule.
                manifest_name, _ = files.metadata(root / entries[0], ("mod.manifest",)) if rule.mode == "folders" else ("", "")
                builtin = game.appid == "1771300" and rule.root.casefold() == "mods" and bool(manifest_name)
                record.confirmed = builtin or rule.source == "user" or bool(previous and previous.confirmed)
                record.evidence = "manifest" if builtin else "user" if record.confirmed else "candidate"
                if previous is not None and (previous.reason == "files_changed" or (previous.confirmed and previous.inventory != record.inventory)):
                    record.confirmed = False
                    record.reason = record.reason or "files_changed"
                record.reason = record.reason or ("" if record.confirmed else "unconfirmed")
                record.state = "enabled" if record.confirmed and not record.reason else "pending"
            except (OSError, ModError) as exc:
                record.state = "pending"
                record.reason = exc.code if isinstance(exc, ModError) else "unreadable"
            result.append(record)
        return result

    def _report(self, data: dict, *, issues=None, library_status=None) -> ModScanReport:
        return ModScanReport(
            games=[SteamGame(**game) for game in data["games"].values()],
            records=[self._record(record) for record in data["records"].values()],
            rules=[DetectionRule(**rule) for rule in data["rules"].values()],
            issues=data.get("issues", {}) if issues is None else issues,
            library_status=data.get("library_status", {}) if library_status is None else library_status,
        )

    def read(self) -> ModScanReport:
        """Load durable records without moving files or implicitly scanning games."""
        with self.store.session() as data:
            return self._report(data)

    def scan(self, games: list[SteamGame], *, library_status: dict[str, str] | None = None, cancelled=None) -> ModScanReport:
        with self.store.session() as data:
            self._recover(data)
            issues: dict[str, list[str]] = {}
            found: dict[str, ModRecord] = {}
            game_map = {installation_key(game): game for game in games if game.appid != "228980"}
            for key, game in game_map.items():
                files.checkpoint(cancelled)
                try:
                    rules = self._rules(game, data)
                    if not rules:
                        issues.setdefault(key, []).append("no_rules")
                    for rule in rules:
                        try:
                            for record in self._detect(game, rule, data, cancelled):
                                found[record.id] = record
                        except (OSError, ModError) as exc:
                            issues.setdefault(key, []).append(exc.code if isinstance(exc, ModError) else "unreadable")
                except (OSError, ModError) as exc:
                    issues.setdefault(key, []).append(exc.code if isinstance(exc, ModError) else "unreadable")
            for identifier, value in data["records"].items():
                files.checkpoint(cancelled)
                previous = self._record(value)
                if identifier in found:
                    continue
                if previous.game_key not in game_map:
                    previous.reason = "game_unavailable"
                    issues.setdefault(previous.game_key, []).append("game_unavailable")
                    found[identifier] = previous
                    continue
                if previous.state == "disabled":
                    try:
                        original, vault = self._paths(previous)
                        if files.snapshot(vault, previous.entries, cancelled) != previous.inventory:
                            previous.reason = "files_changed"
                        elif any(os.path.lexists(original / entry) for entry in previous.entries):
                            previous.reason = "destination_exists"
                        else:
                            previous.reason = ""
                    except (OSError, ModError) as exc:
                        previous.reason = exc.code if isinstance(exc, ModError) else "unreadable"
                else:
                    previous.reason = "unreadable" if previous.game_key in issues and "no_rules" not in issues[previous.game_key] else "files_missing"
                    if previous.reason == "files_missing":
                        previous.state = "pending"
                found[identifier] = previous
            files.checkpoint(cancelled)
            # No partial discovery results are committed on cancellation.
            data["games"].update({key: asdict(game) for key, game in game_map.items()})
            data["records"] = {key: record.to_dict() for key, record in found.items()}
            retained_keys = {record.game_key for record in found.values()}
            data["games"] = {key: value for key, value in data["games"].items() if key in game_map or key in retained_keys}
            data["issues"] = issues
            data["library_status"] = library_status or {}
            self.store.save(data)
            return self._report(data, issues=issues, library_status=library_status)

    def add_rule(self, game: SteamGame, root: str, mode: str) -> None:
        path = self._root(game, root)
        if not path.is_dir() or mode not in {"folders", "packages"}:
            raise ModError("unsafe_root", root)
        with self.store.session() as data:
            self._recover(data)
            key = installation_key(game)
            for rule in self._rules(game, data):
                if rule.game_key == key:
                    other = self._root(game, rule.root)
                    if other != path and (path.is_relative_to(other) or other.is_relative_to(path)):
                        raise ModError("overlapping_rules", root)
            rule = DetectionRule(key, files.relative(root).as_posix(), mode)
            data["rules"] = {k: v for k, v in data["rules"].items() if not (v["game_key"] == key and v["root"].casefold() == rule.root.casefold())}
            data["rules"][rule.key] = asdict(rule)
            data["games"][key] = asdict(game)
            self.store.save(data)

    def confirm(self, identifier: str) -> ModScanReport:
        with self.store.session() as data:
            self._recover(data)
            record = self._record(data["records"][identifier])
            if record.state == "disabled" or record.reason not in {"unconfirmed", "files_changed"}:
                raise ModError("not_manageable", record.name)
            root = self._root(record.game, record.root)
            inventory = files.snapshot(root, record.entries)
            reason = self._special(record.game, root, record.entries, inventory)
            if reason:
                raise ModError(reason, record.name)
            record.confirmed, record.state, record.reason = True, "enabled", ""
            record.evidence, record.inventory = "user", inventory
            data["records"][identifier] = record.to_dict()
            self.store.save(data)
            return self._report(data)

    def toggle(self, identifiers: list[str], enabled: bool) -> ModScanReport:
        with self.store.session() as data:
            self._recover(data)
            before, after, moves = {}, {}, []
            all_paths: list[Path] = []
            checked_games: set[str] = set()
            for identifier in dict.fromkeys(identifiers):
                if identifier not in data["records"]:
                    raise ModError("not_manageable", identifier)
                record = self._record(data["records"][identifier])
                if not record.manageable:
                    raise ModError("not_manageable", record.name)
                if record.state == ("enabled" if enabled else "disabled"):
                    continue
                game_root = self._game_root(record.game)
                if not game_root.is_dir():
                    raise ModError("game_unavailable", record.game.name)
                if record.game_key not in checked_games:
                    if self.running(game_root):
                        raise ModError("game_running", record.game.name)
                    checked_games.add(record.game_key)
                original, vault = self._paths(record)
                reason = self._special(record.game, original, record.entries, record.inventory)
                if reason:
                    raise ModError(reason, record.name)
                source, target = (vault, original) if enabled else (original, vault)
                if files.snapshot(source, record.entries) != record.inventory:
                    raise ModError("files_changed", record.name)
                before[identifier] = record.to_dict()
                for entry in record.entries:
                    src, dst = files.checked(source, entry), files.checked(target, entry)
                    if os.path.lexists(dst):
                        raise ModError("destination_exists", str(dst))
                    # A batch must not claim the same file or nested directories twice.
                    if any(src == path or src.is_relative_to(path) or path.is_relative_to(src) for path in all_paths):
                        raise ModError("overlapping_rules", str(src))
                    all_paths.append(src)
                    moves.append({"record": identifier, "entry": entry, "enabled": enabled})
                record.state = "enabled" if enabled else "disabled"
                after[identifier] = record.to_dict()
            if not moves:
                return self._report(data)
            # Hashing large Mods can take time. Recheck immediately before writing
            # the journal, so a game started during preflight does not get modified.
            for value in {value["game"]["install_path"]: value for value in before.values()}.values():
                record = self._record(value)
                if self.running(self._game_root(record.game)):
                    raise ModError("game_running", record.game.name)
            data["journal"] = {"phase": "moving", "before": before, "after": after, "moves": moves}
            self.store.save(data)
            try:
                for item in moves:
                    record = self._record(before[item["record"]])
                    original, vault = self._paths(record)
                    source, target = (vault, original) if enabled else (original, vault)
                    files.move(files.checked(source, item["entry"]), files.checked(target, item["entry"]))
                data["records"].update(after)
                data["journal"]["phase"] = "committed"
                self.store.save(data)
            except Exception as exc:
                try:
                    self._rollback(data)
                except Exception as recovery_error:
                    raise ModError("recovery_required", str(recovery_error)) from exc
                if isinstance(exc, ModError):
                    raise
                raise ModError("operation_failed", str(exc)) from exc
            # A crash here is a committed operation. Recovery only clears its journal.
            data["journal"] = None
            try:
                self.store.save(data)
            except OSError:
                # State and file moves already committed. A retained committed
                # journal is harmless and will be cleared by the next operation.
                logging.getLogger(__name__).warning("Could not clear committed Mod journal")
            return self._report(data)

    def _rollback(self, data: dict) -> None:
        journal = data["journal"]
        games = {value["game"]["install_path"]: value for value in journal["before"].values()}
        for value in games.values():
            record = self._record(value)
            if self.running(self._game_root(record.game)):
                raise ModError("game_running", record.game.name)
        for item in reversed(journal["moves"]):
            record = self._record(journal["before"][item["record"]])
            if item["entry"] not in record.entries:
                raise ModError("store_corrupt")
            original, vault = self._paths(record)
            source, target = (vault, original) if item["enabled"] else (original, vault)
            src, dst = files.checked(source, item["entry"]), files.checked(target, item["entry"])
            source_exists, target_exists = os.path.lexists(src), os.path.lexists(dst)
            if source_exists == target_exists:
                raise ModError("recovery_required", str(src))
            current = target if target_exists else source
            expected = {key: value for key, value in record.inventory.items() if key == item["entry"] or key.startswith(item["entry"] + "/")}
            if files.snapshot(current, [item["entry"]]) != expected:
                raise ModError("recovery_required", str(dst))
            if target_exists:
                files.move(dst, src)
        data["records"].update(copy.deepcopy(journal["before"]))
        data["journal"] = None
        self.store.save(data)

    def _recover(self, data: dict) -> None:
        if data.get("journal") is None:
            return
        if data["journal"].get("phase") == "committed":
            data["journal"] = None
            self.store.save(data)
            return
        try:
            self._rollback(data)
        except Exception as exc:
            if isinstance(exc, ModError) and exc.code == "game_running":
                raise
            raise ModError("recovery_required", str(exc)) from exc

    def recover(self) -> ModScanReport:
        with self.store.session() as data:
            self._recover(data)
            return self._report(data)

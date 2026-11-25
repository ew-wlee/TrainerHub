"""Read Steam library metadata without touching game contents or Steam state."""

from __future__ import annotations

import logging
import os
import re
import sys
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from .models import ScanReport, SteamGame

MAX_VDF_BYTES = 2 * 1024 * 1024
MAX_VDF_DEPTH = 32
MAX_VDF_TOKENS = 100_000
_MANIFEST = re.compile(r"appmanifest_([0-9]+)\.acf", re.IGNORECASE)
_logger = logging.getLogger(__name__)


class VDFError(ValueError):
    """Malformed or over-limit Valve KeyValues metadata."""


def _tokens(text: str) -> Iterator[str | tuple[str]]:
    pos, count = 0, 0
    while pos < len(text):
        char = text[pos]
        if char.isspace():
            pos += 1
            continue
        if text.startswith("//", pos):
            end = text.find("\n", pos + 2)
            pos = len(text) if end < 0 else end + 1
            continue
        if text.startswith("/*", pos):
            end = text.find("*/", pos + 2)
            if end < 0:
                raise VDFError("Unterminated comment")
            pos = end + 2
            continue
        count += 1
        if count > MAX_VDF_TOKENS:
            raise VDFError("Too many tokens")
        if char in "{}":
            yield (char,)
            pos += 1
            continue
        if char == '"':
            pos += 1
            chars: list[str] = []
            while pos < len(text):
                char = text[pos]
                pos += 1
                if char == '"':
                    break
                if char == "\\":
                    if pos >= len(text):
                        raise VDFError("Unterminated escape")
                    escaped = text[pos]
                    pos += 1
                    chars.append(
                        {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}.get(escaped, "\\" + escaped)
                    )
                else:
                    chars.append(char)
            else:
                raise VDFError("Unterminated string")
            yield "".join(chars)
            continue
        start = pos
        while pos < len(text) and not text[pos].isspace() and text[pos] not in '{}"':
            if text.startswith(("//", "/*"), pos):
                break
            pos += 1
        if pos == start:
            raise VDFError("Unexpected token")
        yield text[start:pos]


def parse_vdf(text: str) -> dict:
    """Parse a bounded KeyValues subset: strings, braces, escapes and comments."""
    if len(text.encode("utf-8")) > MAX_VDF_BYTES:
        raise VDFError("Metadata too large")
    tokens = iter(_tokens(text.lstrip("\ufeff")))

    def block(depth: int, nested: bool) -> dict:
        if depth > MAX_VDF_DEPTH:
            raise VDFError("Nesting too deep")
        result: dict = {}
        for token in tokens:
            if token == ("}",):
                if not nested:
                    raise VDFError("Unexpected closing brace")
                return result
            if not isinstance(token, str):
                raise VDFError("Expected key")
            key = token.casefold()
            if key in result:
                raise VDFError("Duplicate key")
            value = next(tokens, None)
            if value == ("{",):
                result[key] = block(depth + 1, True)
            elif isinstance(value, str):
                result[key] = value
            else:
                raise VDFError("Expected value")
        if nested:
            raise VDFError("Missing closing brace")
        return result

    return block(0, False)


def _read_vdf(path: Path) -> dict:
    with path.open("rb") as stream:
        data = stream.read(MAX_VDF_BYTES + 1)
    if len(data) > MAX_VDF_BYTES:
        raise VDFError("Metadata too large")
    return parse_vdf(data.decode("utf-8-sig"))


def _root(path: str | Path) -> Path:
    value = Path(path).expanduser().resolve()
    return value.parent if value.name.casefold() == "steamapps" else value


def _library_paths(metadata: dict) -> list[str]:
    folders = metadata.get("libraryfolders")
    if not isinstance(folders, dict):
        raise VDFError("Missing libraryfolders")
    paths: list[str] = []
    for key, record in folders.items():
        if not key.isdecimal():
            continue
        value = record.get("path") if isinstance(record, dict) else record
        if not isinstance(value, str) or not value or "\x00" in value:
            raise VDFError("Invalid library path")
        if not Path(value).expanduser().is_absolute():
            raise VDFError("Library path must be absolute")
        paths.append(value)
    return paths


def discover_steam_paths() -> list[str]:
    """Locate Steam roots using read-only platform defaults and Windows registry."""
    home = Path.home()
    candidates: list[str | Path] = []
    if sys.platform == "win32":
        try:
            import winreg

            for hive, key, name in (
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Valve\Steam", "InstallPath"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam", "InstallPath"),
            ):
                try:
                    with winreg.OpenKey(hive, key, 0, winreg.KEY_READ) as handle:
                        value, _ = winreg.QueryValueEx(handle, name)
                    if isinstance(value, str):
                        candidates.append(value)
                except OSError:
                    continue
        except ImportError:
            pass
        for env in ("ProgramFiles(x86)", "ProgramFiles", "ProgramW6432"):
            if os.environ.get(env):
                candidates.append(Path(os.environ[env]) / "Steam")
        candidates.extend((Path("C:/Program Files (x86)/Steam"), Path("C:/Program Files/Steam")))
    elif sys.platform == "darwin":
        candidates.append(home / "Library/Application Support/Steam")
    else:
        candidates.extend((home / ".steam/steam", home / ".steam/root", home / ".local/share/Steam"))
        candidates.append(home / ".var/app/com.valvesoftware.Steam/.local/share/Steam")
        if os.environ.get("XDG_DATA_HOME"):
            candidates.append(Path(os.environ["XDG_DATA_HOME"]) / "Steam")
    roots: list[str] = []
    for candidate in candidates:
        try:
            root = _root(candidate)
            if (root / "steamapps").is_dir() and str(root) not in roots:
                roots.append(str(root))
        except (OSError, ValueError, RuntimeError):
            continue
    return roots


class NotInstalledError(VDFError):
    """A readable manifest confirms that this installation is not ready."""


def _installed_game(manifest: Path, root: Path, scanned_at: str) -> SteamGame:
    match = _MANIFEST.fullmatch(manifest.name)
    state = _read_vdf(manifest).get("appstate")
    if match is None or not isinstance(state, dict):
        raise VDFError("Missing AppState")
    appid = state.get("appid")
    if not isinstance(appid, str) or appid != match.group(1) or int(appid) <= 0:
        raise VDFError("Appid differs from manifest filename")
    try:
        flags = int(state.get("stateflags", ""))
    except (TypeError, ValueError) as exc:
        raise VDFError("Invalid StateFlags") from exc
    if not flags & 4 or flags & ~(4 | 64):
        raise NotInstalledError("Not fully installed or update/download in progress")
    name, directory = state.get("name"), state.get("installdir")
    if not isinstance(name, str) or not name.strip():
        raise VDFError("Missing game name")
    if not isinstance(directory, str) or not directory.strip() or directory in (".", ".."):
        raise VDFError("Invalid installdir")
    if re.search(r"[\\/:\x00-\x1f]", directory) or directory != directory.strip() or directory.endswith("."):
        raise VDFError("Unsafe installdir")
    steamapps = (root / "steamapps").resolve()
    common = (steamapps / "common").resolve()
    install = (common / directory).resolve()
    if not steamapps.is_relative_to(root) or not common.is_relative_to(steamapps):
        raise VDFError("Library directory escapes root")
    if not install.is_relative_to(common) or install == common:
        raise VDFError("Install directory escapes common")
    if not install.is_dir():
        raise NotInstalledError("Install directory missing")
    build = state.get("buildid", "")
    return SteamGame(
        appid,
        name.strip(),
        str(root),
        str(install),
        flags,
        build if isinstance(build, str) else "",
        scanned_at,
    )


def scan_steam(
    paths: list[str] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> ScanReport:
    """Scan roots or library paths; cancelled results never contain partial games."""
    started = perf_counter()
    stamp = datetime.now(timezone.utc).isoformat()
    report = ScanReport(scanned_at=stamp)
    pending = list(discover_steam_paths() if paths is None else paths)
    seen: set[str] = set()
    _logger.info("steam_scan stage=start roots_count=%d", len(pending))

    def finish() -> ScanReport:
        report.games.sort(key=lambda game: (game.name.casefold(), game.appid))
        _logger.info(
            "steam_scan stage=%s libraries_count=%d games_count=%d skipped_count=%d elapsed_ms=%.1f",
            "cancelled" if report.cancelled else "complete",
            len(report.library_status),
            len(report.games),
            len(report.skipped),
            (perf_counter() - started) * 1000,
        )
        return report

    def stop() -> bool:
        if cancelled is not None and cancelled():
            report.cancelled = True
            report.games.clear()
            return True
        return False

    while pending:
        if stop():
            return finish()
        raw = pending.pop(0)
        try:
            root = _root(raw)
            label = str(root)
        except (OSError, ValueError, RuntimeError) as exc:
            report.library_status[str(raw)] = "invalid"
            _logger.warning("steam_scan stage=root error_type=%s", type(exc).__name__)
            continue
        if label in seen:
            continue
        seen.add(label)
        steamapps = root / "steamapps"
        try:
            if not steamapps.is_dir():
                report.library_status[label] = "unavailable"
                continue
            if not steamapps.resolve().is_relative_to(root):
                report.library_status[label] = "invalid"
                report.skipped.append(f"{steamapps}: Library directory escapes root")
                continue
            metadata = steamapps / "libraryfolders.vdf"
            report.library_status[label] = "ok"
            if metadata.exists():
                try:
                    if metadata.is_symlink():
                        raise VDFError("Library metadata must not be a symlink")
                    pending.extend(_library_paths(_read_vdf(metadata)))
                except (OSError, ValueError, RuntimeError) as exc:
                    report.library_status[label] = "invalid"
                    report.skipped.append(f"{metadata}: {exc}")
                    _logger.warning("steam_scan stage=libraryfolders error_type=%s", type(exc).__name__)
            manifests = []
            with os.scandir(steamapps) as entries:
                for entry in entries:
                    if _MANIFEST.fullmatch(entry.name):
                        manifests.append(steamapps / entry.name)
            manifests.sort()
        except (OSError, ValueError, RuntimeError) as exc:
            report.library_status[label] = "unavailable"
            report.skipped.append(f"{root}: {exc}")
            _logger.warning("steam_scan stage=library error_type=%s", type(exc).__name__)
            continue
        for manifest in manifests:
            if stop():
                return finish()
            try:
                if manifest.is_symlink() or not manifest.resolve().is_relative_to(steamapps.resolve()):
                    raise VDFError("Manifest is a symlink or escapes library")
                game = _installed_game(manifest, root, stamp)
            except NotInstalledError as exc:
                report.skipped.append(f"{manifest}: {exc}")
                continue
            except (OSError, ValueError, RuntimeError) as exc:
                report.library_status[label] = "invalid"
                report.skipped.append(f"{manifest}: {exc}")
                _logger.warning("steam_scan stage=manifest error_type=%s", type(exc).__name__)
                continue
            report.games.append(game)
    stop()
    return finish()

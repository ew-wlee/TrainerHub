"""Archive sniffing and safe extraction.

Rules that matter for a tool that downloads third-party files:

* every member path is validated (no absolute paths, no ``..``, no drive letters)
* total uncompressed size and member count are capped
* nothing is ever executed after extraction
"""

from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

ZIP_MAGIC = b"PK\x03\x04"
SEVENZ_MAGIC = b"7z\xbc\xaf\x27\x1c"
RAR_MAGIC = b"Rar!\x1a\x07"
EXE_MAGIC = b"MZ"

MAX_TOTAL_BYTES = 2 * 1024**3
MAX_FILES = 3000
_DRIVE = re.compile(r"^[a-zA-Z]:")


class ArchiveError(RuntimeError):
    """Extraction failed or the archive is not supported."""


class UnsafeArchive(ArchiveError):
    """The archive tries to escape the destination directory."""


def sniff(path: Path) -> str:
    """Return ``zip`` / ``7z`` / ``rar`` / ``exe`` / ``unknown``."""
    try:
        with Path(path).open("rb") as stream:
            head = stream.read(8)
    except OSError:
        return "unknown"
    if head.startswith(ZIP_MAGIC):
        return "zip"
    if head.startswith(SEVENZ_MAGIC):
        return "7z"
    if head.startswith(RAR_MAGIC):
        return "rar"
    if head.startswith(EXE_MAGIC):
        return "exe"
    return "unknown"


def is_archive(path: Path) -> bool:
    return sniff(path) in {"zip", "7z"}


def _safe_target(root: Path, member: str) -> Path:
    name = (member or "").replace("\\", "/").strip()
    if not name:
        raise UnsafeArchive("empty member name")
    if name.startswith("/") or _DRIVE.match(name):
        raise UnsafeArchive(f"absolute path in archive: {member}")
    parts = [part for part in name.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise UnsafeArchive(f"path traversal in archive: {member}")
    return root.joinpath(*parts)


def extract(path: Path, dest: Path, *, max_total_bytes: int = MAX_TOTAL_BYTES) -> list[Path]:
    """Extract *path* into *dest* and return the extracted file list."""
    kind = sniff(path)
    dest.mkdir(parents=True, exist_ok=True)
    if kind == "zip":
        return _extract_zip(path, dest, max_total_bytes)
    if kind == "7z":
        return _extract_7z(path, dest, max_total_bytes)
    if kind == "rar":
        raise ArchiveError("RAR archives are not supported; open the source page instead")
    raise ArchiveError("not an archive")


def _extract_zip(path: Path, dest: Path, max_total_bytes: int) -> list[Path]:
    written: list[Path] = []
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_FILES:
                raise ArchiveError("archive contains too many files")
            if sum(info.file_size for info in infos) > max_total_bytes:
                raise ArchiveError("archive expands beyond the size limit")
            for info in infos:
                target = _safe_target(dest, info.filename)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as sink:
                    shutil.copyfileobj(source, sink, 1024 * 1024)
                written.append(target)
    except zipfile.BadZipFile as exc:
        raise ArchiveError(f"corrupt zip: {exc}") from exc
    return written


def _extract_7z(path: Path, dest: Path, max_total_bytes: int) -> list[Path]:
    try:
        import py7zr
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise ArchiveError("py7zr is required to extract .7z archives") from exc

    try:
        with py7zr.SevenZipFile(path, mode="r") as archive:
            names = archive.getnames()
            if len(names) > MAX_FILES:
                raise ArchiveError("archive contains too many files")
            for name in names:
                _safe_target(dest, name)
            archive.extractall(path=dest)
    except UnsafeArchive:
        raise
    except Exception as exc:  # noqa: BLE001 - py7zr raises a wide range
        raise ArchiveError(f"7z extraction failed: {exc}") from exc

    written: list[Path] = []
    total = 0
    for candidate in dest.rglob("*"):
        if candidate.is_file():
            total += candidate.stat().st_size
            written.append(candidate)
    if total > max_total_bytes:
        raise ArchiveError("archive expands beyond the size limit")
    return written

"""Bounded, non-following file inventories and atomic same-volume moves."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import stat
import sys
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from .models import ModError, ScanCancelled

MAX_FILES = 30_000
MAX_METADATA = 64 * 1024


def native(path: Path) -> Path:
    """Use extended Windows paths for large Mod trees and long Steam library paths."""
    if os.name != "nt" or str(path).startswith("\\\\?\\"):
        return path
    value = os.path.abspath(path)
    return Path("\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value)


def checkpoint(cancelled: Callable[[], bool] | None = None) -> None:
    if cancelled is not None and cancelled():
        raise ScanCancelled()


def relative(value: str) -> Path:
    path = PurePosixPath(value.replace("\\", "/"))
    if not value or any(ord(char) < 32 for char in value) or path.is_absolute() or any(part in {"..", "."} or ":" in part for part in path.parts):
        raise ModError("unsafe_path", value)
    if not path.parts or any(part.endswith((" ", ".")) for part in path.parts):
        raise ModError("unsafe_path", value)
    return Path(*path.parts)


def is_link(path: Path) -> bool:
    info = native(path).lstat()
    return stat.S_ISLNK(info.st_mode) or bool((getattr(info, "st_file_attributes", 0) or 0) & 0x400)


def checked(root: Path, value: str, *, shared: bool = True) -> Path:
    """Reject symlinks, junctions and hardlinked files, including existing ancestors."""
    root = native(root)
    path = root / relative(value)
    if root.exists() and is_link(root):
        raise ModError("linked_files", str(root))
    current = root
    for part in relative(value).parts:
        current = current / part
        if os.path.lexists(current):
            if is_link(current):
                raise ModError("linked_files", str(current))
            if shared and current.is_file() and current.stat().st_nlink > 1:
                raise ModError("linked_files", str(current))
    if not path.resolve().is_relative_to(root.resolve()):
        raise ModError("unsafe_path", str(path))
    return path


def snapshot(root: Path, entries: list[str], cancelled: Callable[[], bool] | None = None) -> dict[str, str]:
    root = native(root)
    result: dict[str, str] = {}

    def visit(path: Path, depth: int) -> None:
        checkpoint(cancelled)
        if depth > 48 or len(result) >= MAX_FILES:
            raise ModError("scan_limit", str(path))
        rel = path.relative_to(root).as_posix()
        checked(root, rel)
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            result[rel + "/"] = "directory"
            for child in sorted(path.iterdir()):
                visit(child, depth + 1)
        elif stat.S_ISREG(info.st_mode):
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    checkpoint(cancelled)
                    digest.update(chunk)
            after = path.stat()
            if (info.st_size, info.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ModError("files_changed", str(path))
            result[rel] = f"{info.st_size}:{digest.hexdigest()}"
        else:
            raise ModError("unsafe_path", str(path))

    for entry in entries:
        visit(checked(root, entry), 0)
    return result


def metadata(directory: Path, filenames: tuple[str, ...] = ("mod.manifest", "manifest.json")) -> tuple[str, str]:
    """Metadata decorates an already-scoped group; it never proves file ownership."""
    for filename in filenames:
        path = directory / filename
        try:
            if is_link(path) or path.stat().st_size > MAX_METADATA:
                continue
            raw = path.read_text(encoding="utf-8-sig")
            if filename.endswith(".json"):
                data = json.loads(raw)
                if not isinstance(data, dict):
                    continue
                name, version = data.get("Name", data.get("name", "")), data.get("Version", data.get("version", ""))
            else:
                if "<!DOCTYPE" in raw.upper() or "<!ENTITY" in raw.upper():
                    continue
                document = ET.fromstring(raw)
                name = document.findtext(".//name", "")
                version = document.findtext(".//version", "")
            if isinstance(name, str) and isinstance(version, (str, int, float)):
                return name.strip()[:240], str(version).strip()[:80]
        except (OSError, ValueError, ET.ParseError):
            continue
    return "", ""


def move(source: Path, destination: Path) -> None:
    source, destination = native(source), native(destination)
    if os.path.lexists(destination):
        raise ModError("destination_exists", str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Windows rename fails if the destination exists; unlike replace, it cannot overwrite it.
    os.rename(source, destination)


def game_running(directory: Path) -> bool:
    """Query process image paths without inspecting process memory or changing processes."""
    if sys.platform != "win32":
        return False
    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value:
        raise ModError("process_check_failed")
    entry = ProcessEntry()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        found = kernel.Process32FirstW(handle, ctypes.byref(entry))
        while found:
            process = kernel.OpenProcess(0x1000, False, entry.th32ProcessID)
            if process:
                try:
                    buffer, size = ctypes.create_unicode_buffer(32768), wintypes.DWORD(32768)
                    if kernel.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)):
                        if native(Path(buffer.value)).resolve().is_relative_to(native(directory).resolve()):
                            return True
                finally:
                    kernel.CloseHandle(process)
            found = kernel.Process32NextW(handle, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(handle)
    return False

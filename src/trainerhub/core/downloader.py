"""Fetching artefacts: extension detection, referer handling, cancellation."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from .archive import sniff
from .http import HttpClient
from .models import DownloadTarget
from .textutil import safe_folder_name

_KNOWN_SUFFIXES = {".zip": "zip", ".7z": "7z", ".rar": "rar", ".exe": "exe"}

ProgressFn = Callable[[int, int], None]


class DownloadError(RuntimeError):
    """A download could not be completed."""


class ExternalTarget(RuntimeError):
    """No direct artefact exists; the caller should open the page instead."""

    def __init__(self, url: str, note: str = "") -> None:
        super().__init__(note or "external download required")
        self.url = url
        self.note = note


class Downloader:
    def __init__(self, client: HttpClient, workdir: Path) -> None:
        self.client = client
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)

    def fetch(
        self,
        target: DownloadTarget,
        *,
        progress: ProgressFn | None = None,
        cancel: threading.Event | None = None,
    ) -> Path:
        if target.is_external:
            raise ExternalTarget(target.external_url or target.note, target.note)

        base = safe_folder_name(target.filename_hint or _basename(target.url), fallback="trainer")
        dest = self.workdir / base
        headers: dict[str, str] = dict(target.headers or {})
        if target.referer:
            headers.setdefault("Referer", target.referer)
        headers.setdefault("Accept", "*/*")

        self.client.download(target.url, dest, headers=headers, progress=progress, cancel=cancel)

        # Normalise the extension from the actual bytes, not from the URL.
        suffix = Path(base).suffix.lower()
        if suffix in _KNOWN_SUFFIXES:
            return dest
        kind = sniff(dest)
        extension = {"zip": ".zip", "7z": ".7z", "rar": ".rar", "exe": ".exe"}.get(kind, "")
        if not extension:
            return dest
        final = self.workdir / f"{base}{extension}"
        dest.replace(final)
        return final


def _basename(url: str) -> str:
    cleaned = (url or "").split("?")[0].rstrip("/")
    return cleaned.rsplit("/", 1)[-1] or "trainer"

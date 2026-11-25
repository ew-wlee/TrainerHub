"""Download pipeline worker: resolve → fetch → extract → archive."""

from __future__ import annotations

import queue
import shutil
import threading
import time
import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..core.archive import ArchiveError, extract, is_archive
from ..core.db import Database
from ..core.downloader import Downloader, ExternalTarget
from ..core.library import LibraryService
from ..core.models import CatalogItem, InstalledItem
from ..core.sources.base import BaseSource


class DownloadWorker(QThread):
    job_state = Signal(str, str, str)  # job_id, state, message
    job_progress = Signal(str, int, int)  # job_id, received, total
    job_external = Signal(str, str)  # job_id, external url
    job_done = Signal(object)  # InstalledItem
    job_failed = Signal(str, str)  # job_id, reason

    def __init__(
        self,
        db: Database,
        sources: dict[str, BaseSource],
        downloader: Downloader,
        library: LibraryService,
        *,
        concurrency: int = 2,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.sources = sources
        self.downloader = downloader
        self.library = library
        self.concurrency = max(1, min(4, concurrency))
        self.source_names: dict[str, str] = {}
        self._queue: queue.Queue[CatalogItem] = queue.Queue()
        self._cancel: dict[str, threading.Event] = {}
        self._cancel_lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    # -- public API -------------------------------------------------------
    def enqueue(self, item: CatalogItem) -> None:
        if self._stop.is_set():
            return
        job_id = f"{item.source_id}:{item.remote_id}"
        self.job_state.emit(job_id, "queued", "")
        self._queue.put(item)

    def cancel(self, job_id: str) -> None:
        with self._cancel_lock:
            event = self._cancel.get(job_id)
        if event:
            event.set()

    def cancel_all(self) -> None:
        with self._cancel_lock:
            for event in self._cancel.values():
                event.set()
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def stop(self) -> None:
        self._stop.set()
        self.cancel_all()

    # -- thread body ------------------------------------------------------
    def run(self) -> None:  # pragma: no cover - exercised through the UI
        self._threads = [
            threading.Thread(target=self._loop, name=f"trainerhub-dl-{i}", daemon=True)
            for i in range(self.concurrency)
        ]
        for thread in self._threads:
            thread.start()
        for thread in self._threads:
            thread.join()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                item = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            self._process(item)

    # -- one job ----------------------------------------------------------
    def _process(self, item: CatalogItem) -> None:
        job_id = f"{item.source_id}:{item.remote_id}"
        cancel = threading.Event()
        with self._cancel_lock:
            self._cancel[job_id] = cancel

        workdir = self.downloader.workdir / job_id.replace(":", "_")
        workdir.mkdir(parents=True, exist_ok=True)
        try:
            if self._stop.is_set():
                self.job_state.emit(job_id, "cancelled", "")
                return

            source = self.sources.get(item.source_id)
            if source is None:
                raise RuntimeError(f"source disabled: {item.source_id}")

            self.job_state.emit(job_id, "resolving", "")
            if not item.detail_loaded and source.requires_detail:
                item = source.fetch_detail(item)
                self.db.save_detail(item)

            if self.library.is_same_version_installed(item):
                record = self.library.installed(item)
                if record:
                    self.job_done.emit(record)
                    self.job_state.emit(job_id, "done", "already-installed")
                    return

            target = source.resolve_download(item)
            if target.is_external:
                self.job_external.emit(job_id, target.external_url or item.page_url)
                self.job_state.emit(job_id, "cancelled", "external")
                return

            self.job_state.emit(job_id, "downloading", "")
            last_emit = [0.0]

            def on_progress(received: int, total: int) -> None:
                now = time.monotonic()
                if now - last_emit[0] >= 0.08 or (total and received >= total):
                    last_emit[0] = now
                    self.job_progress.emit(job_id, received, total)

            path = self.downloader.fetch(target, progress=on_progress, cancel=cancel)

            self.job_state.emit(job_id, "extracting", "")
            files: list[Path]
            if is_archive(path):
                extract_dir = workdir / "extracted"
                files = extract(path, extract_dir)
                path.unlink(missing_ok=True)
                if not files:
                    raise ArchiveError("archive produced no files")
            else:
                files = [path]

            self.job_state.emit(job_id, "installing", "")
            record = self.library.install(
                item, files, source_name=self.source_names.get(item.source_id, item.source_id)
            )
            self.job_done.emit(record)
            self.job_state.emit(job_id, "done", "")
        except ExternalTarget as exc:
            self.job_external.emit(job_id, exc.url)
            self.job_state.emit(job_id, "cancelled", "external")
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            if cancel.is_set():
                self.job_state.emit(job_id, "cancelled", "")
            else:
                detail = str(exc) or exc.__class__.__name__
                if not isinstance(exc, (ArchiveError, RuntimeError)):
                    detail = f"{detail}\n{traceback.format_exc(limit=2)}"
                self.job_failed.emit(job_id, detail)
                self.job_state.emit(job_id, "failed", detail)
        finally:
            with self._cancel_lock:
                self._cancel.pop(job_id, None)
            shutil.rmtree(workdir, ignore_errors=True)


def installed_summary(record: InstalledItem) -> str:  # pragma: no cover - formatting helper
    return f"{record.game_name} · {record.version or '—'}"

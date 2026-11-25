"""Lazy detail loader: one queue, one thread, newest request wins."""

from __future__ import annotations

import queue
import threading

from PySide6.QtCore import QThread, Signal

from ..core.db import Database
from ..core.models import CatalogItem
from ..core.sources.base import BaseSource


class DetailWorker(QThread):
    detail_ready = Signal(object)  # CatalogItem
    detail_failed = Signal(str, str)  # key, message

    def __init__(self, db: Database, sources: dict[str, BaseSource], parent=None) -> None:
        super().__init__(parent)
        self.db = db
        self.sources = sources
        self._queue: queue.Queue[CatalogItem] = queue.Queue()
        self._stop = threading.Event()
        self._inflight = ""

    def submit(self, item: CatalogItem) -> None:
        if self._stop.is_set():
            return
        self._inflight = f"{item.source_id}:{item.remote_id}"
        self._queue.put(item)

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:  # pragma: no cover - exercised through the UI
        while not self._stop.is_set():
            try:
                item = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            source = self.sources.get(item.source_id)
            if source is None:
                continue
            try:
                enriched = source.fetch_detail(item)
                self.db.save_detail(enriched)
                self.detail_ready.emit(enriched)
            except Exception as exc:  # noqa: BLE001 - detail failures are non-fatal
                self.detail_failed.emit(f"{item.source_id}:{item.remote_id}", str(exc))

"""Background catalogue sync — one QThread, sequential per source."""

from __future__ import annotations

import threading
import traceback
from datetime import datetime

from PySide6.QtCore import QThread, Signal

from ..core.db import Database
from ..core.http import NetworkError, SourceStructureError
from ..core.sources.base import BaseSource


class SyncWorker(QThread):
    progress = Signal(str, int, int)  # source_id, page, items_in_page
    source_done = Signal(str, int)  # source_id, total items
    source_failed = Signal(str, str)  # source_id, message
    finished_all = Signal(int, int)  # total items, failed source count

    MAX_PAGES = 80

    def __init__(self, db: Database, sources: dict[str, BaseSource], parent=None) -> None:
        super().__init__(parent)
        self.db = db
        self.sources = sources
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:  # pragma: no cover - exercised through the UI
        total = 0
        failures = 0
        for source_id, source in self.sources.items():
            if self._stop.is_set():
                break
            count = 0
            try:
                for page in range(1, self.MAX_PAGES + 1):
                    if self._stop.is_set():
                        break
                    result = source.fetch_page(page)
                    if not result.items:
                        break
                    count += self.db.upsert_items(result.items)
                    self.progress.emit(source_id, page, len(result.items))
                    if len(result.items) < (source.page_size or 100):
                        break
                self.db.meta_set(f"synced:{source_id}", datetime.now().isoformat(timespec="seconds"))
                self.db.meta_set("last_sync", datetime.now().isoformat(timespec="seconds"))
                total += count
                self.source_done.emit(source_id, count)
            except (NetworkError, SourceStructureError, OSError) as exc:
                failures += 1
                self.source_failed.emit(source_id, str(exc))
            except Exception as exc:  # noqa: BLE001 - keep the loop alive
                failures += 1
                self.source_failed.emit(source_id, f"{exc}\n{traceback.format_exc(limit=2)}")
        self.finished_all.emit(total, failures)

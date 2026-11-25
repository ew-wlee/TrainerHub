"""Background live search against the source index."""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal

from ..core.remote_search import make_client, search_fling

LOGGER = logging.getLogger("trainerhub.search")


class SearchWorker(QThread):
    results = Signal(str, list)
    failed = Signal(str, str)

    def __init__(self, term: str, parent=None) -> None:
        super().__init__(parent)
        self.term = term
        self._client = None

    def run(self) -> None:  # noqa: D102 - QThread entry point
        try:
            self._client = make_client()
            items = search_fling(self.term, client=self._client)
        except Exception as exc:  # noqa: BLE001 - any transport error is recoverable
            if not self.isInterruptionRequested():
                LOGGER.info("remote search failed for %r: %s", self.term, exc)
                self.failed.emit(self.term, str(exc))
            return
        finally:
            if self._client is not None:
                self._client.close()
                self._client = None
        if self.isInterruptionRequested():
            return
        self.results.emit(self.term, items)

    def stop(self) -> None:
        self.requestInterruption()
        if self._client is not None:
            try:
                self._client.close()
            except Exception:  # noqa: BLE001 - closing twice is fine
                pass

"""Background live search with an immutable query context."""

from __future__ import annotations

import logging

import httpx
from PySide6.QtCore import QThread, Signal

from ..core.remote_search import make_client, search_fling_variants

LOGGER = logging.getLogger("trainerhub.search")


class SearchWorker(QThread):
    results = Signal(str, list)
    failed = Signal(str, str)
    context_results = Signal(int, str, str, object)
    context_failed = Signal(int, str, str, str)

    def __init__(
        self,
        term: str,
        parent=None,
        *,
        generation: int = 0,
        source_filter: str = "all",
        terms: list[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.term = term
        self.generation = generation
        self.source_filter = source_filter
        self.terms = tuple(terms or [term])

    def run(self) -> None:
        if self.isInterruptionRequested():
            return
        try:
            with make_client() as client:
                items = search_fling_variants(
                    self.terms, client=client, cancelled=self.isInterruptionRequested
                )
        except Exception as exc:
            if self.isInterruptionRequested():
                return
            if isinstance(exc, httpx.TimeoutException):
                category = "timeout"
            elif isinstance(exc, httpx.HTTPStatusError):
                category = "http"
            elif isinstance(exc, ValueError):
                category = "response"
            else:
                category = "network"
            LOGGER.info("remote search failed (%s)", category)
            self.failed.emit(self.term, category)
            self.context_failed.emit(self.generation, self.term, self.source_filter, category)
            return
        if not self.isInterruptionRequested():
            self.results.emit(self.term, items)
            self.context_results.emit(self.generation, self.term, self.source_filter, items)

    def stop(self) -> None:
        self.requestInterruption()

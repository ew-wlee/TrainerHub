"""Search worker context and cancellation, without real network traffic."""

from contextlib import nullcontext

import httpx

from trainerhub.core.models import CatalogItem
from trainerhub.workers import search_worker


def test_results_keep_query_generation_and_source(monkeypatch):
    item = CatalogItem("fling", "1", "Hades Trainer", "Hades")
    monkeypatch.setattr(search_worker, "make_client", lambda: nullcontext(object()))
    received_terms = []

    def search(terms, **kwargs):
        received_terms.extend(terms)
        return [item]

    monkeypatch.setattr(search_worker, "search_fling_variants", search)
    worker = search_worker.SearchWorker("哈迪斯", generation=7, source_filter="xiaoxing", terms=["Hades"])
    received = []
    worker.context_results.connect(lambda *args: received.append(args))
    worker.run()
    assert received_terms == ["Hades"]
    assert received == [(7, "哈迪斯", "xiaoxing", [item])]


def test_failure_is_classified_without_logging_query(monkeypatch):
    monkeypatch.setattr(search_worker, "make_client", lambda: nullcontext(object()))

    def fail(*args, **kwargs):
        raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr(search_worker, "search_fling_variants", fail)
    worker = search_worker.SearchWorker("Hades", generation=3)
    failures = []
    worker.context_failed.connect(lambda *args: failures.append(args))
    worker.run()
    assert failures == [(3, "Hades", "all", "timeout")]


def test_interruption_while_searching_drops_results(monkeypatch):
    monkeypatch.setattr(search_worker, "make_client", lambda: nullcontext(object()))
    worker = search_worker.SearchWorker("Hades")
    received = []
    worker.context_results.connect(lambda *args: received.append(args))
    monkeypatch.setattr(worker, "isInterruptionRequested", lambda: True)
    worker.run()
    assert received == []

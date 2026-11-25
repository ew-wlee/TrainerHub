from __future__ import annotations

from trainerhub.core.models import CatalogItem
from trainerhub.core.search import SearchEngine


def test_chinese_query_matches_chinese_entry(sample_items: list[CatalogItem]) -> None:
    engine = SearchEngine(sample_items)
    hits = engine.query("黑神话")
    assert hits and hits[0].item.game_name == "黑神话：悟空"


def test_pinyin_initials_cross_source(sample_items: list[CatalogItem]) -> None:
    engine = SearchEngine(sample_items)
    hits = engine.query("hshwk")
    assert hits
    assert hits[0].item.remote_id == "65"


def test_english_query_matches_english_entry(sample_items: list[CatalogItem]) -> None:
    engine = SearchEngine(sample_items)
    hits = engine.query("elden")
    assert hits and hits[0].item.game_name == "Elden Ring"


def test_source_filter(sample_items: list[CatalogItem]) -> None:
    engine = SearchEngine(sample_items)
    hits = engine.query("", source_id="xiaoxing")
    assert len(hits) == 1
    assert hits[0].item.source_id == "xiaoxing"


def test_unknown_query_falls_back_to_fuzzy(sample_items: list[CatalogItem]) -> None:
    engine = SearchEngine(sample_items)
    hits = engine.query("eldenrng")
    assert any(hit.item.game_name == "Elden Ring" for hit in hits)


def test_empty_query_orders_by_recency(sample_items: list[CatalogItem]) -> None:
    engine = SearchEngine(sample_items)
    hits = engine.query("")
    assert hits[0].item.updated_at >= hits[-1].item.updated_at

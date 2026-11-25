"""Remote search parsing: no network, fixed WordPress payloads."""

from __future__ import annotations

from trainerhub.core.remote_search import parse_posts


def post(pid: int, title: str, date: str = "2026-11-20T10:00:00") -> dict:
    return {
        "id": pid,
        "date": date,
        "modified": date,
        "link": f"https://flingtrainer.com/trainer/{pid}/",
        "title": {"rendered": title},
    }


def test_keeps_only_matching_trainer_posts() -> None:
    payload = [
        post(1, "Hades II Trainer"),
        post(2, "Hades Trainer"),
        post(3, "My Trainers Archive"),
        post(4, "Unrelated Article"),
        post(5, "Hades Soundtrack"),
    ]
    items = parse_posts(payload, "hades")
    assert [item.game_name for item in items] == ["Hades II", "Hades"]
    assert all(item.source_id == "fling" for item in items)


def test_strips_trainer_suffix_and_decodes_entities() -> None:
    payload = [post(10, "Baldur&#8217;s Gate 3 Trainer")]
    items = parse_posts(payload, "baldur")
    assert len(items) == 1
    assert items[0].game_name == "Baldur\u2019s Gate 3"
    assert items[0].title.endswith("Trainer")


def test_deduplicates_by_game_name_and_respects_limit() -> None:
    payload = [post(1, "Hades Trainer"), post(2, "Hades II Trainer"), post(3, "Hades Trainer")]
    items = parse_posts(payload, "hades", limit=1)
    assert len(items) == 1
    assert items[0].game_name == "Hades"


def test_ignores_posts_without_the_query() -> None:
    payload = [post(1, "Atomic Heart Trainer"), post(2, "Europa Universalis V Trainer")]
    assert parse_posts(payload, "hades") == []


def test_short_or_empty_query_returns_nothing() -> None:
    payload = [post(1, "Hades Trainer")]
    assert parse_posts(payload, "") == []
    assert parse_posts(payload, " ") == []
    assert parse_posts({"not": "a list"}, "hades") == []

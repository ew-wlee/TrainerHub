"""Remote search parsing: no network, fixed WordPress payloads."""

from __future__ import annotations

import httpx
import pytest

from trainerhub.core.remote_search import (
    InvalidSearchResponse,
    parse_posts,
    search_fling,
    search_fling_variants,
)


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


@pytest.mark.parametrize("title", [None, "text", [], {"rendered": []}])
def test_malformed_titles_are_ignored(title) -> None:
    payload = post(1, "Hades Trainer")
    payload["title"] = title
    assert parse_posts([payload], "hades") == []


@pytest.mark.parametrize(
    "link",
    [
        "https://evil.test/hades/",
        "javascript:alert(1)",
        "https://flingtrainer.com@evil.test/hades/",
        "http://flingtrainer.com/trainer/hades/",
        "https://flingtrainer.com:9999/hades/",
        None,
    ],
)
def test_untrusted_links_are_ignored(link) -> None:
    payload = post(1, "Hades Trainer")
    payload["link"] = link
    assert parse_posts([payload], "hades") == []


@pytest.mark.parametrize("pid", [None, True, -1, "1"])
def test_invalid_ids_are_ignored(pid) -> None:
    payload = post(1, "Hades Trainer")
    payload["id"] = pid
    assert parse_posts([payload], "hades") == []


def test_request_uses_real_endpoint_and_query() -> None:
    def handle(request):
        assert request.url.host == "flingtrainer.com"
        assert request.url.params["search"] == "Hades"
        assert request.url.params["_fields"] == "id,date,modified,link,title"
        return httpx.Response(200, json=[post(1, "Hades Trainer")])

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        assert search_fling("Hades", client=client)[0].remote_id == "1"


@pytest.mark.parametrize("payload", [{"code": "unavailable"}, None, "not an article list"])
def test_invalid_response_not_reported_as_no_match(payload) -> None:
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as client,
        pytest.raises(InvalidSearchResponse),
    ):
        search_fling("Hades", client=client)


def test_invalid_json_and_http_errors_are_not_empty_results() -> None:
    for response, error in [
        (httpx.Response(200, text="<html>"), ValueError),
        (httpx.Response(503), httpx.HTTPStatusError),
    ]:
        with (
            httpx.Client(transport=httpx.MockTransport(lambda _, r=response: r)) as client,
            pytest.raises(error),
        ):
            search_fling("Hades", client=client)


def test_alias_search_is_bounded_and_deduplicated() -> None:
    calls = []

    def handle(request):
        calls.append(request.url.params["search"])
        return httpx.Response(200, json=[post(1, "Hades Trainer")])

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        items = search_fling_variants(["哈迪斯", "Hades", "hades", "Hades II", "fourth"], client=client)
    assert calls == ["哈迪斯", "Hades", "Hades II"]
    assert len(items) == 1


def test_cancelled_variant_search_does_not_request() -> None:
    def fail(_):
        raise AssertionError("Cancelled search must not request")

    with httpx.Client(transport=httpx.MockTransport(fail)) as client:
        assert search_fling_variants(["Hades"], client=client, cancelled=lambda: True) == []


def test_variant_failure_never_masquerades_as_missing_fling() -> None:
    def handle(request):
        return httpx.Response(503 if request.url.params["search"] == "Hades" else 200, json=[])

    with httpx.Client(transport=httpx.MockTransport(handle)) as client, pytest.raises(httpx.HTTPStatusError):
        search_fling_variants(["哈迪斯", "Hades"], client=client)


def test_zero_limit_returns_nothing() -> None:
    assert parse_posts([post(1, "Hades Trainer")], "Hades", limit=0) == []

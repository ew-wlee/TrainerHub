from __future__ import annotations

from typing import Any

from trainerhub.core.sources.fling import FlingSource, parse_size
from trainerhub.core.sources.xiaoxing import XiaoxingSource, parse_content


class StubClient:
    """Minimal stand-in for HttpClient so adapter tests stay offline."""

    def __init__(self, json_payload: Any = None, text: str = "") -> None:
        self._json = json_payload
        self._text = text
        self.calls: list[str] = []

    def get_json(self, url: str, params: dict | None = None, **_: Any) -> Any:
        self.calls.append(url)
        return self._json

    def get_text(self, url: str, **_: Any) -> str:
        self.calls.append(url)
        return self._text


def test_fling_list_parsing(fling_posts: list[dict]) -> None:
    source = FlingSource("https://flingtrainer.com", StubClient(json_payload=fling_posts))
    page = source.fetch_page(1)

    assert len(page.items) == 2
    first = page.items[0]
    assert first.game_name == "Ashes of the Singularity II"
    assert first.remote_id == "43551"
    assert first.supports_direct_download is True
    assert first.updated_at == "2026-11-10"


def test_fling_detail_parsing(fling_posts: list[dict], fling_detail_html: str) -> None:
    client = StubClient(json_payload={"content": {"rendered": "<p>3 Options</p>"}}, text=fling_detail_html)
    source = FlingSource("https://flingtrainer.com", client)
    list_source = FlingSource("https://flingtrainer.com", StubClient(json_payload=fling_posts))
    base = list_source.fetch_page(1).items[0]

    detail = source.fetch_detail(base)
    assert detail.version == "Plus 11"
    assert detail.file_size == 530432
    assert detail.detail_loaded is True
    assert detail.image_url.endswith("ace.jpg")


def test_fling_resolve_download_points_at_downloads_endpoint(fling_detail_html: str) -> None:
    source = FlingSource("https://flingtrainer.com", StubClient(text=fling_detail_html))
    from trainerhub.core.models import CatalogItem

    item = CatalogItem(
        source_id="fling", remote_id="1", title="A", game_name="A", page_url="https://x/trainer/a/"
    )
    target = source.resolve_download(item)
    assert target.kind == "direct"
    assert "/downloads/" in target.url
    assert target.filename_hint.endswith("Trainer-FLiNG")


def test_xiaoxing_list_parsing(xiaoxing_posts: list[dict]) -> None:
    source = XiaoxingSource("https://www.xiaoxingjie.com", StubClient(json_payload=xiaoxing_posts))
    page = source.fetch_page(1)

    assert len(page.items) == 1
    item = page.items[0]
    assert item.game_name == "黑神话：悟空"
    assert item.game_alias == "Black Myth: Wukong"
    assert item.version == "v1.7.0"
    assert item.supports_direct_download is False
    assert item.detail_loaded is True
    assert item.options_count >= 5


def test_xiaoxing_is_external_download(xiaoxing_posts: list[dict]) -> None:
    source = XiaoxingSource("https://www.xiaoxingjie.com", StubClient(json_payload=xiaoxing_posts))
    item = source.fetch_page(1).items[0]
    target = source.resolve_download(item)
    assert target.kind == "external"
    assert target.external_url == item.page_url


def test_parse_content_extracts_options_and_support() -> None:
    options, supported = parse_content(
        "<p>支持版本：所有PC平台版本游戏</p><p>修改器功能：</p>"
        "<p>无限生命(Alt+1)          无限气力(Alt+2)</p>"
    )
    assert "无限生命(Alt+1)" in options
    assert "无限气力(Alt+2)" in options
    assert supported.startswith("所有PC平台")


def test_parse_size() -> None:
    assert parse_size("518 KB") == 530432
    assert parse_size("1.5 MB") == 1572864
    assert parse_size("n/a") == 0

"""FLiNG Trainer adapter (flingtrainer.com — WordPress).

Two-step design on purpose: the REST list endpoint is cheap and stable, while
attachments (file name, size, download URL) only exist in the detail page HTML.
"""

from __future__ import annotations

import html
import re
from datetime import date
from typing import Any, ClassVar

from ..http import SourceStructureError
from ..models import CatalogItem, DownloadTarget, SourcePage
from ..textutil import normalize_date, split_title
from .base import BaseSource

_OPTION_LINE = re.compile(
    r"^(?:(?:Ctrl|Alt|Shift)\+)*(?:Num\s*(?:\d+)|F\d+|\d+)\s*[\u2013\u2014\-]\s*(.+)$"
)
_INTRO_VERSION = re.compile(r"Game\s*Version\s*:\s*([^<\u00b7\n]+)", re.IGNORECASE)
_INTRO_UPDATED = re.compile(r"Last\s*Updated\s*:\s*([\d./-]+)", re.IGNORECASE)
_INTRO_OPTIONS = re.compile(r"(\d+)\s*Options?", re.IGNORECASE)
_SIZE = re.compile(r"([\d.]+)\s*(B|KB|MB|GB)", re.IGNORECASE)
_PLUS = re.compile(r"Plus\.?\s*(\d+)", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_BREAK = re.compile(r"<br\s*/?>|</p>|</li>|</h\d>", re.IGNORECASE)
_IMG = re.compile(r'<img[^>]+src="([^"]+)"', re.IGNORECASE)
_ATTACHMENT_ROW = re.compile(
    r'<a[^>]+href="(?P<url>[^"]*/downloads/[^"]+)"[^>]*title="(?P<file>[^"]*)"'
    r'.*?<td class="attachment-date">(?P<date>[^<]*)</td>'
    r".*?<td class=\"attachment-size\">(?P<size>[^<]*)</td>",
    re.IGNORECASE | re.DOTALL,
)
_OG_IMAGE = re.compile(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', re.IGNORECASE)


def parse_size(text: str) -> int:
    match = _SIZE.search(text or "")
    if not match:
        return 0
    value = float(match.group(1))
    unit = match.group(2).upper()
    factor = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}[unit]
    return int(value * factor)


def parse_options(content_html: str) -> tuple[list[str], str, str, int]:
    """Return ``(options, game_version, updated_at, advertised_count)``."""
    text = _BREAK.sub("\n", content_html or "")
    text = html.unescape(_TAG.sub("", text))
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    game_version = ""
    updated_at = ""
    count = 0
    options: list[str] = []
    for line in lines:
        if not game_version:
            match = _INTRO_VERSION.search(line)
            if match:
                game_version = match.group(1).strip(" .;,")
        if not updated_at:
            match = _INTRO_UPDATED.search(line)
            if match:
                updated_at = normalize_date(match.group(1))
        if not count:
            match = _INTRO_OPTIONS.search(line)
            if match:
                count = int(match.group(1))
        cleaned = re.sub(r"^\d+\.\s*", "", line)
        if _OPTION_LINE.match(cleaned) and len(cleaned) <= 120:
            if cleaned not in options:
                options.append(cleaned)
    if not count and options:
        count = len(options)
    return options[:60], game_version, updated_at, count


class FlingSource(BaseSource):
    id: ClassVar[str] = "fling"
    name_key: ClassVar[str] = "source.fling"
    homepage: ClassVar[str] = "https://flingtrainer.com"
    supports_direct_download: ClassVar[bool] = True
    requires_detail: ClassVar[bool] = True

    # -- listing ----------------------------------------------------------
    def fetch_page(self, page: int = 1, page_size: int | None = None) -> SourcePage:
        size = min(100, page_size or self.page_size)
        payload = self.client.get_json(
            f"{self.base_url}/wp-json/wp/v2/posts",
            params={
                "per_page": size,
                "page": max(1, page),
                "_fields": "id,date,modified,slug,link,title",
            },
        )
        if not isinstance(payload, list):
            raise SourceStructureError("FLiNG: unexpected list payload")

        items: list[CatalogItem] = []
        for post in payload:
            if not isinstance(post, dict):
                continue
            raw_title = html.unescape(_TAG.sub("", post.get("title", {}).get("rendered", "") or ""))
            name, alias, version = split_title(raw_title)
            if not name:
                continue
            published = str(post.get("date") or "")
            modified = str(post.get("modified") or "") or published
            items.append(
                CatalogItem(
                    source_id=self.id,
                    remote_id=str(post.get("id") or post.get("slug") or ""),
                    title=raw_title.strip(),
                    game_name=name,
                    game_alias=alias,
                    version=version,
                    page_url=str(post.get("link") or ""),
                    updated_at=normalize_date(modified) or normalize_date(published),
                    published_at=normalize_date(published),
                    supports_direct_download=True,
                )
            )
        total_pages = 1
        if len(items) >= size:
            total_pages = max(1, page) + 1
        return SourcePage(items=items, page=page, total_pages=total_pages, total_items=0)

    # -- detail ------------------------------------------------------------
    def fetch_detail(self, item: CatalogItem) -> CatalogItem:
        data = self._detail_json(item)
        content = data.get("content", {}).get("rendered", "") if isinstance(data, dict) else ""
        options, game_version, updated_at, advertised = parse_options(content)

        page_html = ""
        if item.page_url:
            try:
                page_html = self.client.get_text(item.page_url)
            except Exception:  # noqa: BLE001 - detail page is optional for listing
                page_html = ""

        attachment = self._first_attachment(page_html)
        result = item.clone()
        result.options = tuple(options)
        result.options_count = advertised or len(options)
        result.game_version = game_version or result.game_version
        result.updated_at = updated_at or result.updated_at
        if attachment:
            filename, file_url, added, size_text = attachment
            result.file_size = parse_size(size_text)
            if added:
                result.updated_at = normalize_date(added) or result.updated_at
            plus = _PLUS.search(filename)
            if plus:
                result.version = f"Plus {plus.group(1)}"
            result.summary = filename
            if not result.image_url:
                result.image_url = self._og_image(page_html)
        if not result.image_url:
            match = _IMG.search(content or "")
            if match:
                result.image_url = match.group(1)
        result.detail_loaded = True
        result.supports_direct_download = True
        return result

    def _detail_json(self, item: CatalogItem) -> dict[str, Any]:
        payload = self.client.get_json(
            f"{self.base_url}/wp-json/wp/v2/posts/{item.remote_id}",
            params={"_fields": "id,content,excerpt,modified"},
        )
        if not isinstance(payload, dict) or "content" not in payload:
            raise SourceStructureError("FLiNG: unexpected detail payload")
        return payload

    @staticmethod
    def _og_image(page_html: str) -> str:
        match = _OG_IMAGE.search(page_html or "")
        return match.group(1) if match else ""

    @staticmethod
    def _first_attachment(page_html: str) -> tuple[str, str, str, str] | None:
        match = _ATTACHMENT_ROW.search(page_html or "")
        if not match:
            return None
        return (
            html.unescape(match.group("file")),
            match.group("url"),
            match.group("date").strip(),
            match.group("size").strip(),
        )

    # -- download ----------------------------------------------------------
    def resolve_download(self, item: CatalogItem) -> DownloadTarget:
        page_html = self.client.get_text(item.page_url) if item.page_url else ""
        attachment = self._first_attachment(page_html)
        if not attachment:
            return DownloadTarget(kind="external", external_url=item.page_url, note="attachment-not-found")
        filename, url, _added, _size = attachment
        return DownloadTarget(
            url=url,
            kind="direct",
            filename_hint=filename,
            referer=item.page_url,
            note=f"fetched {date.today().isoformat()}",
        )



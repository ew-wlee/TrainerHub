"""小幸修改器 adapter (www.xiaoxingjie.com — WordPress).

Titles carry both names and the version:

    黑神话：悟空 多功能修改器 V1.7.0  /  Black Myth: Wukong Trainer

Downloads are distributed through 百度网盘 / MediaFire, so this source is
index-and-jump: we never pretend to have a direct artefact.
"""

from __future__ import annotations

import html
import re
from typing import ClassVar

from ..http import SourceStructureError
from ..models import CatalogItem, DownloadTarget, SourcePage
from ..textutil import extract_version, normalize_date, split_title
from .base import BaseSource

_TAG = re.compile(r"<[^>]+>")
_BREAK = re.compile(r"<br\s*/?>|</p>|</li>|</h\d>", re.IGNORECASE)
_IMG = re.compile(r'<img[^>]+src="([^"]+)"', re.IGNORECASE)
_SUPPORT = re.compile(r"支持版本[:：]\s*([^\n<]+)")
_FEATURES_HEADER = re.compile(r"修改器功能|功能[:：]", re.IGNORECASE)
_OPTION_SPLIT = re.compile(r"\s{2,}|\u3000+")
_HOTKEY = re.compile(r"\((?:Alt|Ctrl|Shift|Num)[^)]*\)|\b(?:Alt|Ctrl|Shift)\+\w+", re.IGNORECASE)


def parse_content(content_html: str) -> tuple[list[str], str]:
    """Return ``(options, supported_game_version)`` from a post body."""
    text = _BREAK.sub("\n", content_html or "")
    text = html.unescape(_TAG.sub("", text))
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    game_version = ""
    options: list[str] = []
    collecting = False
    for line in lines:
        if not game_version:
            match = _SUPPORT.search(line)
            if match:
                game_version = match.group(1).strip(" .;,")
        if _FEATURES_HEADER.search(line):
            collecting = True
            continue
        if not collecting:
            continue
        if re.match(r"^\d{4}[/-]\d{1,2}[/-]\d{1,2}", line):  # changelog starts
            break
        for part in _OPTION_SPLIT.split(line):
            candidate = part.strip(" 　·-")
            if not candidate or len(candidate) > 40:
                continue
            if _HOTKEY.search(candidate) or re.search(r"[\u4e00-\u9fff]{2,}", candidate):
                if candidate not in options:
                    options.append(candidate)
    return options[:80], game_version


class XiaoxingSource(BaseSource):
    id: ClassVar[str] = "xiaoxing"
    name_key: ClassVar[str] = "source.xiaoxing"
    homepage: ClassVar[str] = "https://www.xiaoxingjie.com"
    supports_direct_download: ClassVar[bool] = False
    requires_detail: ClassVar[bool] = False

    def fetch_page(self, page: int = 1, page_size: int | None = None) -> SourcePage:
        size = min(100, page_size or self.page_size)
        payload = self.client.get_json(
            f"{self.base_url}/wp-json/wp/v2/posts",
            params={
                "per_page": size,
                "page": max(1, page),
                "_fields": "id,date,modified,slug,link,title,content",
            },
        )
        if not isinstance(payload, list):
            raise SourceStructureError("XiaoXing: unexpected list payload")

        items: list[CatalogItem] = []
        for post in payload:
            if not isinstance(post, dict):
                continue
            raw_title = html.unescape(_TAG.sub("", post.get("title", {}).get("rendered", "") or ""))
            name, alias, version = split_title(raw_title)
            if not name:
                continue
            # Skip the site's own pages ("最近更新", series index pages): a real
            # trainer always carries a version or the word 修改器 / Trainer.
            if not version and "修改器" not in raw_title and "Trainer" not in raw_title:
                continue
            content = post.get("content", {}).get("rendered", "") or ""
            options, game_version = parse_content(content)
            image = _IMG.search(content)
            published = str(post.get("date") or "")
            modified = str(post.get("modified") or "") or published
            items.append(
                CatalogItem(
                    source_id=self.id,
                    remote_id=str(post.get("id") or ""),
                    title=raw_title.strip(),
                    game_name=name,
                    game_alias=alias,
                    version=version or extract_version(raw_title),
                    page_url=str(post.get("link") or ""),
                    image_url=image.group(1) if image else "",
                    options_count=len(options),
                    game_version=game_version,
                    updated_at=normalize_date(modified),
                    published_at=normalize_date(published),
                    options=tuple(options),
                    supports_direct_download=False,
                    detail_loaded=True,
                )
            )
        total_pages = 1
        if len(items) >= size:
            total_pages = max(1, page) + 1
        return SourcePage(items=items, page=page, total_pages=total_pages, total_items=0)

    def resolve_download(self, item: CatalogItem) -> DownloadTarget:
        return DownloadTarget(
            kind="external",
            external_url=item.page_url,
            note="netdisk",  # 百度网盘 / MediaFire — open the page instead
        )

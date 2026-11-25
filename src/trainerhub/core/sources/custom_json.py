"""A user-supplied JSON index.

Accepts either a bare array or ``{"items": [...]}``. Field names are matched
leniently so a hand-written index does not need to mirror our dataclass.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from ..http import SourceStructureError
from ..models import CatalogItem, DownloadTarget, SourcePage
from ..textutil import normalize_date, split_title
from .base import BaseSource

_ALIASES: dict[str, tuple[str, ...]] = {
    "remote_id": ("remote_id", "id", "slug"),
    "title": ("title", "name"),
    "game_name": ("game_name", "game", "name"),
    "game_alias": ("game_alias", "alias", "name_en"),
    "version": ("version",),
    "page_url": ("page_url", "url", "link"),
    "image_url": ("image_url", "image", "cover"),
    "download_url": ("download_url", "download", "file"),
    "updated_at": ("updated_at", "updated", "date", "modified"),
    "options_count": ("options_count", "options"),
    "game_version": ("game_version", "supported_version"),
    "file_size": ("file_size", "size"),
}

_TAG = re.compile(r"<[^>]+>")


def _pick(record: dict[str, Any], field: str) -> Any:
    for key in _ALIASES[field]:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return None


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class CustomJsonSource(BaseSource):
    id: ClassVar[str] = "custom"
    name_key: ClassVar[str] = "source.custom"
    homepage: ClassVar[str] = ""
    supports_direct_download: ClassVar[bool] = True
    requires_detail: ClassVar[bool] = False

    def fetch_page(self, page: int = 1, page_size: int | None = None) -> SourcePage:
        payload = self.client.get_json(self.base_url)
        if isinstance(payload, dict):
            records = payload.get("items") or payload.get("data") or []
        else:
            records = payload
        if not isinstance(records, list):
            raise SourceStructureError("Custom: index must be a JSON array")

        items: list[CatalogItem] = []
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            raw_title = _TAG.sub("", str(_pick(record, "title") or "")).strip()
            name = str(_pick(record, "game_name") or "").strip()
            alias = str(_pick(record, "game_alias") or "").strip()
            if not name:
                name, alias, _ = split_title(raw_title)
            if not name:
                continue
            download_url = str(_pick(record, "download_url") or "")
            items.append(
                CatalogItem(
                    source_id=self.id,
                    remote_id=str(_pick(record, "remote_id") or index),
                    title=raw_title or name,
                    game_name=name,
                    game_alias=alias,
                    version=str(_pick(record, "version") or ""),
                    page_url=str(_pick(record, "page_url") or ""),
                    image_url=str(_pick(record, "image_url") or ""),
                    options_count=_as_int(_pick(record, "options_count")),
                    game_version=str(_pick(record, "game_version") or ""),
                    file_size=_as_int(_pick(record, "file_size")),
                    updated_at=normalize_date(str(_pick(record, "updated_at") or "")),
                    summary=download_url,
                    supports_direct_download=bool(download_url),
                    detail_loaded=True,
                )
            )
        return SourcePage(items=items, page=1, total_pages=1, total_items=len(items))

    def resolve_download(self, item: CatalogItem) -> DownloadTarget:
        if item.summary:
            return DownloadTarget(url=item.summary, kind="direct", filename_hint=item.game_name)
        return DownloadTarget(kind="external", external_url=item.page_url)

"""Domain models shared by the core layer, workers and UI."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(slots=True)
class CatalogItem:
    """A single trainer entry as it appears in the catalogue."""

    source_id: str
    remote_id: str
    title: str
    game_name: str
    game_alias: str = ""
    version: str = ""
    page_url: str = ""
    image_url: str = ""
    options_count: int = 0
    game_version: str = ""
    file_size: int = 0
    updated_at: str = ""
    published_at: str = ""
    summary: str = ""
    options: tuple[str, ...] = ()
    supports_direct_download: bool = False
    detail_loaded: bool = False

    @property
    def key(self) -> tuple[str, str]:
        return (self.source_id, self.remote_id)

    @property
    def display_alias(self) -> str:
        """The secondary name shown under the main title, when it differs."""
        alias = (self.game_alias or "").strip()
        name = (self.game_name or "").strip()
        if not alias or alias.casefold() == name.casefold():
            return ""
        return alias

    def clone(self, **changes: Any) -> CatalogItem:
        """Copy the item, optionally overriding fields."""
        return replace(self, **changes)

    def to_row(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "remote_id": self.remote_id,
            "title": self.title,
            "game_name": self.game_name,
            "game_alias": self.game_alias,
            "version": self.version,
            "page_url": self.page_url,
            "image_url": self.image_url,
            "options_count": int(self.options_count),
            "game_version": self.game_version,
            "file_size": int(self.file_size),
            "updated_at": self.updated_at,
            "published_at": self.published_at,
            "summary": self.summary,
            "options_json": json.dumps(list(self.options), ensure_ascii=False),
            "supports_direct_download": int(self.supports_direct_download),
            "detail_loaded": int(self.detail_loaded),
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> CatalogItem:
        try:
            options = tuple(json.loads(row.get("options_json") or "[]"))
        except (ValueError, TypeError):
            options = ()
        return cls(
            source_id=row["source_id"],
            remote_id=row["remote_id"],
            title=row["title"],
            game_name=row["game_name"],
            game_alias=row.get("game_alias") or "",
            version=row.get("version") or "",
            page_url=row.get("page_url") or "",
            image_url=row.get("image_url") or "",
            options_count=int(row.get("options_count") or 0),
            game_version=row.get("game_version") or "",
            file_size=int(row.get("file_size") or 0),
            updated_at=row.get("updated_at") or "",
            published_at=row.get("published_at") or "",
            summary=row.get("summary") or "",
            options=options,
            supports_direct_download=bool(row.get("supports_direct_download")),
            detail_loaded=bool(row.get("detail_loaded")),
        )


@dataclass(slots=True)
class SourcePage:
    """One page of results coming back from a source adapter."""

    items: list[CatalogItem] = field(default_factory=list)
    page: int = 1
    total_pages: int = 1
    total_items: int = 0


@dataclass(slots=True)
class DownloadTarget:
    """Where the bytes for a trainer actually live."""

    url: str = ""
    kind: str = "direct"  # "direct" | "external"
    filename_hint: str = ""
    referer: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    external_url: str = ""
    note: str = ""

    @property
    def is_external(self) -> bool:
        return self.kind == "external" or not self.url


@dataclass(slots=True)
class InstalledItem:
    source_id: str
    remote_id: str
    game_name: str
    version: str
    path: str
    size_bytes: int = 0
    options_count: int = 0
    page_url: str = ""
    installed_at: str = ""

    @property
    def key(self) -> tuple[str, str]:
        return (self.source_id, self.remote_id)


@dataclass(slots=True)
class DownloadJob:
    """Runtime state of one download, owned by the download worker."""

    item: CatalogItem
    state: str = "queued"  # queued | resolving | downloading | extracting | done | failed | cancelled
    received: int = 0
    total: int = 0
    message: str = ""
    dest_path: str = ""

    @property
    def job_id(self) -> str:
        return f"{self.item.source_id}:{self.item.remote_id}"

    @property
    def progress(self) -> float:
        if self.total <= 0:
            return 0.0
        return min(1.0, self.received / self.total)

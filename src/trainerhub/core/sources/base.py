"""Source adapter contract.

Every catalogue source implements the same three steps:

* ``fetch_page``    — paginated *list* data (cheap, keeps the index fresh)
* ``fetch_detail``  — richer data for one entry (lazy, cached)
* ``resolve_download`` — where the bytes actually live

Capabilities are declared as class attributes so the UI never has to special
case a source by name.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from ..http import HttpClient
from ..models import CatalogItem, DownloadTarget, SourcePage


class SourceError(RuntimeError):
    """Any recoverable adapter failure surfaced to the UI."""


class BaseSource(ABC):
    id: ClassVar[str] = ""
    name_key: ClassVar[str] = ""
    homepage: ClassVar[str] = ""
    supports_direct_download: ClassVar[bool] = False
    requires_detail: ClassVar[bool] = True
    page_size: ClassVar[int] = 100

    def __init__(self, base_url: str, client: HttpClient) -> None:
        self.base_url = (base_url or self.homepage).rstrip("/")
        self.client = client

    def __repr__(self) -> str:  # pragma: no cover - debugging sugar
        return f"<{type(self).__name__} {self.base_url}>"

    @abstractmethod
    def fetch_page(self, page: int = 1, page_size: int | None = None) -> SourcePage:
        """Return one page of catalogue entries."""

    def fetch_detail(self, item: CatalogItem) -> CatalogItem:
        """Enrich a single entry. Default: nothing to do."""
        return item

    def resolve_download(self, item: CatalogItem) -> DownloadTarget:
        """Resolve a downloadable artefact, or an external fallback target."""
        return DownloadTarget(kind="external", external_url=item.page_url)


def build_sources(config, client: HttpClient) -> dict[str, BaseSource]:
    """Instantiate every enabled adapter for the given config."""
    from .custom_json import CustomJsonSource
    from .fling import FlingSource
    from .xiaoxing import XiaoxingSource

    catalogue: dict[str, type[BaseSource]] = {
        FlingSource.id: FlingSource,
        XiaoxingSource.id: XiaoxingSource,
        CustomJsonSource.id: CustomJsonSource,
    }
    sources: dict[str, BaseSource] = {}
    for source_id, cls in catalogue.items():
        if not config.source_enabled(source_id):
            continue
        if cls is CustomJsonSource:
            index_url = str(config.get("sources.custom.index_url", "")).strip()
            if not index_url:
                continue
            sources[source_id] = cls(index_url, client)
        else:
            sources[source_id] = cls(config.source_base_url(source_id), client)
    return sources

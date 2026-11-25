"""Compare what is installed against what the catalogue now advertises."""

from __future__ import annotations

from dataclasses import dataclass

from .db import Database
from .models import CatalogItem, InstalledItem
from .sources.base import BaseSource
from .textutil import newer_version


@dataclass(slots=True)
class UpdateCandidate:
    item: CatalogItem
    installed: InstalledItem

    @property
    def local_version(self) -> str:
        return self.installed.version or "—"

    @property
    def remote_version(self) -> str:
        return self.item.version or "—"


class UpdateService:
    def __init__(self, db: Database, sources: dict[str, BaseSource]) -> None:
        self.db = db
        self.sources = sources

    def candidates(self) -> list[UpdateCandidate]:
        found: list[UpdateCandidate] = []
        for record in self.db.installed_all():
            item = self.db.get_item(record.source_id, record.remote_id)
            if not item or not item.version:
                continue
            if newer_version(item.version, record.version):
                found.append(UpdateCandidate(item=item, installed=record))
        return found

    def stale_source_count(self, source_id: str) -> int:
        record = self.db.meta_get(f"synced:{source_id}", "")
        return 0 if record else 1

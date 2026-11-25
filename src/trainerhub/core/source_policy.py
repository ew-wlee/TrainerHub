"""Shared catalogue source preference, applied before any source filtering."""

from __future__ import annotations

from collections.abc import Iterable

from .game_matching import _canonical, _identity_groups, _item_names
from .models import CatalogItem


def game_identity(item: CatalogItem) -> str:
    """Stable bilingual identity with sequel, DLC and edition conflict protection."""
    return _canonical(_item_names(item)) or f"key:{item.source_id}:{item.remote_id}"


def select_preferred(
    items: Iterable[CatalogItem],
    *,
    remote_state: str = "idle",
    source_filter: str = "all",
) -> list[CatalogItem]:
    """Keep FLiNG over same-game Xiaoxing; defer fallback while remote loads."""
    deduplicated: dict[tuple[str, str], CatalogItem] = {}
    for item in items:
        previous = deduplicated.get(item.key)
        if previous is None or (item.detail_loaded and not previous.detail_loaded):
            deduplicated[item.key] = item
    catalog = list(deduplicated.values())
    identities = _identity_groups(catalog)
    preferred = {identities[item.key] for item in catalog if item.source_id == "fling"}
    selected = [
        item
        for item in catalog
        if item.source_id != "xiaoxing"
        or (remote_state != "loading" and identities[item.key] not in preferred)
    ]
    if source_filter and source_filter != "all":
        selected = [item for item in selected if item.source_id == source_filter]
    return selected

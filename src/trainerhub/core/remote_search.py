"""Live source search: ask FLiNG's WordPress index for what the local table lacks.

The local SQLite catalogue stays the primary source; this module only fills the
gap when a user searches for a game that has not been synced yet. Results are
not persisted here — the caller decides when to write one into the catalogue.
"""

from __future__ import annotations

import html
import logging
import re
from typing import Any

import httpx

from .models import CatalogItem
from .textutil import normalize, normalize_date, split_title

LOGGER = logging.getLogger("trainerhub.remote_search")

ENDPOINT = "https://flingtrainer.com/wp-json/wp/v2/posts"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 TrainerHub/0.2"
)
_TAG = re.compile(r"<[^>]+>")
_TRAINER_SUFFIX = re.compile(r"\s*trainer\s*$", re.IGNORECASE)


def parse_posts(payload: Any, term: str, limit: int = 6) -> list[CatalogItem]:
    """Turn a WP REST payload into catalogue items, filtered by the query."""
    needle = normalize(term)
    if not needle:
        return []

    results: list[CatalogItem] = []
    seen: set[str] = set()
    for post in payload if isinstance(payload, list) else []:
        if not isinstance(post, dict):
            continue
        raw_title = html.unescape(_TAG.sub("", str(post.get("title", {}).get("rendered", "")))).strip()
        if not raw_title or not _TRAINER_SUFFIX.search(raw_title):
            continue
        name, alias, version = split_title(raw_title)
        if not name or needle not in normalize(name):
            continue
        key = normalize(name)
        if key in seen:
            continue
        seen.add(key)

        published = str(post.get("date") or "")
        modified = str(post.get("modified") or "") or published
        results.append(
            CatalogItem(
                source_id="fling",
                remote_id=str(post.get("id") or post.get("slug") or ""),
                title=raw_title,
                game_name=name,
                game_alias=alias,
                version=version,
                page_url=str(post.get("link") or ""),
                updated_at=normalize_date(modified) or normalize_date(published),
                published_at=normalize_date(published),
                supports_direct_download=True,
            )
        )
        if len(results) >= limit:
            break
    return results


def make_client(timeout: float = 6.0) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )


def search_fling(
    term: str,
    *,
    limit: int = 6,
    timeout: float = 6.0,
    client: httpx.Client | None = None,
) -> list[CatalogItem]:
    """Query the live index. Raises ``httpx.HTTPError`` on network/HTTP failure."""
    term = term.strip()
    if len(term) < 2:
        return []

    params = {
        "search": term,
        "per_page": 8,
        "_fields": "id,date,modified,link,title",
    }
    if client is not None:
        response = client.get(ENDPOINT, params=params, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    else:
        with make_client(timeout) as owned:
            response = owned.get(ENDPOINT, params=params)
            response.raise_for_status()
            payload = response.json()

    items = parse_posts(payload, term, limit=limit)
    LOGGER.info("remote search %r -> %d items", term, len(items))
    return items

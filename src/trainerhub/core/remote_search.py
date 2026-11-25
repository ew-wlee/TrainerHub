"""Live source search: ask FLiNG's WordPress index for what the local table lacks.

The local SQLite catalogue stays the primary source; this module only fills the
gap when a user searches for a game that has not been synced yet. Results are
not persisted here — the caller decides when to write one into the catalogue.
"""

from __future__ import annotations

import html
import logging
import re
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlparse

import httpx

from .models import CatalogItem
from .textutil import normalize, normalize_date, split_title

LOGGER = logging.getLogger("trainerhub.remote_search")

ENDPOINT = "https://flingtrainer.com/wp-json/wp/v2/posts"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 TrainerHub/0.3"
)
_TAG = re.compile(r"<[^>]+>")
_TRAINER_SUFFIX = re.compile(r"\s*trainer\s*$", re.IGNORECASE)


def parse_posts(payload: Any, term: str, limit: int = 6) -> list[CatalogItem]:
    """Turn a WP REST payload into catalogue items, filtered by the query."""
    needle = normalize(term)
    if not needle or limit <= 0:
        return []

    results: list[CatalogItem] = []
    seen: set[str] = set()
    for post in payload if isinstance(payload, list) else []:
        if not isinstance(post, dict):
            continue
        title = post.get("title")
        if not isinstance(title, dict) or not isinstance(title.get("rendered"), str):
            continue
        raw_title = html.unescape(_TAG.sub("", title["rendered"])).strip()
        if not raw_title or not _TRAINER_SUFFIX.search(raw_title):
            continue
        post_id = post.get("id")
        link = post.get("link")
        if isinstance(post_id, bool) or not isinstance(post_id, int) or post_id <= 0:
            continue
        if not isinstance(link, str):
            continue
        try:
            url = urlparse(link)
            if url.scheme != "https" or url.hostname not in ("flingtrainer.com", "www.flingtrainer.com"):
                continue
            if url.username or url.password or url.port not in (None, 443):
                continue
        except ValueError:
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
                remote_id=str(post_id),
                title=raw_title,
                game_name=name,
                game_alias=alias,
                version=version,
                page_url=link,
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
    else:
        with make_client(timeout) as owned:
            response = owned.get(ENDPOINT, params=params)
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as exc:
        raise InvalidSearchResponse("Invalid JSON search response") from exc
    if not isinstance(payload, list):
        raise InvalidSearchResponse("Expected a WordPress article list")
    items = parse_posts(payload, term, limit=limit)
    LOGGER.info("remote search returned %d items", len(items))
    return items


class InvalidSearchResponse(ValueError):
    """The source responded, but its payload is not a searchable article list."""


def search_fling_variants(
    terms: Iterable[str], *, client: httpx.Client, limit: int = 6, cancelled=None
) -> list[CatalogItem]:
    """Search at most three reliable names, keeping results and failures distinct."""
    queries: list[str] = []
    for term in terms:
        term = term.strip()
        if len(term) >= 2 and term.casefold() not in {q.casefold() for q in queries}:
            queries.append(term)
        if len(queries) == 3:
            break
    items: dict[tuple[str, str], CatalogItem] = {}
    successful = False
    failure: Exception | None = None
    for term in queries:
        if cancelled is not None and cancelled():
            break
        try:
            results = search_fling(term, client=client, limit=limit)
        except (httpx.HTTPError, ValueError) as exc:
            failure = exc
            continue
        successful = True
        for item in results:
            items.setdefault(item.key, item)
    if not successful and failure is not None:
        raise failure
    if failure is not None and not items:
        raise failure
    return list(items.values())[:limit]

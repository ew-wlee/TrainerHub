"""In-memory search index.

The catalogue is only a few thousand rows, so a flat scan over pre-normalised
fields beats a database full-text index: no platform-dependent SQLite build
options, no schema churn, and sub-30 ms queries.
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from .models import CatalogItem
from .textutil import normalize, pinyin_forms


@dataclass(slots=True)
class _Entry:
    item: CatalogItem
    norm_game: str
    norm_alias: str
    norm_title: str
    pinyin_full: str
    pinyin_init: str

    def match(self, token: str) -> float:
        game = self.norm_game
        if not game:
            return 0.0
        score = 0.0
        if token == game:
            score = 1000.0
        elif game.startswith(token):
            score = 900.0
        elif token in game:
            score = 780.0
        elif self.norm_alias and token in self.norm_alias:
            score = 720.0
        elif self.pinyin_full.startswith(token):
            score = 560.0
        elif token in self.pinyin_full:
            score = 480.0
        elif self.pinyin_init.startswith(token):
            score = 520.0
        elif token in self.pinyin_init:
            score = 440.0
        elif token in self.norm_title:
            score = 380.0
        if score:
            # Shorter titles are usually the more precise match.
            score += min(60.0, 240.0 / (len(game) + 1))
        return score


@dataclass(slots=True)
class SearchHit:
    item: CatalogItem
    score: float


class SearchEngine:
    def __init__(self, items: list[CatalogItem] | None = None) -> None:
        self._entries: list[_Entry] = []
        self.rebuild(items or [])

    def rebuild(self, items: list[CatalogItem]) -> None:
        entries: list[_Entry] = []
        for item in items:
            game = normalize(item.game_name or item.title)
            alias = normalize(item.game_alias)
            full, initials = pinyin_forms(item.game_name or item.title)
            entries.append(
                _Entry(
                    item=item,
                    norm_game=game,
                    norm_alias=alias,
                    norm_title=normalize(item.title),
                    pinyin_full=full,
                    pinyin_init=initials,
                )
            )
        self._entries = entries

    @property
    def size(self) -> int:
        return len(self._entries)

    def query(
        self,
        text: str = "",
        *,
        source_id: str = "all",
        limit: int = 400,
        fuzzy: bool = True,
    ) -> list[SearchHit]:
        candidates = self._entries
        if source_id and source_id != "all":
            candidates = [entry for entry in candidates if entry.item.source_id == source_id]

        tokens = [token for token in (normalize(part) for part in (text or "").split()) if token]
        if not tokens:
            ordered = sorted(candidates, key=lambda e: e.item.updated_at, reverse=True)
            return [SearchHit(item=e.item, score=0.0) for e in ordered[:limit]]

        hits: list[SearchHit] = []
        seen: set[tuple[str, str]] = set()
        for entry in candidates:
            total = 0.0
            for token in tokens:
                partial = entry.match(token)
                if partial <= 0:
                    total = 0.0
                    break
                total += partial
            if total > 0:
                hits.append(SearchHit(item=entry.item, score=total))
                seen.add(entry.item.key)

        if fuzzy and len(hits) < 8:
            needle = " ".join(tokens)
            for entry in candidates:
                if entry.item.key in seen:
                    continue
                ratio = fuzz.WRatio(needle, entry.norm_game or entry.norm_title)
                if ratio >= 62:
                    hits.append(SearchHit(item=entry.item, score=ratio * 3.0))
                    seen.add(entry.item.key)

        hits.sort(key=lambda hit: (hit.score, hit.item.updated_at), reverse=True)
        return hits[:limit]

    def suggestions(self, text: str, limit: int = 8) -> list[str]:
        """Game names that a partially typed query is likely aiming at."""
        if not text:
            return []
        hits = self.query(text, limit=limit)
        names: list[str] = []
        for hit in hits:
            name = hit.item.game_name
            if name and name not in names:
                names.append(name)
        return names

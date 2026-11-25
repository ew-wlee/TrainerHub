"""Pure local recommendation plans; catalogue versions are never guessed."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import datetime, timezone

from .game_matching import GameMatcher
from .models import CatalogItem, RecommendationEntry, RecommendationPlan, SteamGame
from .source_policy import select_preferred

_RETAINED_STATES = {
    "queued",
    "resolving",
    "downloading",
    "extracting",
    "installing",
    "done",
    "failed",
    "cancelled",
}


def build_plan(
    games: Iterable[SteamGame],
    items: Iterable[CatalogItem],
    installed_keys: set[tuple[str, str]],
    excluded: set[str] | None = None,
    *,
    generation: int = 0,
    previous: RecommendationPlan | None = None,
) -> RecommendationPlan:
    """Rebuild a plan while preserving per-app/item choices and download states."""
    excluded_ids = excluded or set()
    game_list = sorted(games, key=lambda game: (game.name.casefold(), game.appid, game.library_path))
    catalog = select_preferred(items)
    matcher = GameMatcher(catalog)
    history = {(entry.game.appid, entry.item.key): entry for entry in previous.entries} if previous else {}
    stamp = datetime.now(timezone.utc).isoformat()
    snapshot = {
        "games": sorted(
            (game.appid, game.name, game.library_path, game.install_path, game.build_id) for game in game_list
        ),
        "catalog": sorted(
            (item.source_id, item.remote_id, item.game_name, item.game_alias, item.version)
            for item in catalog
        ),
    }
    version = hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[
        :16
    ]
    plan = RecommendationPlan(generation=generation, generated_at=stamp, snapshot_version=version)
    seen: set[str] = set()
    for game in game_list:
        if game.appid in seen or game.appid in excluded_ids:
            continue
        seen.add(game.appid)
        match = matcher.match(game)
        if match is None:
            plan.unmatched.append(game)
            continue
        action = "external" if match.item.source_id == "xiaoxing" else "download"
        entry = RecommendationEntry(game, match.item, match.confidence, match.reason, action=action)
        old = history.get((game.appid, match.item.key))
        if old is not None:
            entry.selected = old.selected
            if old.state in _RETAINED_STATES:
                entry.state = old.state
        if match.item.key in installed_keys:
            entry.state = "installed"
            entry.selected = False
        elif action == "external":
            entry.state = "ready"
            entry.selected = False
        plan.entries.append(entry)
    plan.entries.sort(
        key=lambda entry: (
            entry.state == "installed",
            entry.confidence != "high",
            entry.game.name.casefold(),
            entry.game.appid,
            entry.item.key,
        )
    )
    return plan

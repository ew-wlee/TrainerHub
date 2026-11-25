from __future__ import annotations

import pytest

from trainerhub.core.models import CatalogItem, SteamGame
from trainerhub.core.recommendation import build_plan


def item(name: str, source: str = "fling", remote_id: str = "1") -> CatalogItem:
    return CatalogItem(source, remote_id, name, name)


def game(name: str, appid: str = "123") -> SteamGame:
    return SteamGame(appid, name, "/steam", f"/steam/steamapps/common/{name}")


def test_high_and_medium_matches_selected_by_default():
    plan = build_plan(
        [game("Hades"), game("Final Fantasy VII", "456")],
        [item("Hades"), item("Final Fantasy 7", remote_id="2")],
        set(),
        generation=3,
    )
    assert [entry.confidence for entry in plan.entries] == ["high", "medium"]
    assert all(
        entry.selected and entry.state == "ready" and entry.action == "download" for entry in plan.entries
    )
    assert plan.generation == 3 and plan.generated_at and plan.snapshot_version


def test_external_source_never_auto_selected():
    plan = build_plan([game("Hades")], [item("Hades", "xiaoxing")], set())
    entry = plan.entries[0]
    assert entry.action == "external" and not entry.selected


def test_fling_preferred_to_external_fallback():
    preferred = item("Hades")
    plan = build_plan([game("Hades")], [item("Hades", "xiaoxing"), preferred], set())
    assert plan.entries[0].item is preferred


def test_installed_match_is_not_selected():
    trainer = item("Hades")
    plan = build_plan([game("Hades")], [trainer], {trainer.key})
    assert plan.entries[0].state == "installed" and not plan.entries[0].selected


def test_unmatched_exclusions_and_duplicate_apps():
    unknown, excluded = game("Unknown", "456"), game("Control", "789")
    plan = build_plan(
        [game("Hades"), game("Hades"), unknown, excluded],
        [item("Hades"), item("Control", remote_id="2")],
        set(),
        {"789"},
    )
    assert len(plan.entries) == 1 and plan.unmatched == [unknown]


@pytest.mark.parametrize(
    "state", ["queued", "resolving", "downloading", "extracting", "installing", "done", "failed", "cancelled"]
)
def test_selection_and_queue_states_preserved_for_stable_key(state):
    games, catalog = [game("Hades")], [item("Hades")]
    previous = build_plan(games, catalog, set())
    previous.entries[0].selected = False
    previous.entries[0].state = state
    current = build_plan(games, catalog, set(), previous=previous)
    assert current.entries[0].state == state and not current.entries[0].selected
    assert previous.entries[0].state == state


def test_changed_trainer_key_does_not_inherit_selection_or_queue_state():
    games = [game("Hades")]
    previous = build_plan(games, [item("Hades")], set())
    previous.entries[0].selected = False
    previous.entries[0].state = "downloading"
    current = build_plan(games, [item("Hades", remote_id="2")], set(), previous=previous)
    assert current.entries[0].selected and current.entries[0].state == "ready"


def test_installed_overrides_previous_queue_state():
    trainer = item("Hades")
    previous = build_plan([game("Hades")], [trainer], set())
    previous.entries[0].state = "downloading"
    current = build_plan([game("Hades")], [trainer], {trainer.key}, previous=previous)
    assert current.entries[0].state == "installed" and not current.entries[0].selected


def test_sort_and_snapshot_are_stable_for_reordered_inputs():
    games = [game("Hades", "1"), game("Control", "2"), game("Final Fantasy VII", "3")]
    catalog = [item("Hades"), item("Control", remote_id="2"), item("Final Fantasy 7", remote_id="3")]
    first = build_plan(games, catalog, {catalog[1].key})
    second = build_plan(reversed(games), reversed(catalog), {catalog[1].key})
    assert [entry.game.name for entry in first.entries] == ["Hades", "Final Fantasy VII", "Control"]
    assert [entry.game.name for entry in second.entries] == [entry.game.name for entry in first.entries]
    assert first.snapshot_version == second.snapshot_version


def test_catalog_versions_do_not_change_match_confidence():
    trainer = item("Hades")
    trainer.game_version = "unknown-compatibility"
    plan = build_plan([game("Hades")], [trainer], set())
    assert plan.entries[0].confidence == "high"
    assert "未验证版本兼容性" in plan.entries[0].reason

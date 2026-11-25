from __future__ import annotations

import json
from pathlib import Path

import pytest

from trainerhub.core.game_matching import GameMatcher
from trainerhub.core.models import CatalogItem, SteamGame

_CASES = json.loads((Path(__file__).parent / "fixtures/discovery_cases.json").read_text(encoding="utf-8"))["matching"]


def item(name: str, alias: str = "", source: str = "fling", remote_id: str = "1") -> CatalogItem:
    return CatalogItem(source, remote_id, name, name, game_alias=alias)


def game(name: str) -> SteamGame:
    return SteamGame("123", name, "/steam", "/steam/steamapps/common/game")


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["id"])
def test_matching_fixtures(case):
    catalog = [
        item(row["name"], row.get("alias", ""), remote_id=str(index))
        for index, row in enumerate(case["catalog"])
    ]
    match = GameMatcher(iter(catalog)).match(game(case["steam"]))
    assert (match.confidence if match else None) == case["confidence"]
    if match:
        assert "未验证版本兼容性" in match.reason


def test_exact_prefers_fling_for_same_identity():
    fallback = item("黑神话：悟空", "Black Myth: Wukong", "xiaoxing")
    preferred = item("Black Myth: Wukong")
    match = GameMatcher([fallback, preferred]).match(game("Black Myth: Wukong"))
    assert match and match.item is preferred


def test_same_identity_variants_do_not_count_as_ambiguity():
    preferred = item("Final Fantasy 7")
    fallback = item("最终幻想7", "Final Fantasy 7", "xiaoxing")
    match = GameMatcher([fallback, preferred]).match(game("Final Fantasy VII"))
    assert match and match.confidence == "medium" and match.item is preferred


def test_match_preserves_original_game_and_item_objects():
    source_game, source_item = game("Hades"), item("Hades")
    match = GameMatcher([source_item]).match(source_game)
    assert match and match.game is source_game and match.item is source_item


def test_empty_catalog_has_no_match():
    assert GameMatcher([]).match(game("Hades")) is None


@pytest.mark.parametrize(
    "candidate", ["A Very Long Original Game Title Dawn", "A Very Long Original Game Title Two"]
)
def test_named_expansions_and_short_subtitle_additions_do_not_fuzzy_match(candidate):
    assert GameMatcher([item(candidate)]).match(game("A Very Long Original Game Title")) is None


def test_different_short_subtitle_is_not_overwhelmed_by_long_base_title():
    matcher = GameMatcher([item("A Very Long Original Game Title Alpha")])
    assert matcher.match(game("A Very Long Original Game Title Beta")) is None


@pytest.mark.parametrize(
    "candidate",
    ["Elden Ring Shadow of the Erdtree", "Elden Ring: Shadow of the Erdtree", "Elden Ring Nightreign"],
)
def test_named_dlc_and_new_titles_never_match_base_game(candidate):
    assert GameMatcher([item(candidate)]).match(game("Elden Ring")) is None


def test_similar_but_different_explicit_subtitles_are_not_fuzzy_aliases():
    matcher = GameMatcher([item("The Very Long Original Game: Shadows of Night")])
    assert matcher.match(game("The Very Long Original Game: Shadow of Night")) is None


def test_roman_before_known_remake_suffix_links_reliable_bilingual_alias():
    trainer = item("最终幻想 7 重制版", "Final Fantasy VII Remake Intergrade")
    match = GameMatcher([trainer]).match(game("Final Fantasy VII Remake Intergrade"))
    assert match and match.confidence == "high"
    conflict = item("最终幻想 7", "Final Fantasy VII Remake Intergrade")
    assert GameMatcher([conflict]).match(game("Final Fantasy VII Remake Intergrade")) is None


@pytest.mark.parametrize("suffix", ["Remake Intergrade", "Remastered", "Definitive Edition"])
def test_roman_before_known_edition_suffix_is_a_safe_variant(suffix):
    match = GameMatcher([item(f"Final Fantasy 7 {suffix}")]).match(game(f"Final Fantasy VII {suffix}"))
    assert match and match.confidence == "medium"


def test_roman_at_start_of_sentence_is_not_converted():
    assert GameMatcher([item("1 Am Alive")]).match(game("I Am Alive")) is None


def test_fuzzy_bucket_does_not_evaluate_incompatible_catalog_items(monkeypatch):
    import trainerhub.core.game_matching as matching

    catalog = [item("Cyberpnk 2077")]
    catalog.extend(item(f"Another Game {index}", remote_id=str(index + 2)) for index in range(300))
    matcher = GameMatcher(catalog)
    calls = []
    original = matching._fuzzy_score

    def counted(left, right):
        calls.append(right.text)
        return original(left, right)

    monkeypatch.setattr(matching, "_fuzzy_score", counted)
    assert matcher.match(game("Cyberpunk 2077"))
    assert calls == ["cyberpnk 2077"]


def test_fuzzy_candidate_budget_is_conservative(monkeypatch):
    import trainerhub.core.game_matching as matching

    monkeypatch.setattr(matching, "MAX_FUZZY_CANDIDATES", 1)
    matcher = GameMatcher([item("Cyberpnk 2077"), item("Cyberpank 2077", remote_id="2")])
    assert matcher.match(game("Cyberpunk 2077")) is None

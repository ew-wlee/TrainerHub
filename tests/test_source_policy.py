from __future__ import annotations

import pytest

from trainerhub.core.models import CatalogItem
from trainerhub.core.source_policy import game_identity, select_preferred


def item(
    name: str, source: str = "fling", alias: str = "", remote_id: str = "1", detailed: bool = False
) -> CatalogItem:
    return CatalogItem(source, remote_id, name, name, game_alias=alias, detail_loaded=detailed)


def test_fling_suppresses_only_same_game_xiaoxing():
    preferred = item("Hades")
    duplicate = item("哈迪斯", "xiaoxing", "Hades")
    other = item("Control", "xiaoxing", remote_id="2")
    assert select_preferred([duplicate, other, preferred]) == [other, preferred]


def test_source_filter_is_applied_after_preference():
    preferred, fallback = item("Hades"), item("Hades", "xiaoxing")
    assert select_preferred([preferred, fallback], source_filter="xiaoxing") == []
    assert select_preferred([preferred, fallback], source_filter="fling") == [preferred]


@pytest.mark.parametrize("state", ["idle", "error"])
def test_fallback_allowed_when_not_loading_and_no_known_fling(state):
    fallback = item("Hades", "xiaoxing")
    assert select_preferred([fallback], remote_state=state) == [fallback]


def test_fallback_deferred_while_remote_loading():
    preferred, fallback = item("Control"), item("Hades", "xiaoxing")
    assert select_preferred([preferred, fallback], remote_state="loading") == [preferred]


@pytest.mark.parametrize("reverse", [False, True])
def test_same_key_preserves_detail_loaded_item(reverse):
    detailed = item("Hades", detailed=True)
    detailed.options = ("Infinite Health",)
    sparse = item("Hades")
    values = [sparse, detailed] if reverse else [detailed, sparse]
    result = select_preferred(values)
    assert result == [detailed] and result[0].options == ("Infinite Health",)


@pytest.mark.parametrize("name", ["Hades 2", "Hades DLC", "Hades Ultimate Edition"])
def test_sequel_dlc_edition_are_not_suppressed(name):
    preferred, other = item("Hades"), item(name, "xiaoxing")
    assert select_preferred([preferred, other]) == [preferred, other]


def test_conflicting_alias_does_not_suppress_another_game():
    preferred = item("Hades")
    sequel = item("Hades 2", "xiaoxing", "Hades")
    assert select_preferred([preferred, sequel]) == [preferred, sequel]


def test_bilingual_identity_stable_across_sources():
    english = item("Black Myth: Wukong")
    bilingual = item("黑神话：悟空", "xiaoxing", "Black Myth: Wukong")
    assert game_identity(english) == game_identity(bilingual)


def test_roman_numeral_identity_links_only_explicit_sequence_position():
    roman, arabic = item("Dark Souls III"), item("Dark Souls 3", "xiaoxing")
    assert game_identity(roman) == game_identity(arabic)
    assert select_preferred([arabic, roman]) == [roman]
    assert game_identity(item("V Rising")) != game_identity(item("5 Rising"))


def test_explicit_alias_chain_links_cross_source_titles():
    preferred = item("Resident Evil 4", alias="RE4")
    fallback = item("生化危机4", "xiaoxing", "RE4")
    assert select_preferred([preferred, fallback]) == [preferred]


def test_empty_game_names_are_not_a_shared_identity():
    preferred, other = item(""), item("", "xiaoxing")
    assert select_preferred([preferred, other]) == [preferred, other]

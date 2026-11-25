"""Conservative, precomputed game-name matching; never use search pinyin scores."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache

from rapidfuzz import fuzz, process

from .models import CatalogItem, GameMatch, SteamGame
from .textutil import normalize, strip_noise

_ROMAN = {
    "i": "1",
    "ii": "2",
    "iii": "3",
    "iv": "4",
    "v": "5",
    "vi": "6",
    "vii": "7",
    "viii": "8",
    "ix": "9",
    "x": "10",
    "xi": "11",
    "xii": "12",
    "xiii": "13",
    "xiv": "14",
    "xv": "15",
    "xvi": "16",
    "xvii": "17",
    "xviii": "18",
    "xix": "19",
    "xx": "20",
}
MAX_FUZZY_CANDIDATES = 256
_ROMAN_POSITION = re.compile(
    r"(?<=[\w])\s+(i{1,3}|iv|v|vi{1,3}|ix|x|xi{1,3}|xiv|xv|xvi{1,3}|xix|xx)"
    r"(?=\s*(?:$|[:：–—-])|\s+(?:(?:deluxe|ultimate|definitive|complete|special|anniversary|enhanced)\s+)?"
    r"(?:remake|remaster(?:ed)?|edition)\b)",
    re.IGNORECASE,
)
_QUALIFIERS = {
    "deluxe": r"\bdeluxe\b|豪华",
    "ultimate": r"\bultimate\b|终极",
    "definitive": r"\bdefinitive\b|决定版",
    "complete": r"\bcomplete\b|完整版",
    "remaster": r"\bremaster(?:ed)?\b|高清重制|复刻",
    "remake": r"\bremake\b|重制版",
    "goty": r"\bgoty\b|\bgame\s+of\s+the\s+year\b|年度版",
    "anniversary": r"\banniversary\b|周年",
    "enhanced": r"\benhanced\b|增强版",
    "collector": r"\bcollector(?:'s|s)?\b|典藏",
    "director": r"\bdirector(?:'s|s)?\s+cut\b|导演剪辑",
    "gold": r"\bgold\b|黄金版",
    "standard": r"\bstandard\b|标准版",
    "special": r"\bspecial\b|特别版",
    "legendary": r"\blegendary\b|传奇版",
    "hd": r"\bhd\b",
    "dlc": r"\bdlc\b|\bexpansion\b|\bseason\s+pass\b|资料片|扩展包|季票",
}
_PATTERNS = {key: re.compile(pattern, re.IGNORECASE) for key, pattern in _QUALIFIERS.items()}
_CJK = re.compile(r"[\u3400-\u9fff]")


@dataclass(frozen=True, slots=True)
class _Name:
    text: str
    exact: str
    variant: str
    digits: tuple[str, ...]
    qualifiers: tuple[str, ...]
    tokens: tuple[str, ...]
    subtitle: str

    @property
    def identity(self) -> str:
        return f"{self.variant}|{','.join(self.digits)}|{','.join(self.qualifiers)}"


@lru_cache(maxsize=8192)
def _name(text: str) -> _Name:
    cleaned = re.sub(r"[™®©]", "", text or "")
    folded = unicodedata.normalize("NFKC", cleaned).casefold().strip()
    roman = _ROMAN_POSITION.sub(lambda match: " " + _ROMAN[match.group(1).casefold()], folded)
    digits = tuple(str(int(value)) for value in re.findall(r"[0-9]+", roman))
    qualifiers = tuple(sorted(key for key, pattern in _PATTERNS.items() if pattern.search(folded)))
    if not qualifiers and (re.search(r"\bedition\b", folded) or "版" in folded):
        qualifiers = ("edition",)
    tokens = tuple(re.findall(r"[^\W\d_]+|[0-9]+", roman))
    parts = re.split(r"[:：]", roman, maxsplit=1)
    subtitle = normalize(parts[1]) if len(parts) > 1 else ""
    return _Name(folded, normalize(folded), normalize(roman), digits, qualifiers, tokens, subtitle)


def _compatible(left: _Name, right: _Name) -> bool:
    return left.digits == right.digits and left.qualifiers == right.qualifiers


def _fuzzy_score(left: _Name, right: _Name) -> float:
    if not _compatible(left, right):
        return 0.0
    if left.variant == right.variant:
        return 100.0
    if left.subtitle != right.subtitle:
        return 0.0
    if left.variant in right.variant or right.variant in left.variant:
        return 0.0
    if len(left.tokens) != len(right.tokens):
        return 0.0
    if any(fuzz.ratio(a, b) < 75 for a, b in zip(left.tokens, right.tokens, strict=True)):
        return 0.0
    return fuzz.ratio(left.variant, right.variant)


def _item_names(item: CatalogItem) -> tuple[_Name, ...]:
    primary = _name(item.game_name or strip_noise(item.title))
    if not primary.exact:
        return ()
    alias = _name(item.game_alias)
    if not alias.exact or alias.exact == primary.exact or not _compatible(primary, alias):
        return (primary,)
    # A shortened same-language base title is not a reliable sequel/subtitle alias.
    same_script = bool(_CJK.search(primary.text)) == bool(_CJK.search(alias.text))
    if same_script and (primary.variant in alias.variant or alias.variant in primary.variant):
        return (primary,)
    return primary, alias


def _canonical(names: Iterable[_Name]) -> str:
    available = list(names)
    if not available:
        return ""
    preferred = sorted(
        available, key=lambda name: (bool(_CJK.search(name.text)), -len(name.variant), name.identity)
    )
    return preferred[0].identity


def _identity_groups(items: list[CatalogItem]) -> dict[tuple[str, str], str]:
    """Link only structured, fingerprint-compatible catalogue aliases."""
    parent: dict[str, str] = {}
    all_names: dict[str, _Name] = {}
    item_names: dict[tuple[str, str], tuple[_Name, ...]] = {}

    def find(key: str) -> str:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    for item in items:
        names = _item_names(item)
        item_names[item.key] = names
        for name in names:
            parent.setdefault(name.identity, name.identity)
            all_names[name.identity] = name
        if names:
            root = find(names[0].identity)
            for name in names[1:]:
                parent[find(name.identity)] = root
    components: dict[str, list[_Name]] = {}
    for key, name in all_names.items():
        components.setdefault(find(key), []).append(name)
    identities = {root: _canonical(names) for root, names in components.items()}
    return {
        key: identities[find(names[0].identity)] if names else f"key:{key[0]}:{key[1]}"
        for key, names in item_names.items()
    }


@dataclass(slots=True)
class _Candidate:
    item: CatalogItem
    names: tuple[_Name, ...]
    identity: str


def _preference(item: CatalogItem) -> tuple:
    return (item.source_id != "fling", not item.detail_loaded, item.source_id, item.remote_id)


class GameMatcher:
    """Index once, then return only exact identities or unambiguous >=90 matches."""

    def __init__(self, items: Iterable[CatalogItem]) -> None:
        catalog = list(items)
        groups = _identity_groups(catalog)
        self._entries = [_Candidate(item, _item_names(item), groups[item.key]) for item in catalog]
        self._exact: dict[str, list[_Candidate]] = {}
        self._buckets: dict[tuple, dict[str, tuple[_Candidate, _Name]]] = {}
        for entry in self._entries:
            for name in entry.names:
                self._exact.setdefault(name.exact, []).append(entry)
                bucket = self._buckets.setdefault((name.digits, name.qualifiers, len(name.tokens)), {})
                existing = bucket.get(name.variant)
                if existing is None or _preference(entry.item) < _preference(existing[0].item):
                    bucket[name.variant] = entry, name

    def match(self, game: SteamGame) -> GameMatch | None:
        needle = _name(game.name)
        if not needle.exact:
            return None
        exact = [
            entry
            for entry in self._exact.get(needle.exact, ())
            if any(name.exact == needle.exact and _compatible(needle, name) for name in entry.names)
        ]
        if exact:
            if len({entry.identity for entry in exact}) != 1:
                return None
            chosen = min(exact, key=lambda entry: _preference(entry.item))
            return GameMatch(game, chosen.item, "high", "游戏名称或可靠别名精确一致；未验证版本兼容性")
        bucket = self._buckets.get((needle.digits, needle.qualifiers, len(needle.tokens)), {})
        candidates = process.extract(
            needle.variant,
            tuple(bucket),
            scorer=fuzz.ratio,
            score_cutoff=82,
            limit=MAX_FUZZY_CANDIDATES + 1,
        )
        if len(candidates) > MAX_FUZZY_CANDIDATES:
            return None
        scores: dict[str, tuple[float, _Candidate]] = {}
        for variant, _, _ in candidates:
            entry, name = bucket[variant]
            score = _fuzzy_score(needle, name)
            existing = scores.get(entry.identity)
            if (
                existing is None
                or score > existing[0]
                or (score == existing[0] and _preference(entry.item) < _preference(existing[1].item))
            ):
                scores[entry.identity] = score, entry
        ranked = sorted(scores.values(), key=lambda pair: (-pair[0], _preference(pair[1].item)))
        if not ranked or ranked[0][0] < 90:
            return None
        score, chosen = ranked[0]
        if len(ranked) > 1 and score - ranked[1][0] < 8:
            return None
        return GameMatch(
            game, chosen.item, "medium", "名称安全变体或相似度≥90且领先≥8；请确认名称，未验证版本兼容性"
        )

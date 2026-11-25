"""Text normalisation, bilingual title splitting and version helpers.

Everything here is pure Python — no Qt, no network — so it can be unit tested
and reused by the CLI.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

from pypinyin import Style, lazy_pinyin

# Words that never belong to a game title, in the order they should be removed.
_NOISE_SUFFIXES = (
    "多功能修改器",
    "六十四项修改器",
    "三十二项修改器",
    "十六项修改器",
    "十二项修改器",
    "十项修改器",
    "修改器",
    "辅助器",
    "修改工具",
    "trainer",
    "cheats",
    "cheat table",
)

_VERSION_PATTERNS = (
    re.compile(r"\bv(?:er(?:sion)?)?\.?\s*(\d+(?:\.\d+){1,3})\b", re.IGNORECASE),
    re.compile(r"\b(\d+(?:\.\d+){1,3})\s*版\b"),
    re.compile(r"\bplus\s*(\d+)\b", re.IGNORECASE),
)

_TRAILING_NOISE = re.compile(
    r"(?:\s*[-–—|/]\s*)?(?:"
    + "|".join(re.escape(word) for word in _NOISE_SUFFIXES)
    + r")\s*$",
    re.IGNORECASE,
)

_BILINGUAL_SPLIT = re.compile(r"\s+[/｜|]\s+")
_PUNCT = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)
_PAREN = re.compile(r"[（(【\[][^）)】\]]*[）)】\]]")


def to_halfwidth(text: str) -> str:
    """Convert full-width latin characters and digits to their ASCII form."""
    out: list[str] = []
    for char in text:
        code = ord(char)
        if code == 0x3000:
            out.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        else:
            out.append(char)
    return "".join(out)


def normalize(text: str) -> str:
    """Fold a string into the canonical form used for matching."""
    if not text:
        return ""
    folded = unicodedata.normalize("NFKC", to_halfwidth(text)).casefold()
    folded = _PUNCT.sub("", folded)
    return folded.strip()


def strip_noise(name: str) -> str:
    """Remove trailing product words ("Trainer", "修改器", "Plus 11", …)."""
    text = name.strip()
    for _ in range(4):
        new = _TRAILING_NOISE.sub("", text).strip()
        new = re.sub(r"\s*(?:plus|v)\s*\d+(?:\.\d+)*\s*$", "", new, flags=re.IGNORECASE).strip()
        if new == text or not new:
            break
        text = new
    return text.strip(" -–—:|：·")


def extract_version(title: str) -> str:
    """Pull a version marker out of a title, e.g. ``V1.7.0`` or ``Plus 11``."""
    for pattern in _VERSION_PATTERNS:
        match = pattern.search(title)
        if match:
            value = match.group(1)
            if "plus" in pattern.pattern.lower():
                return f"Plus {value}"
            return f"v{value}"
    return ""


def split_title(title: str) -> tuple[str, str, str]:
    """Split a raw title into ``(game_name, alias, version)``.

    Handles the two shapes we actually meet in the wild::

        "Ace Combat 7: Skies Unknown Trainer"
        "黑神话：悟空 多功能修改器 V1.7.0  /  Black Myth: Wukong Trainer"
    """
    raw = (title or "").strip()
    if not raw:
        return "", "", ""
    raw = re.sub(r"&amp;", "&", raw)

    parts = [p for p in _BILINGUAL_SPLIT.split(raw) if p.strip()]
    version = extract_version(raw)
    if len(parts) >= 2:
        left, right = parts[0], parts[1]
        name = strip_noise(_PAREN.sub("", left)) or strip_noise(left)
        alias = strip_noise(_PAREN.sub("", right)) or strip_noise(right)
        return name.strip(), alias.strip(), version

    name = strip_noise(raw)
    return name.strip(), "", version


def pinyin_forms(text: str) -> tuple[str, str]:
    """Return ``(full_pinyin, initials)`` with no separators, for searching."""
    if not text:
        return "", ""
    chars = [c for c in text if c.strip()]
    if not chars:
        return "", ""
    try:
        full = "".join(lazy_pinyin("".join(chars), style=Style.NORMAL))
        initials = "".join(lazy_pinyin("".join(chars), style=Style.FIRST_LETTER))
    except Exception:  # pragma: no cover - pypinyin is defensive enough
        return "", ""
    return normalize(full), normalize(initials)


def version_key(version: str) -> tuple[int, ...]:
    """Turn ``"v1.7.2"`` / ``"Plus 11"`` into a comparable tuple."""
    if not version:
        return (0,)
    numbers = re.findall(r"\d+", version)
    if not numbers:
        return (0,)
    return tuple(int(n) for n in numbers[:4])


def newer_version(candidate: str, current: str) -> bool:
    """True when *candidate* is strictly newer than *current*."""
    return version_key(candidate) > version_key(current)


def normalize_date(value: str) -> str:
    """Best-effort ISO-ish date so sorting is stable across sources."""
    if not value:
        return ""
    text = value.strip()
    match = re.match(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})", text)
    if match:
        year, month, day = (int(part) for part in match.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return ""
    match = re.match(r"(\d{4})(\d{2})(\d{2})$", text)
    if match:
        year, month, day = (int(part) for part in match.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return ""
    return ""


def human_size(size: int) -> str:
    if size <= 0:
        return "—"
    units = ("B", "KB", "MB", "GB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def safe_folder_name(name: str, fallback: str = "Unknown") -> str:
    """Make a string safe to use as a single directory name on Windows."""
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", name or "")
    text = re.sub(r"\s+", " ", text).strip(" .")
    reserved = {
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    if not text:
        return fallback
    if text.upper() in reserved:
        text = f"_{text}"
    return text[:80]

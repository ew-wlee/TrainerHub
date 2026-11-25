from __future__ import annotations

import pytest

from trainerhub.core.textutil import (
    extract_version,
    normalize,
    pinyin_forms,
    safe_folder_name,
    split_title,
    version_key,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Ashes of the Singularity II Trainer", ("Ashes of the Singularity II", "", "")),
        ("Ace Combat 7: Skies Unknown Trainer", ("Ace Combat 7: Skies Unknown", "", "")),
        (
            "黑神话：悟空 多功能修改器 V1.7.0  /  Black Myth: Wukong Trainer",
            ("黑神话：悟空", "Black Myth: Wukong", "v1.7.0"),
        ),
        ("古龙风云录 多功能修改器 V1.5.2", ("古龙风云录", "", "v1.5.2")),
    ],
)
def test_split_title(raw: str, expected: tuple[str, str, str]) -> None:
    assert split_title(raw) == expected


def test_extract_version_variants() -> None:
    assert extract_version("Foo Trainer Plus 11") == "Plus 11"
    assert extract_version("赛博朋克2077 多功能修改器 V2.6.2") == "v2.6.2"
    assert extract_version("No version here") == ""


def test_normalize_folds_case_width_and_punctuation() -> None:
    assert normalize("Ｂｌａｃｋ　Ｍｙｔｈ: Wukong") == "blackmythwukong"
    assert normalize("黑神话：悟空") == "黑神话悟空"


def test_pinyin_forms() -> None:
    full, initials = pinyin_forms("黑神话悟空")
    assert full == "heishenhuawukong"
    assert initials == "hshwk"


def test_version_key_orders_numerically() -> None:
    assert version_key("Plus 36") > version_key("Plus 9")
    assert version_key("v1.7.10") > version_key("v1.7.9")
    assert version_key("") == (0,)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Black Myth: Wukong", "Black Myth Wukong"),
        ("A/B\\C", "A B C"),
        ("CON", "_CON"),
        ("", "Unknown"),
    ],
)
def test_safe_folder_name(name: str, expected: str) -> None:
    assert safe_folder_name(name) == expected

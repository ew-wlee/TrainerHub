from __future__ import annotations

import json
from pathlib import Path

import pytest

from trainerhub.core.db import Database
from trainerhub.core.models import CatalogItem

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db")
    yield database
    database.close()


@pytest.fixture()
def sample_items() -> list[CatalogItem]:
    return [
        CatalogItem(
            source_id="fling",
            remote_id="1",
            title="Black Myth: Wukong Trainer",
            game_name="Black Myth: Wukong",
            version="Plus 36",
            updated_at="2026-08-28",
            options_count=36,
            file_size=1024 * 1024,
            supports_direct_download=True,
            detail_loaded=True,
        ),
        CatalogItem(
            source_id="xiaoxing",
            remote_id="65",
            title="黑神话：悟空 多功能修改器 V1.7.0 / Black Myth: Wukong Trainer",
            game_name="黑神话：悟空",
            game_alias="Black Myth: Wukong",
            version="v1.7.0",
            updated_at="2026-08-28",
            supports_direct_download=False,
        ),
        CatalogItem(
            source_id="fling",
            remote_id="2",
            title="Elden Ring Trainer",
            game_name="Elden Ring",
            version="Plus 12",
            updated_at="2026-02-10",
            supports_direct_download=True,
        ),
    ]


@pytest.fixture()
def fling_posts() -> list[dict]:
    return json.loads((FIXTURES / "fling_posts.json").read_text(encoding="utf-8"))


@pytest.fixture()
def fling_detail_html() -> str:
    return (FIXTURES / "fling_detail.html").read_text(encoding="utf-8")


@pytest.fixture()
def xiaoxing_posts() -> list[dict]:
    return json.loads((FIXTURES / "xiaoxing_posts.json").read_text(encoding="utf-8"))

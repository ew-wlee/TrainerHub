"""Opt-in real source and desktop search acceptance; never downloads executables."""

from __future__ import annotations

import os
import time

import pytest
from PySide6.QtWidgets import QApplication

from trainerhub.core.config import Config
from trainerhub.core.db import Database
from trainerhub.core.http import HttpClient
from trainerhub.core.library import LibraryService
from trainerhub.core.models import CatalogItem
from trainerhub.core.search import SearchEngine
from trainerhub.core.sources.fling import FlingSource
from trainerhub.ui.main_window import MainWindow

pytestmark = pytest.mark.skipif(
    os.environ.get("TRAINERHUB_LIVE_SEARCH_TEST") != "1",
    reason="Real network acceptance requires TRAINERHUB_LIVE_SEARCH_TEST=1",
)


@pytest.mark.parametrize("query", ["Hades", "Cyberpunk 2077"])
def test_real_desktop_search_detail_and_download_resolution(query, tmp_path):
    app = QApplication.instance() or QApplication([])
    config = Config(tmp_path / "config.json", {
        "library_dir": str(tmp_path / "library"),
        "first_run": False,
        "ui": {"sync_on_start": False},
    })
    db = Database(tmp_path / "catalog.db")
    fallback = CatalogItem("xiaoxing", "fallback", query, query)
    db.upsert_items([fallback])
    client = HttpClient(timeout=10, max_retries=0, min_interval=0.2)
    source = FlingSource("https://flingtrainer.com", client)
    window = MainWindow(
        config=config, search=SearchEngine([fallback]),
        library=LibraryService(config.library_dir, db),
        sources={"fling": source}, workers={}, items=[fallback],
    )
    try:
        window.show()
        window.search_box.setText(query)
        end = time.monotonic() + 30
        while time.monotonic() < end and not window._remote_items:
            app.processEvents()
            time.sleep(0.02)
        assert window._remote_items, "Real FLiNG search did not produce results"
        window._run_search()
        items = [window.discover.model.item_at(row) for row in range(window.discover.model.rowCount())]
        matched = next(item for item in items if item.game_name.casefold() == query.casefold())
        assert matched.source_id == "fling"
        assert not any(item.source_id == "xiaoxing" and item.game_name == query for item in items)
        window._on_selection(matched)
        assert window.discover.detail.isVisible()
        detail = source.fetch_detail(matched)
        assert detail.detail_loaded and detail.options_count > 0
        target = source.resolve_download(detail)
        assert target.kind == "direct" and target.url.startswith("https://")
    finally:
        window.close()
        app.processEvents()
        client.close()
        db.close()

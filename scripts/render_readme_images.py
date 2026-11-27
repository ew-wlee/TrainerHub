"""Render README illustrations from the real UI using isolated example data.

Run from the repository root: python scripts/render_readme_images.py
The script never connects to the network or opens the user's TrainerHub data.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["TRAINERHUB_REDUCED_MOTION"] = "1"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from trainerhub.core.config import Config  # noqa: E402
from trainerhub.core.db import Database  # noqa: E402
from trainerhub.core.library import LibraryService  # noqa: E402
from trainerhub.core.models import (  # noqa: E402
    CatalogItem,
    InstalledItem,
    RecommendationEntry,
    RecommendationPlan,
    SteamGame,
)
from trainerhub.core.mods import ModService  # noqa: E402
from trainerhub.core.search import SearchEngine  # noqa: E402
from trainerhub.i18n import set_language  # noqa: E402
from trainerhub.ui.main_window import MainWindow  # noqa: E402
from trainerhub.ui.theme import apply  # noqa: E402

OUTPUT = ROOT / "docs" / "images" / "readme"
NAMES = ("Hades II", "Cyberpunk 2077", "Elden Ring", "Black Myth: Wukong")


def settle(app: QApplication) -> None:
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def render(language: str, base: Path, app: QApplication) -> None:
    set_language(language)
    cfg = Config(base / "config.json", {"library_dir": str(base / "library"), "discovery": {"enabled": False}})
    db = Database(base / "catalog.db")
    items = [
        CatalogItem("fling", str(i), name + " Trainer", name, version="v1.0", options_count=24 + i,
                    file_size=920_000, supports_direct_download=True, detail_loaded=True)
        for i, name in enumerate(NAMES)
    ]
    db.upsert_items(items)
    for i, item in enumerate(items[:2]):
        db.installed_upsert(InstalledItem("fling", str(i), item.game_name, "v1.0", str(base / "library" / str(i)),
                                          installed_at=f"2026-11-{25 - i}T10:00:00"))
    sources = {"fling": SimpleNamespace(supports_direct_download=True, requires_detail=False)}
    window = MainWindow(config=cfg, search=SearchEngine(), library=LibraryService(cfg.library_dir, db),
                        sources=sources, workers={}, items=items)
    window.resize(1200, 675)
    window.show()
    settle(app)
    cfg.set("discovery.enabled", True, save=False)
    games = [SteamGame(str(i), item.game_name, "", "") for i, item in enumerate(items)]
    window.discovery_controller.games = games
    window.discovery_controller.plan = RecommendationPlan(entries=[
        RecommendationEntry(game, item, "high", "", selected=(i >= 2), state="installed" if i < 2 else "ready")
        for i, (game, item) in enumerate(zip(games, items, strict=True))
    ])
    window._render_plan(window.discovery_controller.plan)
    window._refresh_library()
    settle(app)
    assert window.grab().save(str(OUTPUT / f"discover-{language}.png"))

    window.search_box.setText("Elden Ring")
    window._search_timer.stop()
    window._remote_timer.stop()
    window._run_search()
    window.discover.select_row(0)
    settle(app)
    assert window.grab().save(str(OUTPUT / f"search-{language}.png"))

    window._switch_page("library")
    window.downloads.add_job("fling:2", items[2], "FLiNG")
    window.downloads.update_state("fling:2", "downloading")
    window.downloads.update_progress("fling:2", 620, 1000)
    settle(app)
    assert window.grab().save(str(OUTPUT / f"library-{language}.png"))
    render_mods(window, language, base, app)
    window.cleanup()
    window.close()
    settle(app)
    db.close()


def render_mods(window: MainWindow, language: str, base: Path, app: QApplication) -> None:
    """Use real file operations on isolated examples, never the user's games."""
    chinese = language == "zh_CN"
    library = base / "Steam"
    root = library / "steamapps/common/ExampleGame"
    root.mkdir(parents=True)
    game = SteamGame("123456", "Steam 示例游戏" if chinese else "Example Steam game", str(library), str(root))
    examples = [
        ("modExampleHUD", "界面精简（示例）" if chinese else "HUD layout (example)", "1.2"),
        ("modExampleTextures", "环境纹理（示例）" if chinese else "Textures (example)", "2.0"),
        ("modUnreviewed", "待核对内容（示例）" if chinese else "Unreviewed content (example)", "0.9"),
    ]
    for directory, name, version in examples:
        folder = root / "Mods" / directory
        (folder / "content").mkdir(parents=True)
        (folder / "content/example.bin").write_bytes(b"README example, not a real Mod")
        (folder / "manifest.json").write_text(json.dumps({"Name": name, "Version": version}, ensure_ascii=False), encoding="utf-8")
    service = ModService(base / "Mods", running=lambda _: False)
    report = service.scan([game])
    for record in report.records:
        if record.reason == "unconfirmed" and record.entries != ["modUnreviewed"]:
            service.confirm(record.id)
    textures = next(record for record in service.read().records if record.entries == ["modExampleTextures"])
    report = service.toggle([textures.id], False)
    window.mods_page.controller.initialized = True
    window.mods_page.controller.report = report
    window.mods_page.set_report(report)
    window._switch_page("mods")
    QTest.qWait(220)  # Let the native search clear-button fade finish before capture.
    settle(app)
    assert window.grab().save(str(OUTPUT / f"mods-{language}.png"))


def main() -> None:
    app = QApplication([])
    if sys.platform == "win32":
        for name in ("msyh.ttc", "msyhbd.ttc", "segoeui.ttf", "seguisym.ttf"):
            QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name))
    apply(app)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    cache = ROOT / ".pytest_cache"
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="readme-", dir=cache) as temporary:
        assert Path(temporary).resolve().is_relative_to(cache.resolve())
        for language in ("zh_CN", "en_US"):
            folder = Path(temporary) / language
            folder.mkdir()
            render(language, folder, app)
    print(f"Saved examples to {OUTPUT}")


if __name__ == "__main__":
    main()

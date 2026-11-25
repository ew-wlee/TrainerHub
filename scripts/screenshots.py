"""Generate README screenshots headlessly (``QT_QPA_PLATFORM=offscreen``).

Run:  .venv/bin/python scripts/screenshots.py
"""

from __future__ import annotations

import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from trainerhub.app import TrainerHubApp  # noqa: E402
from trainerhub.core.models import InstalledItem  # noqa: E402
from trainerhub.i18n import tr  # noqa: E402
from trainerhub.ui.dialogs.welcome_wizard import WelcomeWizard  # noqa: E402
from trainerhub.ui.pages.library_page import InstalledRow  # noqa: E402

OUT = ROOT / "docs" / "screenshots"

# (source, game name, version to "install", bytes) — the versions differ from the
# catalogue on purpose so the update badge has something to show.
DEMO_INSTALLS = [
    ("fling", "Inazuma Eleven: Victory Road", "Plus 37", 1_820_000),
    ("fling", "The Legend of Heroes: Trails Through Daybreak II", "Plus 60", 14_600_000),
    ("xiaoxing", "黑神话：悟空", "v1.6.2", 4_400_000),
]


def wait(app: QApplication, ms: int) -> None:
    end = time.time() + ms / 1000
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def grab(widget, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    widget.grab().save(str(path))
    print("saved", path)


def seed_library(controller: TrainerHubApp) -> list[InstalledItem]:
    """Install a few placeholder trainers so the library screenshot isn't empty.

    Files are sparse stubs — nothing here is a real trainer and the records are
    removed again by :func:`clear_library` before the process exits.
    """
    if controller.db.installed_all():
        print("library already has entries — skipping demo seeding")
        return []

    by_title = {item.game_name: item for item in controller.db.all_items()}
    display = {sid: tr(source.name_key) for sid, source in controller.sources.items()}
    staging = Path(tempfile.mkdtemp(prefix="trainerhub-demo-"))
    records: list[InstalledItem] = []
    for source_id, game_name, version, size in DEMO_INSTALLS:
        item = by_title.get(game_name)
        if item is None or item.source_id != source_id:
            print("skip demo install (not indexed):", game_name)
            continue
        stub = staging / f"{game_name} Trainer.exe"
        with stub.open("wb") as handle:
            handle.truncate(size)
        try:
            records.append(
                controller.library.install(
                    replace(item, version=version),
                    [stub],
                    source_name=display.get(item.source_id, item.source_id),
                )
            )
        except Exception as exc:  # noqa: BLE001
            print("demo install failed:", game_name, exc)
    return records


def clear_library(controller: TrainerHubApp, records: list[InstalledItem]) -> None:
    for record in records:
        controller.library.delete(record)
    root = controller.library.root
    for folder in (root / "fling", root / "xiaoxing", root):
        try:
            folder.rmdir()
        except OSError:
            pass


def main() -> int:
    controller = TrainerHubApp(sys.argv)
    controller.config.set("first_run", False, save=False)
    controller._show_window()
    window = controller.window
    app = controller.app
    window.setFixedSize(1024, 576)
    wait(app, 500)

    # Warm the first few FLiNG rows so their version pills are populated —
    # FLiNG only exposes "Plus N" on the detail page.
    fling = controller.sources.get("fling")
    if fling is not None:
        for item in [i for i in controller.db.all_items() if i.source_id == "fling"][:6]:
            if item.detail_loaded and item.version:
                continue
            try:
                controller.db.save_detail(fling.fetch_detail(item))
            except Exception as exc:  # noqa: BLE001
                print("warm-up skipped:", exc)
        window._load_items()

    if controller.db.item_count() == 0:
        print("index is empty — run a sync first")
        return 1

    # Seed the library first so the list can show installed dots.
    demo_records = seed_library(controller)
    window._load_items()
    wait(app, 300)

    # 1) Discover, all sources — pick a row that is not installed so the
    # inspector shows the download action.
    window.rail.set_active_source("all")
    window._on_source_filter("all")
    window._switch_page("discover")
    window._run_search()
    wait(app, 300)
    model = window.discover.model
    target = next(
        (row for row in range(model.rowCount()) if model.item_at(row).game_name == "Final Fantasy VII Remake Intergrade"),
        0,
    )
    window.discover.select_row(target)
    wait(app, 2200)
    grab(window, "01-discover.png")

    # 2) Chinese source + detail with options
    window.rail.set_active_source("xiaoxing")
    window._on_source_filter("xiaoxing")
    wait(app, 500)
    window.discover.select_row(0)
    wait(app, 800)
    grab(window, "02-detail-zh.png")

    # 3) Downloads — one row per lifecycle state so the states are documented.
    window._switch_page("downloads")
    items = controller.db.all_items()
    small = [item for item in items if item.source_id == "fling"][:5]
    plan = [
        ("downloading", (1_112_000, 1_780_000), ""),
        ("extracting", (0, 0), ""),
        ("queued", (0, 0), ""),
        ("done", (0, 0), ""),
        ("failed", (0, 0), "远端文件已删除（404）"),
    ]
    for index, item in enumerate(small):
        job_id = f"{item.source_id}:{item.remote_id}"
        state, progress, message = plan[index]
        window.downloads.add_job(job_id, item, "FLiNG Trainer")
        window.downloads.update_state(job_id, state, message)
        if progress[1]:
            window.downloads.update_progress(job_id, *progress)
    wait(app, 300)
    grab(window, "03-downloads.png")

    # 4) Library — seeded above; show the hover actions on one row.
    window._switch_page("library")
    wait(app, 300)
    rows = window.library_page.container.findChildren(InstalledRow)
    if rows:
        rows[0]._show_actions(True)
    wait(app, 120)
    grab(window, "04-library.png")

    # 5) Settings
    window._switch_page("settings")
    wait(app, 300)
    grab(window, "05-settings.png")

    # 6) Wizard
    wizard = WelcomeWizard(controller.config)
    wizard.accept_check.setChecked(True)
    wizard.resize(620, 460)
    wizard.show()
    wait(app, 300)
    grab(wizard, "06-wizard.png")
    wizard.close()

    clear_library(controller, demo_records)

    QTimer.singleShot(50, app.quit)
    app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

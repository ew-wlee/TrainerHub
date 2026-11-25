from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, QPoint, Qt, Signal
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from trainerhub.core.config import Config
from trainerhub.core.db import Database
from trainerhub.core.library import LibraryService
from trainerhub.core.models import (
    CatalogItem,
    InstalledItem,
    RecommendationEntry,
    RecommendationPlan,
    ScanReport,
    SteamGame,
)
from trainerhub.core.search import SearchEngine
from trainerhub.ui.main_window import MainWindow
from trainerhub.ui.widgets.trainer_list import ROW_HEIGHT


@pytest.fixture(scope="session")
def app():
    application = QApplication.instance() or QApplication([])
    return application


class DownloadStub(QObject):
    job_state = Signal(str, str, str)
    job_progress = Signal(str, int, int)
    job_done = Signal(object)
    job_failed = Signal(str, str)
    job_external = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.queued = []

    def enqueue(self, item):
        self.queued.append(item)

    def stop(self):
        pass

    def isRunning(self):  # noqa: N802
        return False


@pytest.fixture
def window(app, tmp_path):
    config = Config(tmp_path / "config.json", {"library_dir": str(tmp_path / "trainers")})
    db = Database(tmp_path / "catalog.db")
    downloads = DownloadStub()
    sources = {
        "fling": SimpleNamespace(supports_direct_download=True, requires_detail=False),
        "xiaoxing": SimpleNamespace(supports_direct_download=False, requires_detail=False),
    }
    view = MainWindow(config=config, search=SearchEngine(), library=LibraryService(config.library_dir, db),
                      sources=sources, workers={"download": downloads}, items=[])
    view.show()
    QTest.qWait(10)
    yield view
    view.close()
    QApplication.processEvents()
    db.close()


def item(source="fling", name="Elden Ring", alias="", remote="elden-ring"):
    return CatalogItem(source, remote, name + " Trainer", name, game_alias=alias,
                       page_url="https://example.test/trainer", supports_direct_download=source == "fling")


def game(name="Elden Ring", appid="1245620"):
    return SteamGame(appid, name, "/Steam", "/Steam/steamapps/common/" + name)


def install_plan(window, entries):
    controller = window.discovery_controller
    window.config.set("discovery.enabled", True, save=False)
    controller.plan = RecommendationPlan(entries=entries)
    controller.games = [entry.game for entry in entries]
    controller.plan_changed.emit(controller.plan)
    QApplication.processEvents()


def wait_until(predicate, timeout=2000):
    deadline = time.monotonic() + timeout / 1000
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert predicate()


def test_first_screen_is_one_title_and_scan_button(window):
    assert window.discover.empty.title.text()
    assert window.discover.empty.body.isHidden()
    assert window.discover.empty.glyph.isHidden()
    assert window.discover.empty.action.isVisible()
    assert window.discover.toolbar.isHidden()
    assert window.discover.detail.isHidden()
    assert window.status_label.text() == ""
    assert window.size().width() == 1024
    assert ROW_HEIGHT == 56
    assert not window.config.get("discovery.scan_on_start")


def test_checkbox_does_not_open_inspector_or_enqueue(window):
    entry = RecommendationEntry(game(), item(), "medium", "Local alias")
    install_plan(window, [entry])
    selected = QSignalSpy(window.discover.selection_changed)
    rect = window.discover.view.visual_rect_for_row(0)
    QTest.mouseClick(window.discover.view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(24, rect.center().y()))
    assert not entry.selected
    assert selected.count() == 0
    assert window.discover.detail.isHidden()
    assert window.download_worker.queued == []


def test_row_selection_opens_only_detail_and_medium_download_has_no_confirmation(window):
    entry = RecommendationEntry(game(), item(), "medium", "Local alias")
    install_plan(window, [entry])
    rect = window.discover.view.visual_rect_for_row(0)
    QTest.mouseClick(window.discover.view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(100, rect.center().y()))
    assert window.discover.detail.isVisible()
    assert window.discover.detail.match_note.isHidden()
    assert window.download_worker.queued == []
    QTest.mouseClick(window.discover.batch_button, Qt.MouseButton.LeftButton)
    assert window.download_worker.queued == [entry.item]
    assert entry.state == "queued"
    assert not entry.selected
    assert window.stack.currentWidget() is window.discover
    window._enqueue_download(entry.item)
    assert len(window.download_worker.queued) == 1


def test_select_all_and_batch_only_affect_visible_source(window):
    first = RecommendationEntry(game(), item(), "high", "Exact")
    hidden = RecommendationEntry(game("Control", "870780"), item("custom", "Control", remote="control"), "high", "Exact")
    window.config.set("sources.custom.enabled", True, save=False)
    window.sources["custom"] = SimpleNamespace(supports_direct_download=True, requires_detail=False)
    install_plan(window, [first, hidden])
    window.source_filter = "fling"
    window.discovery_controller.plan_changed.emit(window.discovery_controller.plan)
    assert window.discover.model.rowCount() == 1
    QTest.mouseClick(window.discover.select_all, Qt.MouseButton.LeftButton)
    assert not first.selected
    assert hidden.selected
    QTest.mouseClick(window.discover.select_all, Qt.MouseButton.LeftButton)
    assert first.selected
    assert hidden.selected
    QTest.mouseClick(window.discover.batch_button, Qt.MouseButton.LeftButton)
    assert window.download_worker.queued == [first.item]
    assert hidden.state == "ready"
    assert hidden.selected


def test_detail_ready_replaces_plan_item_reference(window):
    original = item()
    entry = RecommendationEntry(game(), original, "high", "Exact")
    install_plan(window, [entry])
    window.items = [original]
    window._on_selection(original)
    detailed = original.clone(detail_loaded=True, version="1.2", file_size=128)
    window._on_detail_ready(detailed)
    assert entry.item is detailed
    assert window.discovery_controller.entry_for(original.key).item.detail_loaded
    window.search_box.setText("Elden")
    window._search_timer.stop()
    window._remote_timer.stop()
    window._run_search()
    window.search_box.clear()
    assert window.discover.model.item_at(0) is detailed


def test_deleting_installed_record_forgets_done_state_and_rebuilds(window, monkeypatch):
    original = item()
    entry = RecommendationEntry(game(), original, "high", "Exact", selected=False, state="installed")
    install_plan(window, [entry])
    db = window.library.db
    db.upsert_items([original])
    db.save_steam_scan(ScanReport([game()], {"/Steam": "ok"}))
    record = InstalledItem("fling", "elden-ring", "Elden Ring", "1", "/trainers/elden")
    db.installed_upsert(record)
    window.discovery_controller.update_job(original.key, "done")
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(window.library, "delete", lambda value: db.installed_delete(*value.key))
    window._delete_record(record)
    wait_until(lambda: not window.discovery_controller.busy)
    rebuilt = window.discovery_controller.entry_for(original.key)
    assert rebuilt.state == "ready"
    assert original.key not in window.discovery_controller._job_states
    assert window.discover.model.index(0, 0).flags() & Qt.ItemFlag.ItemIsUserCheckable


def test_owned_and_external_cannot_be_checked(window, monkeypatch):
    owned = RecommendationEntry(game(), item(), "high", "Exact", selected=False, state="installed")
    external = RecommendationEntry(game("Other Game", "2"), item("xiaoxing", "Other Game", remote="other"),
                                   "medium", "Exact", selected=False, action="external")
    install_plan(window, [owned, external])
    for row in range(2):
        index = window.discover.model.index(row, 0)
        assert not index.flags() & Qt.ItemFlag.ItemIsUserCheckable
    opened = []
    monkeypatch.setattr(window, "_open_page", lambda value: opened.append(value))
    window._enqueue_download(external.item)
    assert opened == [external.item]
    assert window.download_worker.queued == []
    assert external.state == "ready"


def test_search_clear_restores_plan_choices(window):
    first = RecommendationEntry(game(), item(), "high", "Exact", selected=False)
    install_plan(window, [first])
    window.library.db.upsert_items([first.item])
    window.search.rebuild([first.item])
    window.search_box.setText("Elden")
    window._search_timer.stop()
    window._remote_timer.stop()
    window._run_search()
    assert window.discover.model.entry_at(0) is None
    window.search_box.clear()
    assert window.discover.model.entry_at(0) is first
    assert not first.selected


def test_local_and_remote_preference_applied_before_xiaoxing_filter(window):
    local = item("xiaoxing", "艾尔登法环", "Elden Ring")
    remote = item()
    window.search.rebuild([local])
    window.source_filter = "xiaoxing"
    window.search_box.setText("艾尔登法环")
    window._search_timer.stop()
    window._remote_timer.stop()
    generation = window._search_generation
    assert "Elden Ring" in window._remote_terms("艾尔登法环")
    window._on_remote_results(generation, "艾尔登法环", "xiaoxing", [remote])
    assert window.discover.model.rowCount() == 0
    assert window.discover.empty.title.text() == "此游戏在 FLiNG"
    assert window.discover.empty.action.isVisible()
    QTest.mouseClick(window.discover.empty.action, Qt.MouseButton.LeftButton)
    window._remote_timer.stop()
    assert window.source_filter == "all"
    assert window.discover.model.item_at(0).source_id == "fling"


def test_stale_remote_results_never_populate_cache_or_list(window):
    window.search_box.setText("Elden")
    old_generation = window._search_generation
    window.search_box.setText("Elden Ring")
    window._search_timer.stop()
    window._remote_timer.stop()
    window._on_remote_results(old_generation, "Elden", "all", [item()])
    assert window._remote_cache == {}
    assert window._remote_items == {}
    window.config.set("sources.fling.enabled", False, save=False)
    window._on_remote_results(window._search_generation, "Elden Ring", "all", [item()])
    assert window._remote_cache == {}


def test_empty_remote_result_is_not_negative_cached(window):
    window.search_box.setText("Elden")
    window._search_timer.stop()
    window._remote_timer.stop()
    window._on_remote_results(window._search_generation, "Elden", "all", [])
    assert window._remote_cache == {}


def test_loading_failure_and_no_match_are_distinct_and_failure_can_retry(window, monkeypatch):
    window.search_box.setText("Missing Game")
    window._search_timer.stop()
    window._remote_timer.stop()
    generation = window._search_generation
    window._remote_state = "loading"
    window._run_search()
    loading_title = window.discover.empty.title.text()
    assert not window.discover.empty.action.isVisible()
    window._on_remote_failed(generation, "Missing Game", "all", "timeout")
    failed_title = window.discover.empty.title.text()
    assert failed_title != loading_title
    assert window.discover.empty.action.text() == "重试联网"
    assert window.discover.empty.action.isVisible()
    assert window.remote_retry_button.isHidden()
    scanned = QSignalSpy(window.discover.scan_requested)
    retried = []

    def restart():
        retried.append(window.search_box.text())
        window._remote_state = "loading"
        window._run_search()

    monkeypatch.setattr(window, "_start_remote_search", restart)
    QTest.mouseClick(window.discover.empty.action, Qt.MouseButton.LeftButton)
    assert retried == ["Missing Game"]
    assert window._search_generation > generation
    assert scanned.count() == 0
    assert window.discover.empty.title.text() == loading_title
    window._on_remote_results(window._search_generation, "Missing Game", "all", [])
    assert window.discover.empty.title.text() not in {loading_title, failed_title}
    assert window.discover.empty.action.isHidden()
    window.search_box.clear()
    assert window.discover.empty.action.text() != "重试联网"
    assert window.remote_retry_button.isHidden()


def test_failed_remote_search_keeps_local_list_and_compact_retry(window, monkeypatch):
    local = item()
    window.search.rebuild([local])
    window.search_box.setText("Elden Ring")
    window._search_timer.stop()
    window._remote_timer.stop()
    window._on_remote_failed(window._search_generation, "Elden Ring", "all", "network")
    assert window.discover.model.item_at(0).key == local.key
    assert window.remote_retry_button.isVisible()
    retried = []

    def restart():
        retried.append(True)
        window._remote_state = "loading"
        window._run_search()

    monkeypatch.setattr(window, "_start_remote_search", restart)
    QTest.mouseClick(window.remote_retry_button, Qt.MouseButton.LeftButton)
    assert retried == [True]
    assert window.discover.model.item_at(0).key == local.key
    assert window.remote_retry_button.isHidden()


def test_download_failure_and_external_return_to_plan(window):
    entry = RecommendationEntry(game(), item(), "high", "Exact")
    install_plan(window, [entry])
    window._enqueue_download(entry.item, switch_page=False)
    window._on_job_failed("fling:elden-ring", "failed")
    assert entry.state == "failed"
    window.discovery_controller.set_selected(entry.item.key, True)
    assert entry.selected
    window._on_job_external("fling:elden-ring", "")
    window._on_job_state("fling:elden-ring", "cancelled", "external")
    assert entry.action == "external"
    assert entry.state == "ready"
    assert not entry.selected


@pytest.mark.parametrize("action", ["cancel", "clear", "disable"])
def test_discovery_invalidates_before_late_reply(window, action):
    controller = window.discovery_controller
    window.config.set("discovery.enabled", True, save=False)
    generation = controller.generation
    scanned = game()
    report = ScanReport([scanned], {"/Steam": "ok"})
    if action == "disable":
        controller.set_enabled(False)
    else:
        getattr(controller, action)()
    assert controller.generation > generation
    controller._accept(generation, report, RecommendationPlan(), [scanned], set())
    assert window.library.db.steam_games() == []


def test_scan_and_matching_run_off_gui_thread_and_save_valid_report(window, monkeypatch):
    import trainerhub.workers.discovery_worker as worker_module

    ui_thread = threading.get_ident()
    observed = []
    scanned = game()

    def scan(paths, cancelled=None):
        observed.append(threading.get_ident())
        return ScanReport([scanned], {"/Steam": "ok"})

    original = worker_module.build_plan

    def build(*args, **kwargs):
        observed.append(threading.get_ident())
        return original(*args, **kwargs)

    monkeypatch.setattr(worker_module, "scan_steam", scan)
    monkeypatch.setattr(worker_module, "build_plan", build)
    window.library.db.upsert_items([item()])
    window._scan_steam()
    wait_until(lambda: not window.discovery_controller.busy)
    assert observed and all(thread != ui_thread for thread in observed)
    assert window.library.db.steam_games()[0].appid == scanned.appid
    assert len(window.discovery_controller.plan.entries) == 1


def test_scan_real_manifest_and_manual_path(window, tmp_path):
    root = tmp_path / "Steam"
    steamapps = root / "steamapps"
    install = steamapps / "common" / "Elden Ring"
    install.mkdir(parents=True)
    (steamapps / "appmanifest_1245620.acf").write_text(
        '"AppState" { "appid" "1245620" "name" "Elden Ring" "StateFlags" "4" "installdir" "Elden Ring" }',
        encoding="utf-8",
    )
    window.settings.steam_paths_edit.setText(str(root))
    window.settings._on_steam_paths()
    window.library.db.upsert_items([item()])
    window._scan_steam()
    wait_until(lambda: not window.discovery_controller.busy)
    scanned = window.library.db.steam_games()
    assert len(scanned) == 1
    assert scanned[0].install_path == str(install)
    assert window.discovery_controller.plan.entries[0].item.key == item().key


def test_partial_failed_scan_preserves_previous_library(window, monkeypatch):
    import trainerhub.workers.discovery_worker as worker_module

    old = game()
    window.library.db.save_steam_scan(ScanReport([old], {"/Steam": "ok"}))
    window.library.db.upsert_items([item()])
    monkeypatch.setattr(worker_module, "scan_steam", lambda *args, **kwargs: ScanReport([], {"/Steam": "unavailable"}))
    window._scan_steam()
    wait_until(lambda: not window.discovery_controller.busy)
    assert window.library.db.steam_games()[0].appid == old.appid
    assert window.discovery_controller.plan.entries[0].game.appid == old.appid


def test_invalid_library_games_are_not_added_to_db_or_plan(window, monkeypatch):
    import trainerhub.workers.discovery_worker as worker_module

    window.library.db.upsert_items([item()])
    monkeypatch.setattr(worker_module, "scan_steam", lambda *args, **kwargs: ScanReport([game()], {"/Steam": "invalid"}))
    window._scan_steam()
    wait_until(lambda: not window.discovery_controller.busy)
    assert window.library.db.steam_games() == []
    assert window.discovery_controller.games == []
    assert window.discovery_controller.plan.entries == []


def test_remote_requests_are_bounded_and_latest_pending_wins(window, monkeypatch):
    import trainerhub.ui.main_window as window_module

    class SearchStub(QObject):
        context_results = Signal(int, str, str, object)
        context_failed = Signal(int, str, str, str)
        finished = Signal()

        def __init__(self, term, parent=None, *, generation=0, source_filter="all", terms=None):
            super().__init__(parent)
            self.term = term
            self.generation = generation
            self.source_filter = source_filter
            self.terms = terms

        def start(self):
            pass

        def stop(self):
            pass

        def wait(self):
            pass

    monkeypatch.setattr(window_module, "SearchWorker", SearchStub)
    for query in ("one", "two", "three", "four"):
        window.search_box.setText(query)
        window._search_timer.stop()
        window._remote_timer.stop()
        window._start_remote_search()
    assert len(window._search_workers) == 2
    assert window._remote_pending[1] == "four"
    old = next(worker for worker in window._search_workers if worker.term == "one")
    old.context_results.emit(old.generation, old.term, old.source_filter, [item()])
    assert window._remote_cache == {}
    old.finished.emit()
    assert len(window._search_workers) == 2
    assert any(worker.term == "four" for worker in window._search_workers)
    assert window._remote_pending is None


def test_disabling_discovery_restores_minimal_empty_state(window):
    entry = RecommendationEntry(game(), item(), "high", "Exact")
    install_plan(window, [entry])
    window.discovery_controller.set_enabled(False)
    assert window.discover.toolbar.isHidden()
    assert window.discover.empty.action.isVisible()


def test_clear_requires_confirmation_and_keeps_installed_trainers(window, monkeypatch):
    db = window.library.db
    db.save_steam_scan(ScanReport([game()], {"/Steam": "ok"}))
    record = InstalledItem("fling", "elden-ring", "Elden Ring", "1", "/trainers/elden")
    db.installed_upsert(record)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Cancel)
    window.settings._clear_discovery()
    assert db.steam_games()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    window.settings._clear_discovery()
    assert db.steam_games() == []
    assert db.installed_all()[0].key == record.key
    assert not window.config.get("discovery.enabled")
    assert not window.config.get("discovery.scan_on_start")
    assert window.config.get("discovery.steam_paths") == []
    assert not window.settings.discovery_check.isChecked()
    assert not window.settings.scan_start_check.isChecked()
    assert window.settings.steam_paths_edit.text() == ""


def test_cleanup_waits_until_discovery_thread_finishes(window, monkeypatch):
    import trainerhub.workers.discovery_worker as worker_module

    ended = threading.Event()

    def scan(paths, cancelled=None):
        time.sleep(0.03)
        ended.set()
        return ScanReport(cancelled=bool(cancelled and cancelled()))

    monkeypatch.setattr(worker_module, "scan_steam", scan)
    window._scan_steam()
    QTest.qWait(5)
    window.shutdown_discovery()
    window.shutdown_discovery()
    assert ended.is_set()
    assert all(not worker.isRunning() for worker in window.discovery_controller._workers)


def test_library_search_is_local_and_preserves_installed_order(window):
    for remote, name, when in [("old", "Old Game", "2024-01-01"), ("new", "New Game", "2025-01-01")]:
        window.library.db.installed_upsert(InstalledItem("fling", remote, name, "1", "/tmp/" + remote, installed_at=when))
    window._switch_page("library")
    rows = [window.library_page.container_layout.itemAt(i).widget().record.game_name for i in range(2)]
    assert rows == ["New Game", "Old Game"]
    window.search_box.setText("old")
    assert window.library_page.container_layout.itemAt(0).widget().record.game_name == "Old Game"
    assert window.library_page.container_layout.count() == 2  # one row and stretch
    assert not window._remote_timer.isActive()
    window._switch_page("discover")
    assert window.search_box.text() == ""


def test_downloads_in_library_hide_completed_and_offer_retry(window):
    trainer = item()
    window._enqueue_download(trainer)
    job_id = "fling:elden-ring"
    assert window.stack.currentWidget() is window.library_page
    row = window.downloads._rows[job_id]
    assert not window.downloads.isHidden()
    window._on_job_state(job_id, "failed", "network error")
    assert not row.retry_button.isHidden()
    QTest.mouseClick(row.retry_button, Qt.MouseButton.LeftButton)
    assert len(window.download_worker.queued) == 2
    window._on_job_state(job_id, "done", "")
    assert window.downloads.isHidden()


def test_welcome_sources_default_selected_without_changing_existing_settings(app, tmp_path):
    from trainerhub.ui.dialogs.welcome_wizard import WelcomeWizard

    config = Config(tmp_path / "config.json", {"sources": {"xiaoxing": {"enabled": False}}})
    wizard = WelcomeWizard(config)
    assert all(check.isChecked() for check in wizard.source_checks.values())
    assert not config.source_enabled("xiaoxing")
    wizard._apply()
    assert all(config.source_enabled(source) for source in ("fling", "xiaoxing", "custom"))
    assert config.get("sources.custom.index_url") == ""

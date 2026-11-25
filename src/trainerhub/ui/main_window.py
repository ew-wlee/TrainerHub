"""Main window: brand + search bar, rail, pages, on-demand inspector."""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, VERSION
from ..core.config import Config
from ..core.library import LibraryService, open_in_file_manager
from ..core.models import CatalogItem, InstalledItem
from ..core.paths import resource_path
from ..core.search import SearchEngine
from ..core.source_policy import select_preferred
from ..core.textutil import normalize
from ..core.updater import UpdateService
from ..i18n import tr
from ..workers.detail_worker import DetailWorker
from ..workers.download_worker import DownloadWorker
from ..workers.search_worker import SearchWorker
from ..workers.sync_worker import SyncWorker
from .dialogs.scanned_games_dialog import ScannedGamesDialog
from .discovery_controller import ACTIVE_STATES, DiscoveryController
from .pages.discover_page import DiscoverPage
from .pages.downloads_page import DownloadsPage
from .pages.library_page import LibraryPage
from .pages.settings_page import SettingsPage
from .widgets.source_rail import SourceRail
from .widgets.toast import Toast

SOURCE_LABEL_KEYS = {
    "all": "source.all",
    "fling": "source.fling",
    "xiaoxing": "source.xiaoxing",
    "custom": "source.custom",
    "local": "source.local",
}


class MainWindow(QMainWindow):
    language_change_requested = Signal(str)

    def __init__(
        self,
        *,
        config: Config,
        search: SearchEngine,
        library: LibraryService,
        sources: dict,
        workers: dict,
        items: list[CatalogItem],
        on_rebuild: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.search = search
        self.library = library
        self.sources = sources
        self.items = items
        self.on_rebuild = on_rebuild
        self.source_filter = "all"
        self._current: CatalogItem | None = None
        self._detail_pending: set[tuple[str, str]] = set()

        self._remote_items: dict[tuple[str, str], CatalogItem] = {}
        self._remote_cache: dict[tuple[str, str], tuple[float, list[CatalogItem]]] = {}
        self._search_workers: set[SearchWorker] = set()
        self._search_generation = 0
        self._remote_state = "idle"
        self._remote_pending: tuple[int, str, str] | None = None
        self._closing = False
        self._was_searching = False
        self._plan_current_key: tuple[str, str] | None = None
        self._active_jobs: set[str] = set()
        self._external_jobs: set[str] = set()
        self.discovery_controller = DiscoveryController(config, library.db, self)

        self.sync_worker: SyncWorker | None = workers.get("sync")
        self.detail_worker: DetailWorker | None = workers.get("detail")
        self.download_worker: DownloadWorker | None = workers.get("download")

        self.setWindowTitle(f"{APP_NAME} · {VERSION}")
        self.setWindowIcon(QIcon(str(resource_path("resources", "app_mark.svg"))))
        self.setMinimumSize(960, 540)
        self.resize(1024, 576)

        self._build_ui()
        self._wire()
        self._load_items(initial=True)
        QTimer.singleShot(0, self.discovery_controller.initialize)

    # -- construction -----------------------------------------------------
    def _source_names(self) -> dict[str, str]:
        names = {source_id: tr(key) for source_id, key in SOURCE_LABEL_KEYS.items()}
        if self.download_worker is not None:
            self.download_worker.source_names = names
        return names

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)

        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        enabled = {sid: tr(SOURCE_LABEL_KEYS.get(sid, sid)) for sid in self.sources}
        self.rail = SourceRail(enabled)
        outer.addWidget(self.rail)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # -- top bar -----------------------------------------------------
        top_bar = QWidget()
        top_bar.setObjectName("TopBar")
        top_bar.setFixedHeight(52)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(14, 8, 14, 8)
        top_layout.setSpacing(10)

        self.brand = QLabel(tr("nav.discover"))
        self.brand.setObjectName("BrandName")

        self.search_box = QLineEdit()
        self.search_box.setObjectName("SearchBox")
        self.search_box.setPlaceholderText(tr("search.placeholder"))
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setFixedWidth(300)

        self.status_label = QLabel("")
        self.status_label.setObjectName("TopStatus")
        self.status_label.setMaximumWidth(280)

        self.sync_button = QPushButton("⟳")
        self.sync_button.setObjectName("IconButton")
        self.sync_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sync_button.setToolTip(tr("action.sync"))

        self.remote_retry_button = QPushButton(tr("search.remote.retry"))
        self.remote_retry_button.setObjectName("LinkButton")
        self.remote_retry_button.clicked.connect(self._retry_remote_search)
        self.remote_retry_button.hide()

        self.settings_button = QPushButton("⚙")
        self.settings_button.setObjectName("IconButton")
        self.settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_button.setToolTip(tr("nav.settings"))

        top_layout.addWidget(self.brand)
        top_layout.addStretch(1)
        top_layout.addWidget(self.search_box)
        top_layout.addWidget(self.status_label)
        top_layout.addWidget(self.remote_retry_button)
        top_layout.addWidget(self.sync_button)
        top_layout.addWidget(self.settings_button)
        right_layout.addWidget(top_bar)

        # -- pages -------------------------------------------------------
        self.stack = QStackedWidget()
        self.discover = DiscoverPage()
        self.downloads = DownloadsPage()
        self.library_page = LibraryPage()
        self.settings = SettingsPage(self.config)
        self.discover.set_source_names(self._source_names())
        self.stack.addWidget(self.discover)
        self.library_page.add_downloads(self.downloads)
        self.stack.addWidget(self.library_page)
        self.stack.addWidget(self.settings)
        right_layout.addWidget(self.stack, 1)

        outer.addWidget(right, 1)
        self.toast = Toast(root)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(170)
        self._search_timer.timeout.connect(self._run_search)

        self._remote_timer = QTimer(self)
        self._remote_timer.setSingleShot(True)
        self._remote_timer.setInterval(320)
        self._remote_timer.timeout.connect(self._start_remote_search)

    def _wire(self) -> None:
        self.rail.navigate.connect(self._switch_page)
        self.rail.source_changed.connect(self._on_source_filter)
        self.search_box.textChanged.connect(self._on_search_text)
        self.sync_button.clicked.connect(self.start_sync)
        self.settings_button.clicked.connect(lambda: self._switch_page("settings"))

        self.discover.selection_changed.connect(self._on_selection)
        self.discover.download_requested.connect(self._enqueue_download)
        self.discover.open_page_requested.connect(self._open_page)
        self.discover.open_folder_requested.connect(self._open_folder)
        self.discover.run_requested.connect(self._run_catalog_item)
        self.discover.delete_requested.connect(self._delete_catalog_item)
        self.discover.sync_requested.connect(self.start_sync)
        self.discover.closed.connect(self._on_inspector_closed)
        controller = self.discovery_controller
        self.discover.scan_requested.connect(self._scan_steam)
        self.discover.retry_remote_requested.connect(self._retry_remote_search)
        self.discover.show_all_requested.connect(self._show_all_search)
        self.discover.cancel_scan_requested.connect(controller.cancel)
        self.discover.manage_requested.connect(self._manage_scanned_games)
        self.discover.batch_requested.connect(self._download_selected)
        self.discover.checked_changed.connect(controller.set_selected)
        self.discover.select_all_requested.connect(lambda selected: controller.select_all(selected, source_filter=self.source_filter))
        self.discover.detail.exclude_requested.connect(lambda appid: controller.set_excluded(appid, True))
        controller.plan_changed.connect(self._render_plan)
        controller.state_changed.connect(self._on_discovery_state)
        controller.failed.connect(lambda message: self.toast.show_message(message[:160], 3600))

        self.downloads.cancel_requested.connect(self._cancel_download)
        self.downloads.retry_requested.connect(lambda item: self._enqueue_download(item, switch_page=False))

        self.library_page.import_requested.connect(self._import_folder)
        self.library_page.update_check_requested.connect(self._check_updates)
        self.library_page.open_requested.connect(lambda record: open_in_file_manager(Path(record.path)))
        self.library_page.run_requested.connect(self._run_trainer)
        self.library_page.delete_requested.connect(self._delete_record)

        self.settings.language_changed.connect(self._on_language_changed)
        self.settings.library_changed.connect(self._on_library_changed)
        self.settings.sources_changed.connect(self._on_sources_changed)
        self.settings.discovery_changed.connect(controller.set_enabled)
        self.settings.discovery_paths_changed.connect(controller.cancel)
        self.settings.discovery_clear_requested.connect(self._clear_discovery)
        self.settings.discovery_scan_requested.connect(self._scan_steam)

        if self.detail_worker is not None:
            self.detail_worker.detail_ready.connect(self._on_detail_ready)
            self.detail_worker.detail_failed.connect(self._on_detail_failed)
        if self.download_worker is not None:
            self.download_worker.job_state.connect(self._on_job_state)
            self.download_worker.job_progress.connect(self.downloads.update_progress)
            self.download_worker.job_progress.connect(self._on_job_progress)
            self.download_worker.job_done.connect(self._on_job_done)
            self.download_worker.job_failed.connect(self._on_job_failed)
            self.download_worker.job_external.connect(self._on_job_external)

        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self._close_inspector)

        geometry = self.config.get("ui.window_geometry", "")
        if geometry:
            try:
                self.restoreGeometry(bytes.fromhex(geometry))
            except ValueError:
                pass

    # -- status -----------------------------------------------------------
    def _set_status(self, text: str, timeout_ms: int = 0) -> None:
        self.status_label.setText(text)
        self.status_label.setToolTip(text)
        if timeout_ms:
            QTimer.singleShot(timeout_ms, lambda: self.status_label.setText("") if self.status_label.text() == text else None)

    # -- items & search ---------------------------------------------------
    def _load_items(self, *, initial: bool = False) -> None:
        self.items = self._db_items()
        self.search.rebuild(self.items)
        self._run_search()
        self._refresh_library()
        if not initial:
            self.discovery_controller.rebuild_plan()

    def _db_items(self) -> list[CatalogItem]:
        return self.library.db.all_items()

    def _installed_keys(self) -> set[tuple[str, str]]:
        return {record.key for record in self.library.db.installed_all()}

    def _invalidate_search(self) -> None:
        self._search_generation += 1
        self._remote_pending = None
        self._remote_items.clear()
        self._remote_state = "idle"
        self.remote_retry_button.hide()
        if not self.discovery_controller.busy:
            self._set_status("")
        for worker in self._search_workers:
            worker.stop()

    def _on_source_filter(self, source_id: str) -> None:
        self.source_filter = source_id
        self.config.set("ui.last_source", source_id)
        self._invalidate_search()
        if self.stack.currentWidget() is not self.discover:
            self._switch_page("discover")
        self._remote_timer.start()

    def _on_search_text(self, text: str) -> None:
        if self.stack.currentWidget() is self.library_page:
            self._refresh_library()
            return
        searching = bool(text.strip())
        if searching and not self._was_searching:
            self._plan_current_key = self._current.key if self._current else None
        self._was_searching = searching
        self._invalidate_search()
        self._close_inspector()
        if not searching:
            self._search_timer.stop()
            self._remote_timer.stop()
            self._run_search()
        else:
            self._search_timer.start()
            self._remote_timer.start()

    def _run_search(self) -> None:
        query = self.search_box.text().strip()
        if self._closing:
            return
        if not query:
            self.remote_retry_button.hide()
            self._render_plan(self.discovery_controller.plan)
            if self._plan_current_key is not None:
                row = self.discover.model.row_of(self._plan_current_key)
                if row >= 0:
                    self.discover.select_row(row)
                self._plan_current_key = None
            return
        hits = self.search.query(query, source_id="all", limit=2000)
        if self._remote_items:
            hits = [hit for hit in hits if hit.score >= 380]
        local_items = [hit.item for hit in hits if self.config.source_enabled(hit.item.source_id) or hit.item.source_id == "local"]
        merged = local_items + list(self._remote_items.values())
        items = select_preferred(merged, remote_state=self._remote_state, source_filter=self.source_filter)
        self.discover.set_remote_keys(set(self._remote_items.keys()))
        self.discover.set_installed_keys(self._installed_keys())

        self.remote_retry_button.setVisible(bool(items) and self._remote_state == "failed" and self._remote_allowed(query))
        if not items:
            preferred_suppressed = (self.source_filter == "xiaoxing"
                                    and any(item.source_id == "xiaoxing" for item in merged)
                                    and any(item.source_id == "fling" for item in merged))
            self.discover.set_empty_mode("noresult", query, remote_state=self._remote_state,
                                         preferred_suppressed=preferred_suppressed)
            self._current = None
            return

        self.discover.set_items(items)
        if self._current is not None and self._current.key in {item.key for item in items}:
            row = self.discover.model.row_of(self._current.key)
            if row >= 0:
                self.discover.select_row(row)
        else:
            self._current = None
            self.discover.hide_detail()

    # -- live search ------------------------------------------------------
    def _retry_remote_search(self) -> None:
        query = self.search_box.text().strip()
        if not self._remote_allowed(query):
            return
        self._search_timer.stop()
        self._remote_timer.stop()
        self._remote_cache.pop((normalize(query), self.source_filter), None)
        self._invalidate_search()
        self._start_remote_search()

    def _show_all_search(self) -> None:
        known_remote = dict(self._remote_items)
        self.rail.set_active_source("all")
        self._on_source_filter("all")
        if known_remote:
            self._remote_items = known_remote
            self._remote_state = "ready"
            self._run_search()

    def _remote_allowed(self, query: str) -> bool:
        return (self.stack.currentWidget() is self.discover and not self._closing and len(query) >= 2 and self.source_filter in {"all", "fling", "xiaoxing"}
                and self.config.source_enabled("fling") and "fling" in self.sources)

    def _remote_terms(self, query: str) -> list[str]:
        terms = [query]
        for hit in self.search.query(query, source_id="all", fuzzy=False, limit=8):
            if hit.score < 700 or not self.config.source_enabled(hit.item.source_id):
                continue
            for name in (hit.item.game_alias, hit.item.game_name):
                name = name.strip()
                if len(name) >= 2 and name.isascii() and any(c.isalpha() for c in name) and name.casefold() not in {term.casefold() for term in terms}:
                    terms.append(name)
            if len(terms) >= 3:
                break
        return terms[:3]

    def _start_remote_search(self) -> None:
        query = self.search_box.text().strip()
        if not self._remote_allowed(query):
            return
        key = (normalize(query), self.source_filter)
        cached = self._remote_cache.get(key)
        if cached is not None and time.monotonic() - cached[0] < 120:
            self._remote_items = {item.key: item for item in cached[1]}
            self._remote_state = "ready"
            self._run_search()
            return
        self._remote_cache.pop(key, None)
        context = (self._search_generation, query, self.source_filter)
        if any((worker.generation, worker.term, worker.source_filter) == context for worker in self._search_workers):
            return
        self._remote_pending = context
        self._remote_state = "loading"
        self._run_search()
        self._launch_remote_pending()

    def _launch_remote_pending(self) -> None:
        if self._closing or self._remote_pending is None or len(self._search_workers) >= 2:
            return
        generation, query, source_filter = self._remote_pending
        self._remote_pending = None
        if not self._valid_search_context(generation, query, source_filter):
            return
        worker = SearchWorker(query, self, generation=generation, source_filter=source_filter,
                              terms=self._remote_terms(query))
        worker.context_results.connect(self._on_remote_results)
        worker.context_failed.connect(self._on_remote_failed)
        worker.finished.connect(lambda w=worker: self._retire_worker(w))
        self._search_workers.add(worker)
        worker.start()
        self._set_status(tr("search.remote.loading"))

    def _valid_search_context(self, generation: int, term: str, source_filter: str) -> bool:
        return (generation == self._search_generation and term == self.search_box.text().strip()
                and source_filter == self.source_filter and self._remote_allowed(term))

    def _retire_worker(self, worker: SearchWorker) -> None:
        self._search_workers.discard(worker)
        worker.deleteLater()
        self._launch_remote_pending()

    def _on_remote_results(self, generation: int, term: str, source_filter: str, items: list[CatalogItem]) -> None:
        if not self._valid_search_context(generation, term, source_filter):
            return
        if items:
            self._remote_cache[(normalize(term), source_filter)] = (time.monotonic(), items)
        if len(self._remote_cache) > 20:
            self._remote_cache.pop(next(iter(self._remote_cache)), None)
        self._remote_items = {item.key: item for item in items if self.config.source_enabled(item.source_id)}
        self._remote_state = "ready"
        self._set_status("")
        self._run_search()

    def _on_remote_failed(self, generation: int, term: str, source_filter: str, _message: str) -> None:
        if not self._valid_search_context(generation, term, source_filter):
            return
        self._remote_items.clear()
        self._remote_state = "failed"
        self._set_status(tr("search.remote.offline"), 4000)
        self._run_search()

    # -- discovery --------------------------------------------------------
    def _render_plan(self, plan) -> None:
        if self._closing or self.search_box.text().strip():
            return
        self.discover.set_plan(plan, has_games=self.discovery_controller.enabled and bool(self.discovery_controller.games),
                               source_filter=self.source_filter)
        if self._current is not None and not self.discover.detail.isHidden():
            entry = self.discovery_controller.entry_for(self._current.key)
            if entry is not None:
                self._on_selection(entry.item)

    def _on_discovery_state(self, state: str) -> None:
        self.discover.set_busy(state)
        self._set_status(tr(f"discovery.{state}") if state in {"scanning", "planning"} else "")

    def _scan_steam(self) -> None:
        self.settings.discovery_check.blockSignals(True)
        self.settings.discovery_check.setChecked(True)
        self.settings.discovery_check.blockSignals(False)
        self.discovery_controller.scan()
        self._render_plan(self.discovery_controller.plan)

    def _clear_discovery(self) -> None:
        self.discovery_controller.clear()
        for checkbox in (self.settings.discovery_check, self.settings.scan_start_check):
            checkbox.blockSignals(True)
            checkbox.setChecked(False)
            checkbox.blockSignals(False)
        self.settings.steam_paths_edit.clear()

    def _manage_scanned_games(self) -> None:
        controller = self.discovery_controller
        dialog = ScannedGamesDialog(controller.games, controller.excluded, controller.plan.unmatched,
                                    controller.report, self)
        dialog.exclusion_changed.connect(controller.set_excluded)
        dialog.search_requested.connect(lambda name: (dialog.accept(), self.search_box.setText(name), self.search_box.setFocus()))
        dialog.exec()

    def _download_selected(self) -> None:
        for item in self.discovery_controller.selected_items(source_filter=self.source_filter):
            self._enqueue_download(item, switch_page=False)

    # -- detail -----------------------------------------------------------
    def _on_selection(self, item: CatalogItem) -> None:
        self._current = item
        source = self.sources.get(item.source_id)
        installed = self.library.installed(item)
        source_name = tr(SOURCE_LABEL_KEYS.get(item.source_id, item.source_id))
        direct = source.supports_direct_download if source else item.supports_direct_download
        remote = item.key in self._remote_items
        self.discover.show_detail(item, installed, source_name, direct, remote=remote)
        entry = self.discovery_controller.entry_for(item.key) if not self.search_box.text().strip() else None
        if entry is not None:
            self.discover.detail.show_match(entry)

        if (
            not item.detail_loaded
            and source is not None
            and source.requires_detail
            and self.detail_worker is not None
            and item.key not in self._detail_pending
        ):
            self._detail_pending.add(item.key)
            self._set_status(tr("detail.loading"))
            self.detail_worker.submit(item)

    def _on_detail_ready(self, item: CatalogItem) -> None:
        self._detail_pending.discard(item.key)
        for index, existing in enumerate(self.items):
            if existing.key == item.key:
                self.items[index] = item
                break
        if item.key in self._remote_items:
            self._remote_items[item.key] = item
        self.search.rebuild(self.items)
        self.discovery_controller.replace_item(item)
        self.discover.replace_item(item)
        if self._current is not None and self._current.key == item.key:
            self._on_selection(item)
        self._set_status("")

    def _on_detail_failed(self, key: str, message: str) -> None:
        self._detail_pending.discard(tuple(key.split(":", 1)))  # type: ignore[arg-type]
        self._set_status("")
        logging.getLogger("trainerhub.detail").warning("detail failed for %s: %s", key, message)

    def _on_inspector_closed(self) -> None:
        self._current = None

    def _close_inspector(self) -> None:
        self._current = None
        self.discover.hide_detail()

    # -- sync -------------------------------------------------------------
    def start_sync(self) -> None:
        if self.sync_worker is not None and self.sync_worker.isRunning():
            self.toast.show_message(tr("status.syncing", source="…", page=1))
            return
        self.sync_worker = SyncWorker(self.library.db, self.sources)
        self.sync_worker.progress.connect(self._on_sync_progress)
        self.sync_worker.source_done.connect(self._on_source_done)
        self.sync_worker.source_failed.connect(self._on_source_failed)
        self.sync_worker.finished_all.connect(self._on_sync_done)
        self.sync_button.setEnabled(False)
        self._set_status(tr("status.syncing", source="…", page=1))
        self.sync_worker.start()

    def _on_sync_progress(self, source_id: str, page: int, count: int) -> None:
        self._set_status(
            tr("status.syncing", source=tr(SOURCE_LABEL_KEYS.get(source_id, source_id)), page=page)
        )

    def _on_source_done(self, source_id: str, count: int) -> None:
        self._set_status(tr("status.synced", count=count))

    def _on_source_failed(self, source_id: str, message: str) -> None:
        self._set_status(tr("status.offline"))
        self.toast.show_message(tr("error.network"), 3200)

    def _on_sync_done(self, total: int, failures: int) -> None:
        self.sync_button.setEnabled(True)
        self._load_items()
        self._set_status(tr("toast.synced", count=total), 4000)
        if failures:
            self.toast.show_message(tr("error.network"), 3200)
        else:
            self.toast.show_message(tr("toast.synced", count=total))

    # -- downloads --------------------------------------------------------
    def _enqueue_download(self, item: CatalogItem, *, switch_page: bool = True) -> None:
        if self._closing or not self.config.source_enabled(item.source_id):
            return
        entry = self.discovery_controller.entry_for(item.key)
        source = self.sources.get(item.source_id)
        direct = source.supports_direct_download if source is not None else item.supports_direct_download
        if (entry is not None and entry.action == "external") or not direct:
            self._open_page(item)
            return
        if self.download_worker is None:
            return
        job_id = f"{item.source_id}:{item.remote_id}"
        if job_id in self._active_jobs:
            return
        if entry is not None and entry.state in {"installed", "done"}:
            return
        if self.library.is_same_version_installed(item):
            record = self.library.installed(item)
            if record:
                open_in_file_manager(Path(record.path))
            return

        # A live result becomes a real catalogue row the moment it is used.
        if item.key in self._remote_items:
            self.library.db.upsert_items([item])
            self._remote_items.pop(item.key, None)
            if not any(existing.key == item.key for existing in self.items):
                self.items.append(item)
            self.search.rebuild(self.items)
            self.discover.set_remote_keys(set(self._remote_items.keys()))

        self._active_jobs.add(job_id)
        self.discover.set_job_state(item.key, "queued")
        self._external_jobs.discard(job_id)
        self.discovery_controller.update_job(item.key, "queued")
        self.downloads.add_job(job_id, item, tr(SOURCE_LABEL_KEYS.get(item.source_id, item.source_id)))
        self.download_worker.enqueue(item)
        self.toast.show_message(tr("toast.download.queued"), 1800)
        if switch_page:
            self._switch_page("library")

    def _cancel_download(self, job_id: str) -> None:
        if self.download_worker is not None:
            self.download_worker.cancel(job_id)

    def _on_job_state(self, job_id: str, state: str, message: str) -> None:
        self.downloads.update_state(job_id, state, message)
        key = tuple(job_id.split(":", 1))
        if len(key) == 2:
            self.discover.set_job_state(key, state)
        if state in ACTIVE_STATES:
            self._active_jobs.add(job_id)
        else:
            self._active_jobs.discard(job_id)
        if len(key) == 2:
            if message == "external" or job_id in self._external_jobs:
                self.discovery_controller.external(key)
            else:
                self.discovery_controller.update_job(key, state)

    def _on_job_progress(self, job_id: str, received: int, total: int) -> None:
        key = tuple(job_id.split(":", 1))
        if len(key) == 2:
            self.discover.set_job_progress(key, received, total)

    def _on_job_done(self, record: InstalledItem) -> None:
        self._active_jobs.discard(f"{record.source_id}:{record.remote_id}")
        self.discovery_controller.update_job(record.key, "done")
        self.toast.show_message(tr("toast.download.done", name=record.game_name))
        self._refresh_library()
        if self._current is not None and self._current.key == record.key:
            self.discover.update_installed(record)
        self.discover.set_installed_keys(self._installed_keys())

    def _on_job_failed(self, job_id: str, reason: str) -> None:
        self._active_jobs.discard(job_id)
        self.discovery_controller.update_job(tuple(job_id.split(":", 1)), "failed")
        self.toast.show_message(tr("toast.download.failed", reason=(reason.splitlines() or [tr("state.failed")])[0][:90]), 3600)

    def _on_job_external(self, job_id: str, url: str) -> None:
        self._active_jobs.discard(job_id)
        self._external_jobs.add(job_id)
        self.discovery_controller.external(tuple(job_id.split(":", 1)))
        if url:
            QDesktopServices.openUrl(QUrl(url))
        self.toast.show_message(tr("error.external"), 3000)

    # -- library ----------------------------------------------------------
    def _refresh_library(self) -> None:
        records = self.library.db.installed_all()
        query = self.search_box.text().strip().casefold() if self.stack.currentWidget() is self.library_page else ""
        self.library_page.set_records([record for record in records if query in record.game_name.casefold()])
        self.discover.set_installed_keys(self._installed_keys())

    def _import_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("library.import.title"), str(self.config.library_dir))
        if not folder:
            return
        records = self.library.import_tree(Path(folder))
        self._refresh_library()
        self.toast.show_message(tr("toast.import.done", count=len(records)))

    def _check_updates(self) -> None:
        service = UpdateService(self.library.db, self.sources)
        candidates = service.candidates()
        if not candidates:
            self.toast.show_message(tr("dialog.updates.none"))
            self._refresh_library()
            return
        box = QMessageBox(self)
        box.setWindowTitle(tr("dialog.updates.title", count=len(candidates)))
        box.setText("\n".join(f"• {c.item.game_name}: {c.local_version} → {c.remote_version}" for c in candidates[:12]))
        box.setInformativeText(tr("dialog.updates.body"))
        box.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        box.exec()
        self._refresh_library()

    def _run_trainer(self, record: InstalledItem) -> None:
        from PySide6.QtCore import QProcess

        folder = Path(record.path)
        executables = sorted(folder.glob("*.exe"))
        if not executables:
            QMessageBox.information(self, tr("dialog.run.title"), tr("dialog.run.missing"))
            return
        target = executables[0]
        started, _pid = QProcess.startDetached(str(target), [], str(folder))
        if not started:
            QMessageBox.warning(self, tr("dialog.run.title"), tr("dialog.run.failed"))

    def _run_catalog_item(self, item: CatalogItem) -> None:
        record = self.library.installed(item)
        if record is not None:
            self._run_trainer(record)

    def _delete_catalog_item(self, item: CatalogItem) -> None:
        record = self.library.installed(item)
        if record is not None:
            self._delete_record(record)

    def _delete_record(self, record: InstalledItem) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(tr("dialog.delete.title"))
        box.setText(tr("library.delete.confirm", name=record.game_name))
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        try:
            self.library.delete(record)
        except OSError as exc:
            QMessageBox.warning(self, tr("dialog.delete.title"), tr("dialog.delete.failed", reason=str(exc)))
            return
        self.discover.set_job_state(record.key, "ready")
        self.discovery_controller.forget_job(record.key)
        self._refresh_library()
        if self._current is not None and self._current.key == record.key:
            self._on_selection(self._current)

    # -- misc -------------------------------------------------------------
    def _switch_page(self, page: str) -> None:
        mapping = {"discover": 0, "library": 1, "settings": 2}
        self._search_timer.stop()
        self._remote_timer.stop()
        self._invalidate_search()
        self.search_box.blockSignals(True)
        self.search_box.clear()
        self.search_box.blockSignals(False)
        self._was_searching = False
        self.stack.setCurrentIndex(mapping.get(page, 0))
        self.rail.set_active_page(page if page != "settings" else "")
        self.brand.setText(tr("nav.library") if page == "library" else tr("nav.discover"))
        self.search_box.setVisible(page != "settings")
        self.search_box.setPlaceholderText(tr("library.search.placeholder") if page == "library" else tr("search.placeholder"))
        if page == "library":
            self._refresh_library()
        elif page == "discover":
            self._run_search()

    def _on_library_changed(self, folder: str) -> None:
        self.library.root = Path(folder)
        self._refresh_library()

    def _on_language_changed(self, language: str) -> None:
        self.cleanup()
        self.language_change_requested.emit(language)

    def _on_sources_changed(self) -> None:
        self._invalidate_search()
        self._remote_cache.clear()
        self.discovery_controller.cancel()
        if self.on_rebuild is not None:
            self.cleanup()
            self.on_rebuild()
        else:
            self._run_search()
            self.discovery_controller.rebuild_plan()

    def _open_page(self, item: CatalogItem) -> None:
        if item.page_url:
            QDesktopServices.openUrl(QUrl(item.page_url))

    def _open_folder(self, record: InstalledItem) -> None:
        open_in_file_manager(Path(record.path))

    def shutdown_discovery(self) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._search_timer.stop()
        self._remote_timer.stop()
        self._invalidate_search()
        self._remote_cache.clear()
        self.discovery_controller.cleanup()
        for worker in (self.sync_worker, self.detail_worker, self.download_worker):
            if worker is None:
                continue
            if hasattr(worker, "stop"):
                worker.stop()
            if worker.isRunning():
                worker.wait()
        for worker in list(self._search_workers):
            worker.stop()
            worker.wait()

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            self.config.set("ui.window_geometry", bytes(self.saveGeometry()).hex(), save=False)
            self.config.save()
        except Exception:  # noqa: BLE001
            pass
        self.cleanup()
        super().closeEvent(event)


def window_title() -> str:
    return f"{APP_NAME} {VERSION} ({sys.platform})"

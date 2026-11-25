"""Main window: rail + top bar + stacked pages + status bar."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon
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
from ..core.textutil import human_size
from ..core.updater import UpdateService
from ..i18n import tr
from ..workers.detail_worker import DetailWorker
from ..workers.download_worker import DownloadWorker
from ..workers.sync_worker import SyncWorker
from . import theme as theme_tokens
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
        self.source_filter = config.get("ui.last_source", "all") or "all"
        self._current: CatalogItem | None = None
        self._detail_pending: set[tuple[str, str]] = set()

        self.sync_worker: SyncWorker | None = workers.get("sync")
        self.detail_worker: DetailWorker | None = workers.get("detail")
        self.download_worker: DownloadWorker | None = workers.get("download")

        self.setWindowTitle(f"{APP_NAME} · {VERSION}")
        self.setWindowIcon(QIcon(str(resource_path("resources", "app_icon.svg"))))
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)

        self._build_ui()
        self._wire()
        self._apply_theme(config.theme)
        self._load_items(initial=True)

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
        top_bar.setFixedHeight(60)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(20, 10, 20, 10)
        top_layout.setSpacing(10)

        self.search_box = QLineEdit()
        self.search_box.setObjectName("SearchBox")
        self.search_box.setPlaceholderText(tr("search.placeholder"))
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setMinimumWidth(280)
        self.search_box.setMaximumWidth(560)

        self.sync_button = QPushButton(tr("action.sync"))
        self.sync_button.setObjectName("GhostButton")
        self.sync_button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.theme_button = QPushButton(tr("settings.theme.light"))
        self.theme_button.setObjectName("IconButton")
        self.theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_button.setToolTip(tr("settings.theme"))

        top_layout.addWidget(self.search_box)
        top_layout.addStretch(1)
        top_layout.addWidget(self.sync_button)
        top_layout.addWidget(self.theme_button)
        right_layout.addWidget(top_bar)

        # -- pages -------------------------------------------------------
        self.stack = QStackedWidget()
        self.discover = DiscoverPage()
        self.downloads = DownloadsPage()
        self.library_page = LibraryPage()
        self.settings = SettingsPage(self.config)
        self.discover.set_source_names(self._source_names())
        self.stack.addWidget(self.discover)
        self.stack.addWidget(self.downloads)
        self.stack.addWidget(self.library_page)
        self.stack.addWidget(self.settings)
        right_layout.addWidget(self.stack, 1)

        # -- status bar --------------------------------------------------
        status = QWidget()
        status.setObjectName("StatusBar")
        status.setFixedHeight(26)
        status_layout = QHBoxLayout(status)
        status_layout.setContentsMargins(20, 0, 20, 0)
        status_layout.setSpacing(12)
        self.status_left = QLabel(tr("status.ready"))
        self.status_right = QLabel(str(self.config.library_dir))
        self.status_right.setMaximumWidth(520)
        status_layout.addWidget(self.status_left)
        status_layout.addStretch(1)
        status_layout.addWidget(self.status_right)
        right_layout.addWidget(status)

        outer.addWidget(right, 1)
        self.toast = Toast(root)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(170)
        self._search_timer.timeout.connect(self._run_search)

    def _wire(self) -> None:
        self.rail.navigate.connect(self._switch_page)
        self.rail.source_changed.connect(self._on_source_filter)
        self.search_box.textChanged.connect(lambda _text: self._search_timer.start())
        self.sync_button.clicked.connect(self.start_sync)
        self.theme_button.clicked.connect(self._toggle_theme)

        self.discover.selection_changed.connect(self._on_selection)
        self.discover.download_requested.connect(self._enqueue_download)
        self.discover.open_page_requested.connect(self._open_page)
        self.discover.open_folder_requested.connect(self._open_folder)
        self.discover.sync_requested.connect(self.start_sync)

        self.downloads.cancel_requested.connect(self._cancel_download)

        self.library_page.import_requested.connect(self._import_folder)
        self.library_page.update_check_requested.connect(self._check_updates)
        self.library_page.open_requested.connect(lambda record: open_in_file_manager(Path(record.path)))
        self.library_page.run_requested.connect(self._run_trainer)
        self.library_page.delete_requested.connect(self._delete_record)

        self.settings.theme_changed.connect(self._apply_theme)
        self.settings.language_changed.connect(self.language_change_requested.emit)
        self.settings.library_changed.connect(self._on_library_changed)
        self.settings.sources_changed.connect(self._on_sources_changed)

        if self.detail_worker is not None:
            self.detail_worker.detail_ready.connect(self._on_detail_ready)
            self.detail_worker.detail_failed.connect(self._on_detail_failed)
        if self.download_worker is not None:
            self.download_worker.job_state.connect(self._on_job_state)
            self.download_worker.job_progress.connect(self.downloads.update_progress)
            self.download_worker.job_done.connect(self._on_job_done)
            self.download_worker.job_failed.connect(self._on_job_failed)
            self.download_worker.job_external.connect(self._on_job_external)

        geometry = self.config.get("ui.window_geometry", "")
        if geometry:
            try:
                self.restoreGeometry(bytes.fromhex(geometry))
            except ValueError:
                pass

    # -- items & search ---------------------------------------------------
    def _load_items(self, *, initial: bool = False) -> None:
        self.items = self._db_items()
        self.search.rebuild(self.items)
        self._refresh_counts()
        self._run_search()
        self._refresh_library()
        if initial and not self.items:
            self.discover.set_empty_mode("empty")

    def _db_items(self) -> list[CatalogItem]:
        return self.library.db.all_items()

    def _refresh_counts(self) -> None:
        counts = self.library.db.count_by_source()
        self.rail.set_counts(counts)
        self.rail.set_footer(str(self.config.library_dir))

    def _on_source_filter(self, source_id: str) -> None:
        self.source_filter = source_id
        self.config.set("ui.last_source", source_id)
        self._switch_page("discover")
        self._run_search()

    def _run_search(self) -> None:
        query = self.search_box.text().strip()
        hits = self.search.query(query, source_id=self.source_filter, limit=2000)
        items = [hit.item for hit in hits]
        if not items:
            if query:
                self.discover.set_empty_mode("noresult", query)
            elif not self.items:
                self.discover.set_empty_mode("empty")
            else:
                self.discover.set_empty_mode("noresult", query)
            return
        self.discover.set_items(items)
        if self._current is None:
            self.discover.select_row(0)

    # -- detail -----------------------------------------------------------
    def _on_selection(self, item: CatalogItem) -> None:
        self._current = item
        source = self.sources.get(item.source_id)
        installed = self.library.installed(item)
        source_name = tr(SOURCE_LABEL_KEYS.get(item.source_id, item.source_id))
        direct = source.supports_direct_download if source else item.supports_direct_download
        self.discover.show_detail(item, installed, source_name, direct)

        if (
            not item.detail_loaded
            and source is not None
            and source.requires_detail
            and self.detail_worker is not None
            and item.key not in self._detail_pending
        ):
            self._detail_pending.add(item.key)
            self.status_left.setText(tr("detail.loading"))
            self.detail_worker.submit(item)

    def _on_detail_ready(self, item: CatalogItem) -> None:
        self._detail_pending.discard(item.key)
        for index, existing in enumerate(self.items):
            if existing.key == item.key:
                self.items[index] = item
                break
        self.search.rebuild(self.items)
        self.discover.replace_item(item)
        if self._current is not None and self._current.key == item.key:
            self._on_selection(item)
        self.status_left.setText(tr("status.ready"))

    def _on_detail_failed(self, key: str, message: str) -> None:
        self._detail_pending.discard(tuple(key.split(":", 1)))  # type: ignore[arg-type]
        self.status_left.setText(tr("status.ready"))
        logging.getLogger("trainerhub.detail").warning("detail failed for %s: %s", key, message)

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
        self.status_left.setText(tr("status.syncing", source="…", page=1))
        self.sync_worker.start()

    def _on_sync_progress(self, source_id: str, page: int, count: int) -> None:
        self.status_left.setText(tr("status.syncing", source=tr(SOURCE_LABEL_KEYS.get(source_id, source_id)), page=page))

    def _on_source_done(self, source_id: str, count: int) -> None:
        self.status_left.setText(tr("status.synced", count=count))

    def _on_source_failed(self, source_id: str, message: str) -> None:
        self.status_left.setText(tr("status.offline"))
        self.toast.show_message(tr("error.network"), 3200)

    def _on_sync_done(self, total: int, failures: int) -> None:
        self.sync_button.setEnabled(True)
        self._load_items()
        self.status_left.setText(tr("toast.synced", count=total))
        if failures:
            self.toast.show_message(tr("error.network"), 3200)
        else:
            self.toast.show_message(tr("toast.synced", count=total))

    # -- downloads --------------------------------------------------------
    def _enqueue_download(self, item: CatalogItem) -> None:
        if self.download_worker is None:
            return
        if self.library.is_same_version_installed(item):
            record = self.library.installed(item)
            if record:
                open_in_file_manager(Path(record.path))
            return
        job_id = f"{item.source_id}:{item.remote_id}"
        self.downloads.add_job(job_id, item, tr(SOURCE_LABEL_KEYS.get(item.source_id, item.source_id)))
        self.download_worker.enqueue(item)
        self.toast.show_message(tr("toast.download.queued"), 1800)
        self._switch_page("downloads")

    def _cancel_download(self, job_id: str) -> None:
        if self.download_worker is not None:
            self.download_worker.cancel(job_id)

    def _on_job_state(self, job_id: str, state: str, message: str) -> None:
        self.downloads.update_state(job_id, state, message)

    def _on_job_done(self, record: InstalledItem) -> None:
        self.toast.show_message(tr("toast.download.done", name=record.game_name))
        self._refresh_library()
        if self._current is not None and self._current.key == record.key:
            self.discover.update_installed(record)

    def _on_job_failed(self, job_id: str, reason: str) -> None:
        self.toast.show_message(tr("toast.download.failed", reason=reason.splitlines()[0][:90]), 3600)

    def _on_job_external(self, job_id: str, url: str) -> None:
        if url:
            QDesktopServices.openUrl(QUrl(url))
        self.toast.show_message(tr("error.external"), 3000)

    # -- library ----------------------------------------------------------
    def _refresh_library(self) -> None:
        records = self.library.db.installed_all()
        service = UpdateService(self.library.db, self.sources)
        updates = {candidate.item.key: candidate.item.version for candidate in service.candidates()}
        self.library_page.set_records(records, updates)
        self.status_right.setText(f"{self.config.library_dir}  ·  {human_size(self.library.total_bytes())}")

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
            QMessageBox.information(self, tr("dialog.run.title"), "No .exe found in this folder.")
            return
        target = executables[0]
        box = QMessageBox(self)
        box.setWindowTitle(tr("dialog.run.title"))
        box.setText(tr("dialog.run.body", name=f"{record.game_name} · {target.name}"))
        box.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        if box.exec() != QMessageBox.StandardButton.Ok:
            return
        started, _pid = QProcess.startDetached(str(target), [], str(folder))
        if not started:
            QMessageBox.warning(self, tr("dialog.run.title"), "Failed to start the trainer.")

    def _delete_record(self, record: InstalledItem) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(tr("dialog.delete.title"))
        box.setText(tr("library.delete.confirm", name=record.game_name))
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        self.library.delete(record)
        self._refresh_library()
        if self._current is not None and self._current.key == record.key:
            self._on_selection(self._current)

    # -- misc -------------------------------------------------------------
    def _switch_page(self, page: str) -> None:
        mapping = {"discover": 0, "downloads": 1, "library": 2, "settings": 3}
        index = mapping.get(page, 0)
        self.stack.setCurrentIndex(index)
        self.rail.set_active_page(page)
        if page == "library":
            self._refresh_library()
        if page == "discover":
            self._run_search()

    def _on_library_changed(self, folder: str) -> None:
        self.library.root = Path(folder)
        self._refresh_counts()
        self._refresh_library()

    def _on_sources_changed(self) -> None:
        if self.on_rebuild is not None:
            self.on_rebuild()

    def _toggle_theme(self) -> None:
        theme = "light" if self.config.theme == "dark" else "dark"
        self.config.set("theme", theme)
        self._apply_theme(theme)

    def _apply_theme(self, theme: str) -> None:
        from PySide6.QtWidgets import QApplication

        self.config.set("theme", theme)
        app = QApplication.instance()
        if app is not None:
            theme_tokens.apply(app, theme)
        self.theme_button.setText(
            tr("settings.theme.light") if theme == "dark" else tr("settings.theme.dark")
        )
        self.discover.set_theme(theme)

    def _open_page(self, item: CatalogItem) -> None:
        if item.page_url:
            QDesktopServices.openUrl(QUrl(item.page_url))

    def _open_folder(self, record: InstalledItem) -> None:
        open_in_file_manager(Path(record.path))

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            self.config.set("ui.window_geometry", bytes(self.saveGeometry()).hex(), save=False)
            self.config.save()
        except Exception:  # noqa: BLE001
            pass
        for worker in (self.sync_worker, self.detail_worker, self.download_worker):
            if worker is None:
                continue
            if hasattr(worker, "stop"):
                worker.stop()
            if worker.isRunning():
                worker.wait(3000)
        super().closeEvent(event)


def window_title() -> str:
    return f"{APP_NAME} {VERSION} ({sys.platform})"

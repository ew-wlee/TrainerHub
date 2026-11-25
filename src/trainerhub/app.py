"""Application bootstrap and window lifecycle."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from . import APP_ID, APP_NAME, VERSION
from .core.config import Config
from .core.db import Database
from .core.downloader import Downloader
from .core.http import HttpClient
from .core.library import LibraryService
from .core.paths import cache_dir, database_file, log_dir, resource_path
from .core.search import SearchEngine
from .core.sources.base import build_sources
from .i18n import set_language
from .ui import theme as theme_tokens
from .ui.dialogs.welcome_wizard import WelcomeWizard
from .ui.main_window import MainWindow
from .workers.detail_worker import DetailWorker
from .workers.download_worker import DownloadWorker


def configure_logging() -> None:
    handler = RotatingFileHandler(
        log_dir() / "trainerhub.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)


class TrainerHubApp:
    def __init__(self, argv: list[str]) -> None:
        configure_logging()
        self.app = QApplication(argv)
        self.app.setApplicationName(APP_NAME)
        self.app.setApplicationDisplayName(APP_NAME)
        self.app.setApplicationVersion(VERSION)
        self.app.setOrganizationName(APP_ID)
        self.app.setWindowIcon(QIcon(str(resource_path("resources", "app_mark.svg"))))

        self.config = Config.load()
        set_language(self.config.language)
        theme_tokens.apply(self.app, self.config.theme)

        self.db = Database(database_file())
        self.http = HttpClient(
            timeout=float(self.config.get("download.timeout", 20)),
            max_retries=int(self.config.get("download.max_retries", 2)),
            min_interval=0.45,
        )
        self.sources = build_sources(self.config, self.http)
        self.library = LibraryService(self.config.library_dir, self.db)
        self.downloader = Downloader(self.http, cache_dir() / "downloads")
        self.search = SearchEngine(self.db.all_items())

        self.detail_worker: DetailWorker | None = None
        self.download_worker: DownloadWorker | None = None
        self.window: MainWindow | None = None
        self.app.aboutToQuit.connect(self._shutdown_workers)

    # -- lifecycle --------------------------------------------------------
    def run(self) -> int:
        if os.environ.get("TRAINERHUB_SMOKE_TEST"):
            # Packaging smoke test: no first-run wizard, no network sync.
            self.config.set("first_run", False, save=False)
            self.config.set("ui.sync_on_start", False, save=False)
        if self.config.get("first_run", True):
            wizard = WelcomeWizard(self.config)
            if wizard.exec() != WelcomeWizard.DialogCode.Accepted:
                return 0
            self.library.root = self.config.library_dir
            self._refresh_sources()

        self._show_window()
        if self.config.get("ui.sync_on_start", True) and not self.db.item_count():
            QTimer.singleShot(600, self.window.start_sync)  # type: ignore[union-attr]
        if os.environ.get("TRAINERHUB_SMOKE_TEST"):
            # Used by CI / packaging checks: boot the UI, then exit cleanly.
            QTimer.singleShot(1500, self.app.quit)
        return self.app.exec()

    def _refresh_sources(self) -> None:
        self.sources = build_sources(self.config, self.http)

    def _show_window(self) -> None:
        self.detail_worker = DetailWorker(self.db, self.sources)
        self.detail_worker.start()
        self.download_worker = DownloadWorker(
            self.db,
            self.sources,
            self.downloader,
            self.library,
            concurrency=int(self.config.get("download.concurrency", 2)),
        )
        self.download_worker.start()

        workers = {"detail": self.detail_worker, "download": self.download_worker}
        self.window = MainWindow(
            config=self.config,
            search=self.search,
            library=self.library,
            sources=self.sources,
            workers=workers,
            items=self.db.all_items(),
            on_rebuild=self._rebuild,
        )
        self.window.language_change_requested.connect(self._on_language)
        self.window.show()

    def _shutdown_workers(self) -> None:
        if self.window is not None:
            self.window.shutdown_discovery()
        for worker in (self.detail_worker, self.download_worker):
            if worker is not None:
                worker.stop()
        for worker in (self.detail_worker, self.download_worker):
            if worker is not None and worker.isRunning():
                worker.wait()

    def _rebuild(self) -> None:
        """Recreate workers and window after a structural setting change."""
        geometry = self.window.saveGeometry() if self.window else None
        self._shutdown_workers()
        self._refresh_sources()
        self.library.root = self.config.library_dir
        if self.window is not None:
            self.window.hide()
            self.window.deleteLater()
        self._show_window()
        if geometry is not None and self.window is not None:
            self.window.restoreGeometry(geometry)
        if self.window is not None:
            self.window.show()

    def _on_language(self, language: str) -> None:
        set_language(language)
        self.config.set("language", language)
        self._rebuild()

    def _fatal(self, message: str) -> None:  # pragma: no cover - last resort
        QMessageBox.critical(None, APP_NAME, message)


def install_exception_hook() -> None:
    def handler(exc_type, exc_value, exc_tb):  # noqa: ANN001
        logging.getLogger("trainerhub").exception(
            "unhandled exception", exc_info=(exc_type, exc_value, exc_tb)
        )
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = handler


def library_path() -> Path:  # pragma: no cover - convenience for scripts
    return Config.load().library_dir

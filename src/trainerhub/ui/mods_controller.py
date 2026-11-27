"""One operation at a time, with generation guards and deterministic shutdown."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from ..core.config import Config
from ..core.mods import ModScanReport, ModService, ScanCancelled
from ..core.steam_scan import scan_steam
from ..workers.mod_worker import ModWorker


class ModsController(QObject):
    report_changed = Signal(object)
    busy_changed = Signal(bool, str)
    failed = Signal(str, str)

    def __init__(self, config: Config, parent=None, *, service: ModService | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.service = service or ModService(Path(config.path).parent / "Mods")
        self.report = ModScanReport()
        self.busy = False
        self.initialized = False
        self.kind = ""
        self._generation = 0
        self._worker: ModWorker | None = None
        self._closing = False

    def initialize(self) -> None:
        if not self.initialized:
            self._start("load", lambda _: self.service.recover())

    def _scan(self, cancelled):
        paths = self.config.get("discovery.steam_paths", []) or None
        steam = scan_steam(paths, cancelled=cancelled)
        if steam.cancelled or cancelled():
            raise ScanCancelled()
        return self.service.scan(steam.games, library_status=steam.library_status, cancelled=cancelled)

    def scan(self) -> None:
        self._start("scan", self._scan)

    def toggle(self, identifiers: list[str], enabled: bool) -> None:
        self._start("enable" if enabled else "disable", lambda _: self.service.toggle(identifiers, enabled))

    def confirm(self, identifier: str) -> None:
        self._start("confirm", lambda _: self.service.confirm(identifier))

    def add_rule(self, game, root: str, mode: str) -> None:
        def task(cancelled):
            self.service.add_rule(game, root, mode)
            return self._scan(cancelled)

        self._start("scan", task)

    def cancel(self) -> None:
        if self._worker is not None and self.kind == "scan":
            self._worker.stop()

    def _start(self, kind: str, task) -> None:
        if self.busy or self._closing:
            return
        self._generation += 1
        self.busy, self.kind = True, kind
        worker = ModWorker(self._generation, task, self)
        self._worker = worker
        worker.result.connect(self._on_result)
        worker.finished.connect(self._retire)
        self.busy_changed.emit(True, kind)
        worker.start()

    def _on_result(self, generation: int, report, code: str, detail: str) -> None:
        if self._closing or generation != self._generation:
            return
        if report is not None:
            if self.kind not in {"load", "scan"}:
                report.issues = self.report.issues
                report.library_status = self.report.library_status
            self.report = report
            self.initialized = True
            self.report_changed.emit(report)
        elif code != "cancelled":
            self.failed.emit(code, detail)

    def _retire(self) -> None:
        worker = self.sender()
        if worker is self._worker:
            self._worker = None
            self.busy = False
            if not self._closing:
                self.busy_changed.emit(False, self.kind)
        worker.deleteLater()

    def cleanup(self) -> None:
        self._closing = True
        self._generation += 1
        if self._worker is not None:
            if self.kind in {"load", "scan"}:
                self._worker.stop()
            # Moves are never forcibly interrupted; let the transaction commit or roll back.
            self._worker.wait()

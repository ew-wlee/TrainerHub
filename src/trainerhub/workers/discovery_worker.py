"""Read Steam manifests and build recommendations away from the GUI thread."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ..core.db import Database
from ..core.models import RecommendationPlan
from ..core.recommendation import build_plan
from ..core.steam_scan import scan_steam


class DiscoveryWorker(QThread):
    ready = Signal(int, object, object, object, object)
    failed = Signal(int, str)

    def __init__(
        self,
        db: Database,
        *,
        generation: int,
        scan: bool = False,
        paths: list[str] | None = None,
        sources: set[str] | None = None,
        previous: RecommendationPlan | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.generation = generation
        self.scan = scan
        self.paths = paths
        self.sources = sources
        self.previous = previous

    def stop(self) -> None:
        self.requestInterruption()

    def run(self) -> None:
        try:
            report = scan_steam(self.paths or None, cancelled=self.isInterruptionRequested) if self.scan else None
            if self.isInterruptionRequested() or (report is not None and report.cancelled):
                return
            games = self.db.steam_games()
            if report is not None:
                retained = [game for game in games if report.library_status.get(game.library_path) != "ok"]
                scanned = [game for game in report.games if report.library_status.get(game.library_path) == "ok"]
                games = list({game.appid: game for game in retained + scanned}.values())
            excluded = self.db.steam_excluded()
            items = self.db.all_items()
            if self.sources is not None:
                items = [item for item in items if item.source_id in self.sources]
            installed = {record.key for record in self.db.installed_all()}
            if self.isInterruptionRequested():
                return
            plan = build_plan(
                games, items, installed, excluded,
                generation=self.generation, previous=self.previous,
            )
            if not self.isInterruptionRequested():
                self.ready.emit(self.generation, report, plan, games, excluded)
        except Exception as exc:  # noqa: BLE001
            if not self.isInterruptionRequested():
                self.failed.emit(self.generation, str(exc))

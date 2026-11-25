"""Own discovery generations, selection and download state independently of search."""

from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import QObject, Signal

from ..core.config import Config
from ..core.db import Database
from ..core.models import RecommendationPlan, ScanReport, SteamGame
from ..workers.discovery_worker import DiscoveryWorker

ACTIVE_STATES = {"queued", "resolving", "downloading", "extracting", "installing"}
SELECTABLE_STATES = {"ready", "failed", "cancelled"}


class DiscoveryController(QObject):
    plan_changed = Signal(object)
    state_changed = Signal(str)
    snapshot_changed = Signal(object, object)
    failed = Signal(str)

    def __init__(self, config: Config, db: Database, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.db = db
        self.generation = 0
        self.plan = RecommendationPlan()
        self.games: list[SteamGame] = []
        self.excluded: set[str] = set()
        self.report = ScanReport()
        self.state = "idle"
        self._workers: set[DiscoveryWorker] = set()
        self._pending: tuple[int, bool] | None = None
        self._closed = False
        self._job_states: dict[tuple[str, str], str] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("discovery.enabled", False))

    @property
    def busy(self) -> bool:
        return self.state in {"scanning", "planning"}

    def initialize(self) -> None:
        if self.enabled:
            self._request(scan=bool(self.config.get("discovery.scan_on_start", False)))
        else:
            self.plan_changed.emit(self.plan)

    def _invalidate(self) -> None:
        self.generation += 1
        self._pending = None
        for worker in self._workers:
            worker.stop()

    def _set_state(self, state: str) -> None:
        self.state = state
        self.state_changed.emit(state)

    def scan(self) -> None:
        if self._closed:
            return
        self.config.set("discovery.enabled", True)
        self._request(scan=True)

    def rebuild_plan(self) -> None:
        if self.enabled and not self._closed:
            self._request(scan=False)

    def _request(self, *, scan: bool) -> None:
        self._invalidate()
        self._pending = (self.generation, scan)
        self._set_state("scanning" if scan else "planning")
        self._start_pending()

    def _start_pending(self) -> None:
        if self._closed or self._workers or self._pending is None:
            return
        generation, scan = self._pending
        self._pending = None
        worker = DiscoveryWorker(
            self.db, generation=generation, scan=scan,
            paths=list(self.config.get("discovery.steam_paths", []) or []),
            sources=set(self.config.enabled_sources), previous=deepcopy(self.plan), parent=self,
        )
        worker.ready.connect(self._accept)
        worker.failed.connect(self._fail)
        worker.finished.connect(lambda w=worker: self._retire(w))
        self._workers.add(worker)
        worker.start()

    def _retire(self, worker: DiscoveryWorker) -> None:
        self._workers.discard(worker)
        worker.deleteLater()
        self._start_pending()

    def _accept(self, generation, report, plan, games, excluded) -> None:
        if self._closed or generation != self.generation or not self.enabled:
            return
        if report is not None:
            if report.cancelled:
                self._set_state("idle")
                return
            self.db.save_steam_scan(report)
            self.report = report
        self.games = games
        self.excluded = set(excluded)
        choices = {(entry.game.appid, entry.item.key): entry.selected for entry in self.plan.entries}
        for entry in plan.entries:
            state = self._job_states.get(entry.item.key)
            if state:
                entry.state = "installed" if state == "done" else state
            if entry.action != "download" or entry.state not in SELECTABLE_STATES:
                entry.selected = False
            elif (entry.game.appid, entry.item.key) in choices:
                entry.selected = choices[(entry.game.appid, entry.item.key)]
        self.plan = plan
        self._set_state("idle")
        self.snapshot_changed.emit(self.games, self.excluded)
        self.plan_changed.emit(self.plan)

    def _fail(self, generation: int, message: str) -> None:
        if generation != self.generation or self._closed:
            return
        self._set_state("idle")
        self.failed.emit(message)

    def cancel(self) -> None:
        self._invalidate()
        self._set_state("idle")
        self.plan_changed.emit(self.plan)

    def set_enabled(self, enabled: bool) -> None:
        self.config.set("discovery.enabled", enabled)
        self.cancel()
        if enabled:
            self.rebuild_plan()
        else:
            self.plan = RecommendationPlan(generation=self.generation)
            self.plan_changed.emit(self.plan)

    def clear(self) -> None:
        self.cancel()
        self.config.set("discovery.enabled", False, save=False)
        self.config.set("discovery.scan_on_start", False, save=False)
        self.config.set("discovery.steam_paths", [], save=False)
        self.config.save()
        self.db.clear_discovery()
        self.plan = RecommendationPlan(generation=self.generation)
        self.games = []
        self.excluded = set()
        self.report = ScanReport()
        self.snapshot_changed.emit(self.games, self.excluded)
        self.plan_changed.emit(self.plan)

    def set_excluded(self, appid: str, excluded: bool) -> None:
        self.cancel()
        self.db.set_steam_excluded(str(appid), excluded)
        self.rebuild_plan()

    def entry_for(self, key: tuple[str, str]):
        return next((entry for entry in self.plan.entries if entry.item.key == key), None)

    def set_selected(self, key: tuple[str, str], selected: bool) -> None:
        for entry in self.plan.entries:
            if entry.item.key == key and entry.action == "download" and entry.state in SELECTABLE_STATES:
                entry.selected = bool(selected)
        self.plan_changed.emit(self.plan)

    def select_all(self, selected: bool, *, source_filter: str = "all") -> None:
        for entry in self.plan.entries:
            if source_filter != "all" and entry.item.source_id != source_filter:
                continue
            entry.selected = bool(selected) if entry.action == "download" and entry.state in SELECTABLE_STATES else False
        self.plan_changed.emit(self.plan)

    def selected_items(self, *, source_filter: str = "all"):
        seen = set()
        items = []
        for entry in self.plan.entries:
            if source_filter != "all" and entry.item.source_id != source_filter:
                continue
            if (entry.selected and entry.action == "download"
                    and entry.state in SELECTABLE_STATES and entry.item.key not in seen):
                seen.add(entry.item.key)
                items.append(entry.item)
        return items

    def replace_item(self, item) -> None:
        changed = False
        for entry in self.plan.entries:
            if entry.item.key == item.key:
                entry.item = item
                changed = True
        if changed:
            self.plan_changed.emit(self.plan)

    def forget_job(self, key: tuple[str, str]) -> None:
        self._job_states.pop(key, None)
        for entry in self.plan.entries:
            if entry.item.key == key and entry.state in {"installed", "done"}:
                entry.state = "ready"
                entry.selected = False
        self.plan_changed.emit(self.plan)
        self.rebuild_plan()

    def update_job(self, key: tuple[str, str], state: str) -> None:
        self._job_states[key] = state
        for entry in self.plan.entries:
            if entry.item.key == key:
                entry.state = "installed" if state == "done" else state
                if state in ACTIVE_STATES or state == "done":
                    entry.selected = False
        self.plan_changed.emit(self.plan)

    def external(self, key: tuple[str, str]) -> None:
        self._job_states.pop(key, None)
        for entry in self.plan.entries:
            if entry.item.key == key:
                entry.action = "external"
                entry.state = "ready"
                entry.selected = False
        self.plan_changed.emit(self.plan)

    def cleanup(self) -> None:
        self._closed = True
        self._invalidate()
        for worker in list(self._workers):
            worker.wait()
        self._set_state("idle")

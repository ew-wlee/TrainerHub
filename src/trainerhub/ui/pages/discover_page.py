"""Discover page: the list, plus an inspector that appears only on selection."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QPushButton,
    QSplitter,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from ...core.models import CatalogItem, InstalledItem, RecommendationPlan
from ...i18n import tr
from ..widgets.common import EmptyState
from ..widgets.detail_panel import DetailPanel
from ..widgets.trainer_list import TrainerDelegate, TrainerListModel, TrainerListView


class DiscoverPage(QWidget):
    download_requested = Signal(object)
    open_page_requested = Signal(object)
    open_folder_requested = Signal(object)
    sync_requested = Signal()
    selection_changed = Signal(object)
    closed = Signal()
    scan_requested = Signal()
    cancel_scan_requested = Signal()
    manage_requested = Signal()
    batch_requested = Signal()
    checked_changed = Signal(object, bool)
    select_all_requested = Signal(bool)
    exclude_requested = Signal(str)
    retry_remote_requested = Signal()
    show_all_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.theme = "light"
        self._plan_mode = False
        self._has_games = False
        self._busy = False
        self._empty_action = "scan"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(1)

        list_host = QWidget()
        list_layout = QVBoxLayout(list_host)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(0)

        self.toolbar = QWidget()
        self.toolbar.setObjectName("DiscoveryToolbar")
        actions = QHBoxLayout(self.toolbar)
        actions.setContentsMargins(18, 10, 18, 10)
        actions.setSpacing(10)
        self.select_all = QCheckBox(tr("discovery.select_all"))
        self.select_all.toggled.connect(self.select_all_requested.emit)
        self.batch_button = QPushButton(tr("discovery.download_selected"))
        self.batch_button.setObjectName("PrimaryButton")
        self.batch_button.clicked.connect(self.batch_requested.emit)
        self.manage_button = QPushButton(tr("discovery.manage"))
        self.manage_button.setObjectName("LinkButton")
        self.manage_button.clicked.connect(self.manage_requested.emit)
        self.rescan_button = QPushButton(tr("discovery.rescan"))
        self.rescan_button.setObjectName("GhostButton")
        self.rescan_button.clicked.connect(self.scan_requested.emit)
        self.cancel_button = QPushButton(tr("action.cancel"))
        self.cancel_button.setObjectName("GhostButton")
        self.cancel_button.clicked.connect(self.cancel_scan_requested.emit)
        actions.addWidget(self.select_all)
        actions.addWidget(self.batch_button)
        actions.addStretch(1)
        actions.addWidget(self.manage_button)
        actions.addWidget(self.rescan_button)
        actions.addWidget(self.cancel_button)
        self.toolbar.hide()
        self.cancel_button.hide()
        list_layout.addWidget(self.toolbar)

        self.stack_host = QWidget()
        self.stack = QStackedLayout(self.stack_host)
        self.stack.setContentsMargins(0, 0, 0, 0)

        self.model = TrainerListModel(self)
        self.delegate = TrainerDelegate(self, self.theme)
        self.view = TrainerListView()
        self.view.setModel(self.model)
        self.view.setItemDelegate(self.delegate)
        self.view.setEditTriggers(TrainerListView.EditTrigger.NoEditTriggers)
        self.view.doubleClicked.connect(self._on_double_click)
        self.view.selectionModel().currentChanged.connect(self._on_current_changed)

        self.model.checked_changed.connect(self.checked_changed.emit)
        self.empty = EmptyState(tr("discovery.empty.title"), "", tr("discovery.scan"))
        self.empty.glyph.hide()
        self.empty.body.hide()
        self.empty.action.clicked.connect(self._on_empty_action)

        list_wrapper = QWidget()
        wrapper_layout = QVBoxLayout(list_wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(self.view)

        self.stack.addWidget(list_wrapper)
        self.stack.addWidget(self.empty)
        list_layout.addWidget(self.stack_host)
        self.splitter.addWidget(list_host)

        self.detail = DetailPanel()
        self.detail.hide()
        self.detail.download_requested.connect(self.download_requested.emit)
        self.detail.open_page_requested.connect(self.open_page_requested.emit)
        self.detail.open_folder_requested.connect(self.open_folder_requested.emit)
        self.detail.close_requested.connect(self._on_close)
        self.splitter.addWidget(self.detail)

        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([800, 280])
        layout.addWidget(self.splitter, 1)

    # -- theming ----------------------------------------------------------
    def set_theme(self, theme: str) -> None:
        self.theme = "light"
        self.delegate.set_theme("light")
        self.view.viewport().update()

    def set_source_names(self, names: dict[str, str]) -> None:
        self.delegate.set_source_names(names)

    def set_remote_keys(self, keys: set[tuple[str, str]]) -> None:
        self.delegate.set_remote_keys(keys)
        self.view.viewport().update()

    def set_installed_keys(self, keys: set[tuple[str, str]]) -> None:
        self.delegate.set_installed_keys(keys)
        self.view.viewport().update()

    # -- data -------------------------------------------------------------
    def set_items(self, items: list[CatalogItem]) -> None:
        self._plan_mode = False
        self.toolbar.hide()
        self.model.set_items(items)
        self.stack.setCurrentIndex(0 if items else 1)
        if not items:
            self.hide_detail()

    def set_plan(self, plan: RecommendationPlan, *, has_games: bool, source_filter: str = "all") -> None:
        self._plan_mode = True
        self._empty_action = "scan"
        self._has_games = has_games
        current = self.current_item()
        entries = [entry for entry in plan.entries if source_filter == "all" or entry.item.source_id == source_filter]
        selection = self.view.selectionModel()
        selection.blockSignals(True)
        self.model.set_entries(entries)
        if current is not None:
            row = self.model.row_of(current.key)
            if row >= 0:
                self.view.setCurrentIndex(self.model.index(row, 0))
            else:
                self.hide_detail()
        selection.blockSignals(False)
        selectable = [entry for entry in entries if entry.action == "download" and entry.state in {"ready", "failed", "cancelled"}]
        self.select_all.blockSignals(True)
        self.select_all.setChecked(bool(selectable) and all(entry.selected for entry in selectable))
        self.select_all.blockSignals(False)
        self.select_all.setEnabled(bool(selectable) and not self._busy)
        self.batch_button.setEnabled(any(entry.selected for entry in selectable) and not self._busy)
        self.toolbar.setVisible(has_games or self._busy)
        self.select_all.setVisible(bool(entries))
        self.batch_button.setVisible(bool(entries))
        self.manage_button.setVisible(has_games)
        self.rescan_button.setVisible(has_games and not self._busy)
        if entries:
            self.stack.setCurrentIndex(0)
        else:
            title = tr("discovery.no_matches") if has_games else tr("discovery.empty.title")
            self.empty.set_text(title, "", "" if has_games or self._busy else tr("discovery.scan"))
            self.stack.setCurrentIndex(1)
            self.hide_detail()

    def set_busy(self, state: str) -> None:
        self._busy = state in {"scanning", "planning"}
        self.cancel_button.setVisible(self._busy)
        if self._plan_mode:
            self.toolbar.setVisible(self._has_games or self._busy)
            self.rescan_button.setVisible(self._has_games and not self._busy)
            self.batch_button.setEnabled(not self._busy and self.batch_button.isEnabled())
            self.select_all.setEnabled(not self._busy)
            if self._busy and not self._has_games:
                self.empty.set_text(tr(f"discovery.{state}"), "", "")

    def set_empty_mode(self, mode: str, query: str = "", *, remote_state: str = "idle", preferred_suppressed: bool = False) -> None:
        self.model.set_items([])
        self._plan_mode = mode != "noresult"
        self._empty_action = ""
        self.toolbar.hide()
        if mode == "noresult":
            if preferred_suppressed:
                self.empty.set_text(tr("search.remote.preferred"), "", tr("search.remote.show_all"))
                self._empty_action = "all"
            elif remote_state == "loading":
                self.empty.set_text(tr("search.remote.loading"), "", "")
            elif remote_state == "failed":
                self.empty.set_text(tr("search.remote.failed"), "", tr("search.remote.retry"))
                self._empty_action = "retry"
            else:
                self.empty.set_text(tr("discover.noresult.title", query=query), "", "")
        else:
            self.empty.set_text(tr("discovery.empty.title"), "", tr("discovery.scan"))
            self._empty_action = "scan"
        self.stack.setCurrentIndex(1)
        self.hide_detail()

    def _on_empty_action(self) -> None:
        if self._empty_action == "retry":
            self.retry_remote_requested.emit()
        elif self._empty_action == "all":
            self.show_all_requested.emit()
        elif self._empty_action == "scan":
            self.scan_requested.emit()

    def current_item(self) -> CatalogItem | None:
        index = self.view.currentIndex()
        if not index.isValid():
            return None
        return self.model.item_at(index.row())

    def select_row(self, row: int) -> None:
        if row < 0:
            return
        index = self.model.index(row, 0)
        self.view.setCurrentIndex(index)
        self.view.scrollTo(index, TrainerListView.ScrollHint.EnsureVisible)

    def replace_item(self, item: CatalogItem) -> None:
        self.model.replace_item(item)

    def show_detail(
        self,
        item: CatalogItem,
        installed: InstalledItem | None,
        source_name: str,
        direct: bool,
        remote: bool = False,
    ) -> None:
        self.detail.show_item(
            item,
            installed,
            source_name=source_name,
            source_supports_direct=direct,
            remote=remote,
        )
        self.detail.show()
        self.splitter.setSizes([max(400, self.splitter.width() - 280), 280])

    def update_installed(self, installed: InstalledItem | None) -> None:
        self.detail.update_installed(installed)

    def hide_detail(self) -> None:
        self.detail.hide()
        self.view.clearSelection()

    # -- events -----------------------------------------------------------
    def _on_close(self) -> None:
        self.hide_detail()
        self.closed.emit()

    def _on_current_changed(self, current, _previous) -> None:
        if current.isValid():
            item = self.model.item_at(current.row())
            if item is not None:
                self.selection_changed.emit(item)

    def _on_double_click(self, index) -> None:
        item = self.model.item_at(index.row())
        if item is not None:
            entry = self.model.entry_at(index.row())
            if entry is not None and entry.action == "external":
                self.open_page_requested.emit(item)
            elif entry is None or entry.state in {"ready", "failed", "cancelled"}:
                self.download_requested.emit(item)

"""Discover page: results list on the left, detail panel on the right."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QSplitter,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from ...core.models import CatalogItem, InstalledItem
from ...i18n import tr
from ..widgets.common import EmptyState, HeaderBar
from ..widgets.detail_panel import DetailPanel
from ..widgets.trainer_list import TrainerDelegate, TrainerListModel, TrainerListView


class DiscoverPage(QWidget):
    download_requested = Signal(object)
    open_page_requested = Signal(object)
    open_folder_requested = Signal(object)
    sync_requested = Signal()
    selection_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.theme = "dark"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = HeaderBar(tr("discover.title"), tr("discover.subtitle"))
        self.count_label = QLabel("")
        self.count_label.setObjectName("PageSubtitle")
        self.header.add_action(self.count_label)
        layout.addWidget(self.header)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(1)

        # -- list side ---------------------------------------------------
        list_host = QWidget()
        list_layout = QVBoxLayout(list_host)
        list_layout.setContentsMargins(18, 4, 8, 16)
        list_layout.setSpacing(0)

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

        self.empty = EmptyState(
            tr("discover.empty.title"), tr("discover.empty.body"), tr("discover.empty.action")
        )
        self.empty.action.clicked.connect(self.sync_requested.emit)

        list_wrapper = QWidget()
        wrapper_layout = QVBoxLayout(list_wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(self.view)

        self.stack.addWidget(list_wrapper)
        self.stack.addWidget(self.empty)
        list_layout.addWidget(self.stack_host)
        self.splitter.addWidget(list_host)

        # -- detail side -------------------------------------------------
        self.detail = DetailPanel()
        self.detail.download_requested.connect(self.download_requested.emit)
        self.detail.open_page_requested.connect(self.open_page_requested.emit)
        self.detail.open_folder_requested.connect(self.open_folder_requested.emit)
        self.splitter.addWidget(self.detail)

        self.splitter.setStretchFactor(0, 62)
        self.splitter.setStretchFactor(1, 38)
        self.splitter.setSizes([760, 420])
        layout.addWidget(self.splitter, 1)

    # -- theming ----------------------------------------------------------
    def set_theme(self, theme: str) -> None:
        self.theme = theme
        self.delegate.set_theme(theme)
        self.detail.set_theme(theme)
        self.view.viewport().update()

    def set_source_names(self, names: dict[str, str]) -> None:
        self.delegate.set_source_names(names)

    # -- data -------------------------------------------------------------
    def set_items(self, items: list[CatalogItem]) -> None:
        self.model.set_items(items)
        has_items = bool(items)
        self.stack.setCurrentIndex(0 if has_items else 1)
        self.count_label.setText(tr("status.count", count=len(items)) if has_items else "")
        if not has_items:
            self.detail._show_placeholder()

    def set_empty_mode(self, mode: str, query: str = "") -> None:
        if mode == "noresult":
            self.empty.set_text(
                tr("discover.noresult.title", query=query),
                tr("discover.noresult.body"),
                "",
            )
        else:
            self.empty.set_text(
                tr("discover.empty.title"), tr("discover.empty.body"), tr("discover.empty.action")
            )
        self.stack.setCurrentIndex(1)
        self.count_label.setText("")

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

    def show_detail(self, item: CatalogItem, installed: InstalledItem | None, source_name: str, direct: bool) -> None:
        self.detail.show_item(item, installed, source_name=source_name, source_supports_direct=direct)

    def update_installed(self, installed: InstalledItem | None) -> None:
        self.detail.update_installed(installed)

    # -- events -----------------------------------------------------------
    def _on_current_changed(self, current, _previous) -> None:
        if current.isValid():
            item = self.model.item_at(current.row())
            if item is not None:
                self.selection_changed.emit(item)

    def _on_double_click(self, index) -> None:
        item = self.model.item_at(index.row())
        if item is not None:
            self.download_requested.emit(item)

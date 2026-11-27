"""Installed Mods: clear evidence, explicit adoption and commit-driven switches."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.config import Config
from ...core.library import open_in_file_manager
from ...core.mods import ModRecord, ModScanReport
from ...core.mods.models import installation_key
from ...i18n import tr
from ..mods_controller import ModsController
from ..theme import INSPECTOR_WIDTH, ROW_HEIGHT, TOKENS
from ..widgets.common import Badge, EmptyState, HeaderBar, SegmentedControl
from ..widgets.mod_switch import ModSwitch


def mod_stylesheet() -> str:
    """Local styles only. The application's v0.3.2 stylesheet stays untouched."""
    text = """
    #ModInspector { background: @surface; border-left: 1px solid @line; }
    #ModNotice { color: @dim; font-size: 12px; }
    #ModNotice[error="true"] { color: @danger; }
    QTableWidget#ModTable {
        background: @surface; border: none;
        selection-background-color: @sunken; selection-color: @text;
    }
    QTableWidget#ModTable::item { padding: 6px; border-bottom: 1px solid @line; }
    QTableWidget#ModTable::item:focus { border: 1px solid @primary; }
    QTableWidget#ModTable QHeaderView::section {
        background: @bg; color: @muted; padding: 8px 6px;
        border: none; border-bottom: 1px solid @line;
    }
    QPlainTextEdit {
        background: @surface; color: @text; border: 1px solid @line;
        border-radius: 6px; padding: 8px;
    }
    QPlainTextEdit:focus { border-color: @primary; }
    QPushButton#GhostButton:focus, QPushButton#PrimaryButton:focus,
    QPushButton#LinkButton:focus { border: 1px solid @primary; }
    """
    for name, value in sorted(TOKENS["light"].items(), key=lambda pair: -len(pair[0])):
        text = text.replace(f"@{name}", value)
    return text


def label(text: str = "", name: str = "FieldHint") -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setObjectName(name)
    widget.setWordWrap(True)
    return widget


def button(text: str, name: str = "GhostButton") -> QPushButton:
    widget = QPushButton(text)
    widget.setObjectName(name)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    return widget


def reason_text(code: str) -> str:
    return tr(f"mods.reason.{code}") if code else ""


class ConfirmModDialog(QDialog):
    def __init__(self, record: ModRecord, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(mod_stylesheet())
        self.setWindowTitle(tr("mods.confirm.title"))
        self.resize(500, 360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        layout.addWidget(label(record.name, "SectionTitle"))
        layout.addWidget(label(tr("mods.confirm.body")))
        layout.addWidget(label(str(Path(record.game.install_path) / record.root)))
        members = QPlainTextEdit("\n".join(record.entries))
        members.setReadOnly(True)
        members.setAccessibleName(tr("mods.files"))
        layout.addWidget(members, 1)
        self.consent = QCheckBox(tr("mods.confirm.consent"))
        layout.addWidget(self.consent)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("mods.confirm.action"))
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.consent.toggled.connect(self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)


class ModDirectoryDialog(QDialog):
    def __init__(self, game, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(mod_stylesheet())
        self.game = game
        self.root = ""
        self.setWindowTitle(tr("mods.directory.title"))
        self.resize(520, 340)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        layout.addWidget(label(tr("mods.directory.body")))
        row = QHBoxLayout()
        self.path = QLineEdit()
        self.path.setReadOnly(True)
        self.path.setObjectName("Field")
        self.path.setAccessibleName(tr("mods.directory.path"))
        self.path.setPlaceholderText(tr("mods.directory.path"))
        browse = button(tr("action.browse"))
        browse.clicked.connect(self._browse)
        row.addWidget(self.path, 1)
        row.addWidget(browse)
        layout.addLayout(row)
        layout.addWidget(label(tr("mods.directory.structure"), "FieldLabel"))
        self.mode = QComboBox()
        self.mode.addItem(tr("mods.directory.folders"), "folders")
        self.mode.addItem(tr("mods.directory.packages"), "packages")
        self.mode.setAccessibleName(tr("mods.directory.structure"))
        layout.addWidget(self.mode)
        self.preview = label()
        layout.addWidget(self.preview, 1)
        self.consent = QCheckBox(tr("mods.directory.consent"))
        self.consent.toggled.connect(self._validate)
        layout.addWidget(self.consent)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("mods.directory.action"))
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _browse(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, tr("mods.directory.path"), self.game.install_path)
        if not selected:
            return
        try:
            self.root = Path(selected).resolve().relative_to(Path(self.game.install_path).resolve()).as_posix()
            if self.root == ".":
                raise ValueError("Game root")
            self.path.setText(selected)
            self.preview.setText(tr("mods.directory.preview", root=self.root))
        except ValueError:
            self.root = ""
            self.path.clear()
            self.preview.setText(tr("mods.reason.unsafe_root"))
        self._validate()

    def _validate(self) -> None:
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(self.root) and self.consent.isChecked())


class ModsPage(QWidget):
    def __init__(self, config: Config, parent=None, *, controller: ModsController | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(mod_stylesheet())
        self.controller = controller or ModsController(config, self)
        self.report = ModScanReport()
        self._query = ""
        self._records: list[ModRecord] = []
        self._row_ids: list[str] = []
        self._switches: dict[str, ModSwitch] = {}
        self._status_labels: dict[str, Badge] = {}
        self._detail_id = ""
        self._busy = False
        self._updating = False
        self._error = ""
        self._pending_ids: set[str] = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.header = HeaderBar(tr("mods.title"), tr("mods.subtitle"))
        self.cancel_button = button(tr("action.cancel"), "LinkButton")
        self.cancel_button.clicked.connect(self.controller.cancel)
        self.cancel_button.hide()
        self.scan_button = button(tr("mods.scan"), "PrimaryButton")
        self.scan_button.clicked.connect(self.controller.scan)
        self.header.add_action(self.cancel_button)
        self.header.add_action(self.scan_button)
        layout.addWidget(self.header)

        game_bar = QHBoxLayout()
        game_bar.setContentsMargins(24, 2, 24, 12)
        self.game_combo = QComboBox()
        self.game_combo.setMinimumWidth(180)
        self.game_combo.setAccessibleName(tr("mods.game"))
        self.game_combo.currentIndexChanged.connect(self._game_changed)
        game_label = label(tr("mods.game"), "FieldLabel")
        game_label.setBuddy(self.game_combo)
        self.directory_button = button(tr("mods.add_directory"))
        self.directory_button.clicked.connect(self._add_directory)
        game_bar.addWidget(game_label)
        game_bar.addWidget(self.game_combo, 1)
        game_bar.addWidget(self.directory_button)
        layout.addLayout(game_bar)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(24, 0, 24, 10)
        self.filter = SegmentedControl([("managed", tr("mods.managed")), ("pending", tr("mods.pending"))])
        self.filter.changed.connect(lambda _: self._render())
        self.enable_button = button(tr("mods.enable_selected"), "LinkButton")
        self.disable_button = button(tr("mods.disable_selected"), "LinkButton")
        self.enable_button.clicked.connect(lambda: self._batch(True))
        self.disable_button.clicked.connect(lambda: self._batch(False))
        toolbar.addWidget(self.filter)
        toolbar.addStretch(1)
        toolbar.addWidget(self.enable_button)
        toolbar.addWidget(self.disable_button)
        layout.addLayout(toolbar)

        self.notice = label()
        self.notice.setObjectName("ModNotice")
        self.notice.setContentsMargins(24, 0, 24, 10)
        layout.addWidget(self.notice)

        body = QHBoxLayout()
        body.setSpacing(0)
        self.stack = QStackedWidget()
        self.table = QTableWidget(0, 5)
        self.table.setObjectName("ModTable")
        self.table.setHorizontalHeaderLabels(["", tr("mods.name"), tr("mods.version"), tr("mods.state"), tr("mods.action")])
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.setAccessibleName(tr("mods.list"))
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column, width in ((0, 36), (2, 70), (3, 86), (4, 118)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(column, width)
        self.table.itemChanged.connect(lambda _: self._update_actions())
        self.table.cellClicked.connect(self._select_detail)
        self.empty = EmptyState()
        self.empty.glyph.hide()
        self.empty.action.clicked.connect(self.controller.scan)
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.empty)
        body.addWidget(self.stack, 1)

        self.inspector = QFrame()
        self.inspector.setObjectName("ModInspector")
        self.inspector.setFixedWidth(INSPECTOR_WIDTH)
        detail_layout = QVBoxLayout(self.inspector)
        detail_layout.setContentsMargins(18, 12, 18, 18)
        detail_layout.setSpacing(10)
        close = button(tr("action.close"), "LinkButton")
        close.clicked.connect(self._close_detail)
        detail_layout.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        self.detail_name = label("", "SectionTitle")
        self.detail_reason = label()
        self.detail_source = label()
        self.detail_path = label()
        for widget in (self.detail_name, self.detail_reason, self.detail_source, self.detail_path):
            detail_layout.addWidget(widget)
        detail_layout.addWidget(label(tr("mods.files"), "FieldLabel"))
        self.detail_files = QPlainTextEdit()
        self.detail_files.setReadOnly(True)
        self.detail_files.setAccessibleName(tr("mods.files"))
        detail_layout.addWidget(self.detail_files, 1)
        self.open_button = button(tr("action.open_folder"))
        self.open_button.clicked.connect(self._open_detail)
        detail_layout.addWidget(self.open_button)
        self.inspector.hide()
        body.addWidget(self.inspector)
        layout.addLayout(body, 1)

        self.controller.report_changed.connect(self.set_report)
        self.controller.busy_changed.connect(self._busy_changed)
        self.controller.failed.connect(self._failed)
        self._render()

    def initialize(self) -> None:
        self.controller.initialize()

    def set_search(self, text: str) -> None:
        self._query = text.strip().casefold()
        self._render()

    def _game(self):
        key = self.game_combo.currentData()
        return next((game for game in self.report.games if installation_key(game) == key), None)

    def set_report(self, report: ModScanReport) -> None:
        current = self.game_combo.currentData()
        self.report = report
        self.game_combo.blockSignals(True)
        self.game_combo.clear()
        for game in sorted(report.games, key=lambda value: value.name.casefold()):
            self.game_combo.addItem(game.name, installation_key(game))
        index = self.game_combo.findData(current)
        if index >= 0:
            self.game_combo.setCurrentIndex(index)
        self.game_combo.blockSignals(False)
        if self.controller.kind == "confirm":
            self.filter.set_current("managed")
        self._error = ""
        self._render()
        if self._detail_id:
            self._show_detail(self._detail_id)

    def _game_changed(self) -> None:
        self._close_detail()
        self._error = ""
        self._render()

    def _render(self) -> None:
        key = self.game_combo.currentData()
        records = [record for record in self.report.records if record.game_key == key]
        managed = [record for record in records if record.confirmed]
        pending = [record for record in records if not record.confirmed]
        self.filter._buttons["managed"].setText(tr("mods.managed_count", count=len(managed)))
        self.filter._buttons["pending"].setText(tr("mods.pending_count", count=len(pending)))
        candidates = managed if self.filter.current() == "managed" else pending
        self._records = sorted(
            [record for record in candidates if not self._query or self._query in f"{record.name} {record.root} {record.version}".casefold()],
            key=lambda value: (value.name.casefold(), value.id),
        )
        identifiers = [record.id for record in self._records]
        rebuild = identifiers != self._row_ids
        self._updating = True
        if rebuild:
            self.table.clearContents()
            self.table.setRowCount(len(self._records))
            self._switches, self._status_labels = {}, {}
            self._row_ids = identifiers
        for row, record in enumerate(self._records):
            if rebuild:
                self.table.setRowHeight(row, ROW_HEIGHT)
                select = QTableWidgetItem()
                select.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable)
                select.setCheckState(Qt.CheckState.Unchecked)
                self.table.setItem(row, 0, select)
                self.table.setItem(row, 1, QTableWidgetItem())
                self.table.setItem(row, 2, QTableWidgetItem())
                badge = Badge()
                self._status_labels[record.id] = badge
                wrapper = QWidget()
                badges = QHBoxLayout(wrapper)
                badges.setContentsMargins(3, 0, 3, 0)
                badges.addWidget(badge)
                self.table.setCellWidget(row, 3, wrapper)
                actions = QWidget()
                action_layout = QHBoxLayout(actions)
                action_layout.setContentsMargins(4, 0, 8, 0)
                action_layout.setSpacing(3)
                if record.confirmed:
                    switch = ModSwitch()
                    switch.setAccessibleName(tr("mods.toggle_for", name=record.name))
                    switch.clicked.connect(lambda _=False, identifier=record.id: self._toggle(identifier))
                    self._switches[record.id] = switch
                    action_layout.addWidget(switch)
                    more = button(tr("mods.details"), "LinkButton")
                else:
                    can_confirm = record.reason in {"unconfirmed", "files_changed"}
                    more = button(tr("mods.confirm.action") if can_confirm else tr("mods.view_reason"), "LinkButton")
                more.clicked.connect(lambda _=False, identifier=record.id: self._activate_pending(identifier))
                action_layout.addWidget(more)
                self.table.setCellWidget(row, 4, actions)
            self.table.item(row, 1).setText(record.name)
            self.table.item(row, 1).setToolTip(str(Path(record.game.install_path) / record.root / record.entries[0]))
            self.table.item(row, 2).setText(record.version or tr("mods.unknown"))
            state = record.state if record.manageable else "attention" if record.confirmed else "pending"
            processing = self._busy and record.id in self._pending_ids
            self._status_labels[record.id].setText(tr("mods.state.processing") if processing else tr(f"mods.state.{state}"))
            self._status_labels[record.id].set_level("success" if state == "enabled" else "warn" if state in {"pending", "attention"} else "neutral")
            self._status_labels[record.id].setToolTip(reason_text(record.reason))
            if record.id in self._switches:
                self._switches[record.id].setChecked(record.state == "enabled")
                self._switches[record.id].setEnabled(record.manageable and not self._busy)
                self._switches[record.id].setToolTip(reason_text(record.reason) or tr("mods.toggle_help"))
            self.table.item(row, 0).setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                | (Qt.ItemFlag.ItemIsUserCheckable if record.manageable and not self._busy else Qt.ItemFlag.NoItemFlags)
            )
            self.table.cellWidget(row, 4).setEnabled(not self._busy)
        self._updating = False
        self.stack.setCurrentWidget(self.table if self._records else self.empty)
        issues = self.report.issues.get(key, [])
        if not self.report.games:
            self.empty.set_text(tr("mods.empty.title"), tr("mods.empty.body"), tr("mods.scan"))
        elif self._query:
            self.empty.set_text(tr("mods.empty.search"), tr("mods.empty.search_body"))
        elif self.filter.current() == "managed" and pending:
            self.empty.set_text(tr("mods.empty.pending"), tr("mods.empty.pending_body", count=len(pending)))
        elif "no_rules" in issues:
            self.empty.set_text(tr("mods.empty.no_rules"), tr("mods.empty.no_rules_body"))
        elif issues:
            self.empty.set_text(tr("mods.empty.partial"), reason_text(issues[0]))
        else:
            self.empty.set_text(tr("mods.empty.none"), tr("mods.empty.none_body"))
        if self._error:
            self.notice.setText(self._error)
            self.notice.setProperty("error", "true")
        elif self._busy:
            self.notice.setText(tr(f"mods.busy.{self.controller.kind}"))
            self.notice.setProperty("error", "false")
        elif any(value != "ok" for value in self.report.library_status.values()):
            self.notice.setText(tr("mods.partial_libraries"))
            self.notice.setProperty("error", "false")
        elif issues and issues != ["no_rules"]:
            self.notice.setText(tr("mods.partial_scan") + " " + reason_text(issues[0]))
            self.notice.setProperty("error", "false")
        else:
            self.notice.setText(tr("mods.local_only"))
            self.notice.setProperty("error", "false")
        self.notice.style().unpolish(self.notice)
        self.notice.style().polish(self.notice)
        self._update_actions()

    def _selected(self) -> list[ModRecord]:
        return [record for row, record in enumerate(self._records) if self.table.item(row, 0).checkState() == Qt.CheckState.Checked and record.manageable]

    def _update_actions(self) -> None:
        if self._updating:
            return
        selected = self._selected()
        self.enable_button.setEnabled(not self._busy and any(record.state == "disabled" for record in selected))
        self.disable_button.setEnabled(not self._busy and any(record.state == "enabled" for record in selected))
        self.directory_button.setEnabled(not self._busy and self._game() is not None)
        self.scan_button.setEnabled(not self._busy)
        self.game_combo.setEnabled(not self._busy)
        self.filter.setEnabled(not self._busy)
        self.empty.action.setEnabled(not self._busy)

    def _batch(self, enabled: bool) -> None:
        records = [record for record in self._selected() if record.state != ("enabled" if enabled else "disabled")]
        if records:
            self._pending_ids = {record.id for record in records}
            self.controller.toggle([record.id for record in records], enabled)

    def _toggle(self, identifier: str) -> None:
        record = next((value for value in self.report.records if value.id == identifier), None)
        if record is not None and record.manageable and not self._busy:
            self._pending_ids = {identifier}
            self.controller.toggle([identifier], record.state != "enabled")

    def _busy_changed(self, busy: bool, kind: str) -> None:
        self._busy = busy
        self.cancel_button.setVisible(busy and kind == "scan")
        self.scan_button.setText(tr("mods.scanning") if busy and kind == "scan" else tr("mods.scan"))
        if busy:
            self._error = ""
        self._render()
        if not busy:
            self._pending_ids.clear()

    def _failed(self, code: str, detail: str) -> None:
        self._error = reason_text(code) + ("\n" + detail if detail else "")
        self._render()

    def _activate_pending(self, identifier: str) -> None:
        record = next((value for value in self.report.records if value.id == identifier), None)
        if record is None or self._busy:
            return
        self._show_detail(identifier)
        if not record.confirmed and record.reason in {"unconfirmed", "files_changed"}:
            if ConfirmModDialog(record, self).exec() == QDialog.DialogCode.Accepted:
                self.controller.confirm(identifier)

    def _select_detail(self, row: int, column: int) -> None:
        if column != 0 and 0 <= row < len(self._records):
            self._show_detail(self._records[row].id)

    def _show_detail(self, identifier: str) -> None:
        record = next((value for value in self.report.records if value.id == identifier), None)
        if record is None:
            self._close_detail()
            return
        self._detail_id = identifier
        self.detail_name.setText(record.name)
        self.detail_reason.setText(reason_text(record.reason) or tr("mods.toggle_help"))
        self.detail_source.setText(tr("mods.evidence", source=tr(f"mods.evidence.{record.evidence}")))
        original = Path(record.game.install_path) / record.root
        self.detail_path.setText(str(original))
        self.detail_files.setPlainText("\n".join(record.entries))
        self.inspector.show()

    def _close_detail(self) -> None:
        self._detail_id = ""
        self.inspector.hide()

    def _open_detail(self) -> None:
        record = next((value for value in self.report.records if value.id == self._detail_id), None)
        if record is not None:
            path = self.controller.service._vault(record) if record.state == "disabled" else Path(record.game.install_path) / record.root
            open_in_file_manager(path)

    def _add_directory(self) -> None:
        game = self._game()
        if game is None or self._busy:
            return
        dialog = ModDirectoryDialog(game, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.controller.add_rule(game, dialog.root, dialog.mode.currentData())

    def cleanup(self) -> None:
        self.controller.cleanup()

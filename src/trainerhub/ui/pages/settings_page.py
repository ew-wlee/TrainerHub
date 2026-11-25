"""Settings: grouped cards, applied immediately."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ... import HOMEPAGE, VERSION
from ...core import defender
from ...core.config import Config
from ...i18n import tr
from ..widgets.common import HeaderBar, NoticeBox, SectionTitle


class SettingsPage(QWidget):
    theme_changed = Signal(str)
    language_changed = Signal(str)
    library_changed = Signal(str)
    sources_changed = Signal()
    settings_changed = Signal()

    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(HeaderBar(tr("settings.title"), tr("app.tagline")))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(20, 4, 20, 24)
        self.body_layout.setSpacing(12)

        self.body_layout.addWidget(self._general_card())
        self.body_layout.addWidget(self._sources_card())
        self.body_layout.addWidget(self._download_card())
        self.body_layout.addWidget(self._safety_card())
        self.body_layout.addWidget(self._about_card())
        self.body_layout.addStretch(1)

        scroll.setWidget(body)
        layout.addWidget(scroll, 1)

    # -- helpers ----------------------------------------------------------
    def _card(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("Card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        layout.addWidget(SectionTitle(title))
        return frame, layout

    def _row(self, label_key: str, widget: QWidget, hint_key: str = "") -> QWidget:
        row = QWidget()
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        head = QHBoxLayout()
        head.setSpacing(12)
        label = QLabel(tr(label_key))
        label.setObjectName("FieldLabel")
        head.addWidget(label, 1)
        head.addWidget(widget)
        layout.addLayout(head)
        if hint_key:
            hint = QLabel(tr(hint_key))
            hint.setObjectName("FieldHint")
            hint.setWordWrap(True)
            layout.addWidget(hint)
        return row

    # -- cards ------------------------------------------------------------
    def _general_card(self) -> QFrame:
        frame, layout = self._card(tr("settings.section.general"))

        self.theme_combo = QComboBox()
        self.theme_combo.addItem(tr("settings.theme.dark"), "dark")
        self.theme_combo.addItem(tr("settings.theme.light"), "light")
        self.theme_combo.setCurrentIndex(0 if self.config.theme == "dark" else 1)
        self.theme_combo.currentIndexChanged.connect(self._on_theme)
        layout.addWidget(self._row("settings.theme", self.theme_combo))

        self.language_combo = QComboBox()
        self.language_combo.addItem("简体中文", "zh_CN")
        self.language_combo.addItem("English", "en_US")
        self.language_combo.setCurrentIndex(0 if self.config.language == "zh_CN" else 1)
        self.language_combo.currentIndexChanged.connect(self._on_language)
        layout.addWidget(self._row("settings.language", self.language_combo))

        library_row = QWidget()
        library_layout = QHBoxLayout(library_row)
        library_layout.setContentsMargins(0, 0, 0, 0)
        library_layout.setSpacing(8)
        self.library_edit = QLineEdit(str(self.config.library_dir))
        self.library_edit.setObjectName("Field")
        self.library_edit.setReadOnly(True)
        browse = QPushButton(tr("action.browse"))
        browse.setObjectName("GhostButton")
        browse.setCursor(Qt.CursorShape.PointingHandCursor)
        browse.clicked.connect(self._on_browse)
        library_layout.addWidget(self.library_edit, 1)
        library_layout.addWidget(browse)
        layout.addWidget(self._row("settings.library_dir", library_row))

        self.sync_check = QCheckBox(tr("settings.sync_on_start"))
        self.sync_check.setChecked(bool(self.config.get("ui.sync_on_start", True)))
        self.sync_check.toggled.connect(self._on_sync_toggle)
        layout.addWidget(self.sync_check)
        return frame

    def _sources_card(self) -> QFrame:
        frame, layout = self._card(tr("settings.section.sources"))
        self._source_checks: dict[str, QCheckBox] = {}
        for source_id, label_key in (
            ("fling", "source.fling"),
            ("xiaoxing", "source.xiaoxing"),
            ("custom", "source.custom"),
        ):
            check = QCheckBox(tr(label_key))
            check.setChecked(self.config.source_enabled(source_id))
            check.toggled.connect(self._on_sources_toggle)
            layout.addWidget(check)
            self._source_checks[source_id] = check

        self.custom_edit = QLineEdit(str(self.config.get("sources.custom.index_url", "")))
        self.custom_edit.setObjectName("Field")
        self.custom_edit.setPlaceholderText("https://example.com/trainers.json")
        self.custom_edit.editingFinished.connect(self._on_custom_url)
        layout.addWidget(self._row("settings.custom_source", self.custom_edit, "settings.custom_source.hint"))
        return frame

    def _download_card(self) -> QFrame:
        frame, layout = self._card(tr("settings.section.download"))
        self.concurrency_combo = QComboBox()
        for value in (1, 2, 3, 4):
            self.concurrency_combo.addItem(str(value), value)
        current = int(self.config.get("download.concurrency", 2))
        self.concurrency_combo.setCurrentIndex(max(0, min(3, current - 1)))
        self.concurrency_combo.currentIndexChanged.connect(self._on_concurrency)
        layout.addWidget(self._row("settings.concurrency", self.concurrency_combo))

        self.auto_update_check = QCheckBox(tr("settings.auto_update"))
        self.auto_update_check.setChecked(bool(self.config.get("download.auto_update_trainers", True)))
        self.auto_update_check.toggled.connect(self._on_auto_update)
        layout.addWidget(self.auto_update_check)

        self.auto_data_check = QCheckBox(tr("settings.auto_update_data"))
        self.auto_data_check.setChecked(bool(self.config.get("download.auto_update_data", False)))
        self.auto_data_check.toggled.connect(self._on_auto_data)
        layout.addWidget(self.auto_data_check)
        return frame

    def _safety_card(self) -> QFrame:
        frame, layout = self._card(tr("settings.section.safety"))
        self.defender_button = QPushButton(tr("settings.defender"))
        self.defender_button.setObjectName("GhostButton")
        self.defender_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.defender_button.setEnabled(defender.supported())
        self.defender_button.clicked.connect(self._on_defender)
        layout.addWidget(self._row("settings.defender", self.defender_button, "settings.defender.hint"))

        self.defender_status = QLabel("")
        self.defender_status.setObjectName("FieldHint")
        layout.addWidget(self.defender_status)

        if not defender.supported():
            self.defender_status.setText(tr("settings.defender.unsupported"))

        layout.addWidget(NoticeBox(tr("settings.about.disclaimer")))
        return frame

    def _about_card(self) -> QFrame:
        frame, layout = self._card(tr("settings.section.about"))
        body = QLabel(tr("settings.about.body"))
        body.setWordWrap(True)
        body.setObjectName("FieldHint")
        layout.addWidget(body)

        version = QLabel(tr("app.version", version=VERSION))
        version.setObjectName("FieldHint")
        layout.addWidget(version)

        link = QLabel(f'<a href="{HOMEPAGE}" style="color:#4E8CFF;text-decoration:none;">{HOMEPAGE}</a>')
        link.setOpenExternalLinks(True)
        layout.addWidget(link)

        license_label = QLabel(tr("settings.about.license"))
        license_label.setObjectName("FieldHint")
        layout.addWidget(license_label)
        return frame

    # -- handlers ---------------------------------------------------------
    def _on_theme(self) -> None:
        theme = self.theme_combo.currentData()
        self.config.set("theme", theme)
        self.theme_changed.emit(theme)

    def _on_language(self) -> None:
        language = self.language_combo.currentData()
        if language == self.config.language:
            return
        self.config.set("language", language)
        self.language_changed.emit(language)

    def _on_browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("settings.library_dir"), str(self.config.library_dir))
        if not folder:
            return
        self.config.set("library_dir", folder)
        self.library_edit.setText(folder)
        self.library_changed.emit(folder)

    def _on_sync_toggle(self, checked: bool) -> None:
        self.config.set("ui.sync_on_start", checked)
        self.settings_changed.emit()

    def _on_sources_toggle(self, _checked: bool) -> None:
        for source_id, check in self._source_checks.items():
            self.config.set(f"sources.{source_id}.enabled", check.isChecked())
        self.sources_changed.emit()

    def _on_custom_url(self) -> None:
        self.config.set("sources.custom.index_url", self.custom_edit.text().strip())
        self.sources_changed.emit()

    def _on_concurrency(self) -> None:
        self.config.set("download.concurrency", int(self.concurrency_combo.currentData()))
        self.settings_changed.emit()

    def _on_auto_update(self, checked: bool) -> None:
        self.config.set("download.auto_update_trainers", checked)

    def _on_auto_data(self, checked: bool) -> None:
        self.config.set("download.auto_update_data", checked)

    def _on_defender(self) -> None:
        result = defender.add_exclusion(self.config.library_dir)
        if result.ok:
            self.config.set("safety.defender_exclusion_added", True)
            self.defender_status.setText(tr("settings.defender.done"))
        else:
            self.defender_status.setText(tr("settings.defender.failed"))

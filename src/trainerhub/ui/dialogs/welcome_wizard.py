"""First-run wizard: disclaimer, library folder, sources."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ...core.config import Config
from ...core.paths import default_library_dir
from ...i18n import tr


class WelcomeWizard(QDialog):
    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.setWindowTitle(tr("wizard.welcome"))
        self.setModal(True)
        self.setMinimumSize(620, 460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(14)

        self.steps = QStackedWidget()
        self.steps.addWidget(self._welcome_step())
        self.steps.addWidget(self._library_step())
        self.steps.addWidget(self._sources_step())
        layout.addWidget(self.steps, 1)

        dots_row = QHBoxLayout()
        dots_row.setSpacing(6)
        self._dots: list[QLabel] = []
        for _ in range(3):
            dot = QLabel("●")
            dot.setStyleSheet("color: rgba(255,255,255,0.18); font-size: 10px;")
            self._dots.append(dot)
            dots_row.addWidget(dot)
        dots_row.addStretch(1)

        self.back_button = QPushButton(tr("action.back"))
        self.back_button.setObjectName("GhostButton")
        self.back_button.clicked.connect(self._go_back)
        self.next_button = QPushButton(tr("action.next"))
        self.next_button.setObjectName("PrimaryButton")
        self.next_button.setDefault(True)
        self.next_button.clicked.connect(self._go_next)
        for button in (self.back_button, self.next_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)

        dots_row.addWidget(self.back_button)
        dots_row.addWidget(self.next_button)
        layout.addLayout(dots_row)

        self._update_step()

    # -- steps ------------------------------------------------------------
    def _step_shell(self, title: str, body: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("PageTitle")
        text = QLabel(body)
        text.setObjectName("PageSubtitle")
        text.setWordWrap(True)
        # Centre the step content vertically: the dialog is a fixed size and a
        # top-aligned block leaves most of the window empty.
        layout.addStretch(1)
        layout.addWidget(heading)
        layout.addWidget(text)
        layout.addSpacing(8)
        return page, layout

    def _welcome_step(self) -> QWidget:
        page, layout = self._step_shell(tr("wizard.welcome"), tr("wizard.welcome.body"))
        notice = QLabel(tr("wizard.disclaimer.body"))
        notice.setObjectName("NoticeBox")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.accept_check = QCheckBox(tr("wizard.disclaimer.accept"))
        self.accept_check.toggled.connect(lambda _checked: self._update_step())
        layout.addWidget(self.accept_check)
        layout.addStretch(1)
        return page

    def _library_step(self) -> QWidget:
        page, layout = self._step_shell(tr("wizard.library.title"), tr("wizard.library.body"))
        row = QHBoxLayout()
        row.setSpacing(8)
        self.library_edit = QLineEdit(str(self.config.library_dir or default_library_dir()))
        self.library_edit.setObjectName("Field")
        browse = QPushButton(tr("action.browse"))
        browse.setObjectName("GhostButton")
        browse.clicked.connect(self._browse)
        row.addWidget(self.library_edit, 1)
        row.addWidget(browse)
        layout.addLayout(row)
        layout.addStretch(1)
        return page

    def _sources_step(self) -> QWidget:
        page, layout = self._step_shell(tr("wizard.sources.title"), tr("wizard.sources.body"))
        self.source_checks: dict[str, QCheckBox] = {}
        for source_id, label_key in (
            ("fling", "source.fling"),
            ("xiaoxing", "source.xiaoxing"),
            ("custom", "source.custom"),
        ):
            check = QCheckBox(tr(label_key))
            check.setChecked(self.config.source_enabled(source_id) or source_id == "fling")
            if source_id == "custom":
                check.setChecked(False)
            layout.addWidget(check)
            self.source_checks[source_id] = check
        hint = QLabel(tr("detail.external_hint"))
        hint.setObjectName("FieldHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        return page

    # -- navigation -------------------------------------------------------
    def _update_step(self) -> None:
        index = self.steps.currentIndex()
        last = index == self.steps.count() - 1
        self.back_button.setVisible(index > 0)
        self.next_button.setText(tr("action.finish") if last else tr("action.next"))
        self.next_button.setEnabled(not (index == 0 and not self.accept_check.isChecked()))
        for position, dot in enumerate(self._dots):
            color = "rgba(78,140,255,1)" if position == index else "rgba(255,255,255,0.18)"
            dot.setStyleSheet(f"color: {color}; font-size: 10px;")

    def _go_back(self) -> None:
        self.steps.setCurrentIndex(max(0, self.steps.currentIndex() - 1))
        self._update_step()

    def _go_next(self) -> None:
        if self.steps.currentIndex() == 0 and not self.accept_check.isChecked():
            return
        if self.steps.currentIndex() < self.steps.count() - 1:
            self.steps.setCurrentIndex(self.steps.currentIndex() + 1)
            self._update_step()
            return
        self._apply()
        self.accept()

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("wizard.library.title"), self.library_edit.text())
        if folder:
            self.library_edit.setText(folder)

    def _apply(self) -> None:
        self.config.set("library_dir", self.library_edit.text().strip(), save=False)
        for source_id, check in self.source_checks.items():
            self.config.set(f"sources.{source_id}.enabled", check.isChecked(), save=False)
        self.config.set("safety.disclaimer_accepted", True, save=False)
        self.config.set("first_run", False, save=False)
        self.config.save()

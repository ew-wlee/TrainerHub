from __future__ import annotations

import threading
import time

import pytest
from PySide6.QtCore import QAbstractAnimation, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox

from trainerhub.core.config import Config
from trainerhub.core.models import SteamGame
from trainerhub.core.mods import ModError, ModService
from trainerhub.core.mods.models import installation_key
from trainerhub.i18n import set_language, tr
from trainerhub.ui import theme
from trainerhub.ui.mods_controller import ModsController
from trainerhub.ui.pages.mods_page import ConfirmModDialog, ModsPage
from trainerhub.ui.widgets.mod_switch import ModSwitch


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


def wait_until(predicate, timeout=3000):
    deadline = time.monotonic() + timeout / 1000
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
        # qWait can monopolize the GIL in Windows' test event loop. The real
        # QApplication event loop releases it while background file I/O runs.
        time.sleep(0.002)
    assert predicate()


@pytest.fixture
def page(app, tmp_path):
    set_language("zh_CN")
    theme.apply(app)
    game_path = tmp_path / "Steam/steamapps/common/Game"
    game_path.mkdir(parents=True)
    game = SteamGame("123", "测试游戏", str(tmp_path / "Steam"), str(game_path))
    for name in ("First", "Second"):
        folder = game_path / "Mods" / name
        folder.mkdir(parents=True)
        (folder / "payload.txt").write_text(name)
    config = Config(tmp_path / "config.json")
    service = ModService(tmp_path / "Mods", running=lambda _: False)
    report = service.scan([game])
    service.confirm(report.records[0].id)
    report = service.read()
    controller = ModsController(config, service=service)
    view = ModsPage(config, controller=controller)
    view.resize(836, 524)
    controller.report = report
    view.set_report(report)
    view.show()
    QTest.qWait(10)
    yield view
    view.cleanup()
    view.close()
    controller.deleteLater()
    QApplication.processEvents()


def test_pending_records_have_no_switch(page):
    assert page.table.rowCount() == 1
    assert len(page._switches) == 1
    page.filter.set_current("pending")
    assert page.table.rowCount() == 1
    assert page._switches == {}
    assert not page.enable_button.isEnabled() and not page.disable_button.isEnabled()


def test_toggle_waits_for_commit_and_preserves_keyboard_access(page, monkeypatch):
    identifier = next(iter(page._switches))
    switch = page._switches[identifier]
    assert switch.isChecked()
    service = page.controller.service
    original_toggle = service.toggle
    entered, release = threading.Event(), threading.Event()

    def delayed_toggle(identifiers, enabled):
        entered.set()
        assert release.wait(2)
        return original_toggle(identifiers, enabled)

    monkeypatch.setattr(service, "toggle", delayed_toggle)
    try:
        switch.setFocus()
        QTest.keyClick(switch, Qt.Key.Key_Space)
        wait_until(entered.is_set)
        assert page.controller.busy
        assert switch.isChecked() and not switch.isEnabled()
        assert tr("mods.busy.disable") in page.notice.text()
        assert page._status_labels[identifier].text() == tr("mods.state.processing")
    finally:
        release.set()
    wait_until(lambda: not page.controller.busy)
    assert not switch.isChecked() and switch.isEnabled()
    assert page.report.records[0].state == "disabled"
    QTest.keyClick(switch, Qt.Key.Key_Space)
    wait_until(lambda: not page.controller.busy)
    assert switch.isChecked()


def test_failed_toggle_keeps_previous_state_and_displays_reason(page, monkeypatch):
    switch = next(iter(page._switches.values()))

    def fail(*_):
        raise ModError("game_running", "测试游戏")

    monkeypatch.setattr(page.controller.service, "toggle", fail)
    QTest.mouseClick(switch, Qt.MouseButton.LeftButton)
    wait_until(lambda: not page.controller.busy)
    assert switch.isChecked() and switch.isEnabled()
    assert reason_text_in_page(page, "game_running")


def reason_text_in_page(page, reason):
    return tr(f"mods.reason.{reason}") in page.notice.text()


def test_confirm_requires_explicit_consent(page, monkeypatch):
    pending = next(record for record in page.report.records if not record.confirmed)
    dialog = ConfirmModDialog(pending)
    ok = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert not ok.isEnabled()
    dialog.consent.setChecked(True)
    assert ok.isEnabled()
    dialog.close()
    page.filter.set_current("pending")
    monkeypatch.setattr(ConfirmModDialog, "exec", lambda _: QDialog.DialogCode.Rejected)
    page._activate_pending(pending.id)
    assert not page.controller.busy
    monkeypatch.setattr(ConfirmModDialog, "exec", lambda _: QDialog.DialogCode.Accepted)
    page._activate_pending(pending.id)
    wait_until(lambda: not page.controller.busy)
    assert page.filter.current() == "managed"
    assert len(page._switches) == 2


def test_search_is_local_and_does_not_mutate_records(page):
    page.set_search("does not exist")
    assert page.table.rowCount() == 0
    assert page.empty.title.text() == tr("mods.empty.search")
    assert len(page.report.records) == 2
    page.set_search("")
    assert page.table.rowCount() == 1


def test_batch_controls_only_include_confirmed_checked_records(page):
    record = page._records[0]
    page.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    assert page.disable_button.isEnabled() and not page.enable_button.isEnabled()
    QTest.mouseClick(page.disable_button, Qt.MouseButton.LeftButton)
    wait_until(lambda: not page.controller.busy)
    assert next(value for value in page.report.records if value.id == record.id).state == "disabled"
    assert page.enable_button.isEnabled() and not page.disable_button.isEnabled()


def test_unsafe_markup_in_metadata_stays_plain_text(page):
    record = page._records[0]
    record.name = '<a href="https://example.test">not a link</a>'
    page._show_detail(record.id)
    assert page.detail_name.textFormat() == Qt.TextFormat.PlainText
    assert page.detail_name.text() == record.name


def test_hidden_or_reduced_motion_switch_goes_directly_to_final_value(app, monkeypatch):
    monkeypatch.setenv("TRAINERHUB_REDUCED_MOTION", "1")
    switch = ModSwitch()
    switch.show()
    switch.setChecked(True)
    assert switch.position == 1
    assert switch.animation.state() == QAbstractAnimation.State.Stopped
    switch.hide()
    switch.setChecked(False)
    assert switch.position == 0


def test_motion_retargets_from_current_position_without_delaying_clicks(app, monkeypatch):
    monkeypatch.setattr("trainerhub.ui.widgets.mod_switch.animations_enabled", lambda: True)
    switch = ModSwitch()
    switch.show()
    QTest.qWait(10)
    clicked = QSignalSpy(switch.clicked)
    QTest.mouseClick(switch, Qt.MouseButton.LeftButton)
    assert clicked.count() == 1 and not switch.isChecked()
    switch.setChecked(True)
    QTest.qWait(40)
    intermediate = switch.position
    assert 0 < intermediate < 1
    switch.setChecked(False)
    assert switch.animation.startValue() == intermediate
    QTest.qWait(180)
    assert switch.position == 0
    switch.close()


def test_stale_worker_result_is_ignored(page):
    old = page.controller.report
    page.controller._on_result(-1, object(), "", "")
    assert page.controller.report is old


def test_load_keeps_scan_diagnostics_across_restart(page):
    service = page.controller.service
    game = page.report.games[0]
    report = service.scan([game], library_status={game.library_path: "unavailable"})
    assert report.library_status == service.read().library_status


def test_empty_unknown_game_is_not_reported_as_having_no_mods(page):
    record = page.report.records[0]
    game = record.game
    game_key = record.game_key
    page.report.records = []
    page.report.issues = {game_key: ["no_rules"]}
    page.set_report(page.report)
    assert page.empty.title.text() == tr("mods.empty.no_rules")
    assert page.game_combo.currentData() == installation_key(game)


def test_english_labels_exist_and_no_raw_translation_keys_leak(page):
    set_language("en_US")
    assert tr("mods.reason.configuration_required").startswith("Configuration")
    assert tr("nav.mods") == "Mods"
    set_language("zh_CN")

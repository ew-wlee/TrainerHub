"""Qt bridge: discovery and hashing never run on the UI thread."""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QThread, Signal

from ..core.mods import ModError, ScanCancelled


class ModWorker(QThread):
    result = Signal(int, object, str, str)

    def __init__(self, generation: int, task: Callable, parent=None) -> None:
        super().__init__(parent)
        self.generation = generation
        self.task = task

    def stop(self) -> None:
        self.requestInterruption()

    def run(self) -> None:
        try:
            report = self.task(self.isInterruptionRequested)
            self.result.emit(self.generation, report, "", "")
        except ScanCancelled:
            self.result.emit(self.generation, None, "cancelled", "")
        except ModError as exc:
            self.result.emit(self.generation, None, exc.code, exc.detail)
        except Exception as exc:  # noqa: BLE001 - worker errors must retire the thread
            logging.getLogger(__name__).exception("Mod operation failed")
            self.result.emit(self.generation, None, "operation_failed", str(exc))

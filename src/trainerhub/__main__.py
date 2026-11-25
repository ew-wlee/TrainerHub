"""Console entry point: ``python -m trainerhub`` / ``trainerhub``.

Absolute imports only: this module doubles as the PyInstaller entry script,
where it is executed as a top-level file with no parent package.
"""

from __future__ import annotations

import ctypes
import sys


def main() -> int:
    if sys.platform.startswith("win"):
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TrainerHub.Desktop.0.1")
        except (AttributeError, OSError):  # pragma: no cover - non-Windows
            pass

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    from trainerhub.app import TrainerHubApp, install_exception_hook

    install_exception_hook()
    return TrainerHubApp(sys.argv).run()


if __name__ == "__main__":
    raise SystemExit(main())

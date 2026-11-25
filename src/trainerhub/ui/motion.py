"""Small native motion settings for short, interruptible feedback."""

from __future__ import annotations

import os
import sys


def animations_enabled() -> bool:
    """Respect Windows' animation setting; allow a deterministic test override."""
    if os.environ.get("TRAINERHUB_REDUCED_MOTION") == "1":
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            enabled = ctypes.c_int()
            ok = ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)
            if ok:
                return bool(enabled.value)
        except (AttributeError, OSError):
            pass
    return True

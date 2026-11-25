"""Windows Defender exclusion helper.

Trainers rewrite game memory, so Defender frequently quarantines them. This
module offers the same convenience the reference product does — but scoped to
the user's own library folder, behind an explicit confirmation, and with no
attempt to weaken anything else.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class DefenderResult:
    ok: bool
    message: str = ""
    needs_admin: bool = False


def supported() -> bool:
    return sys.platform.startswith("win")


def _run(command: str) -> tuple[int, str]:
    flags = 0
    if sys.platform.startswith("win"):
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    completed = subprocess.run(  # noqa: S603,S607
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        capture_output=True,
        text=True,
        creationflags=flags,
        timeout=60,
        check=False,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode, output.strip()


def _quote(path: Path) -> str:
    return str(path).replace("'", "''")


def add_exclusion(path: Path) -> DefenderResult:
    if not supported():
        return DefenderResult(False, "Windows only")
    target = Path(path)
    if not target.exists():
        return DefenderResult(False, f"path does not exist: {target}")
    code, output = _run(f"Add-MpPreference -ExclusionPath '{_quote(target)}'")
    if code == 0:
        return DefenderResult(True, str(target))
    lowered = output.lower()
    needs_admin = "access is denied" in lowered or "拒绝访问" in output or "0x80070005" in output
    return DefenderResult(False, output or f"exit code {code}", needs_admin=needs_admin)


def remove_exclusion(path: Path) -> DefenderResult:
    if not supported():
        return DefenderResult(False, "Windows only")
    code, output = _run(f"Remove-MpPreference -ExclusionPath '{_quote(Path(path))}'")
    return DefenderResult(code == 0, output or ("removed" if code == 0 else f"exit code {code}"))


def exclusion_exists(path: Path) -> bool:
    if not supported():
        return False
    code, output = _run("(Get-MpPreference).ExclusionPath -join \"`n\"")
    if code != 0:
        return False
    wanted = str(Path(path)).rstrip("\\/").casefold()
    return any(line.strip().rstrip("\\/").casefold() == wanted for line in output.splitlines())

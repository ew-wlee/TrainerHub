"""Durable atomic JSON state with a process lock; never silently reset damaged state."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

from .models import ModError


class ModStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.path = directory / "state.json"
        self._lock = RLock()

    @contextmanager
    def session(self):
        with self._lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            with (self.directory / "state.lock").open("a+b") as stream:
                if stream.tell() == 0:
                    stream.write(b"0")
                    stream.flush()
                stream.seek(0)
                try:
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    raise ModError("store_busy") from exc
                try:
                    yield self.load()
                finally:
                    stream.seek(0)
                    if os.name == "nt":
                        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(stream, fcntl.LOCK_UN)

    def load(self) -> dict:
        if not self.path.exists():
            return {"version": 1, "games": {}, "records": {}, "rules": {}, "journal": None}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if value["version"] != 1 or not all(isinstance(value[key], dict) for key in ("games", "records", "rules")):
                raise ValueError("Invalid schema")
            if value.get("journal") is not None and not isinstance(value["journal"], dict):
                raise ValueError("Invalid journal")
            return value
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ModError("store_corrupt", str(self.path)) from exc

    def save(self, data: dict) -> None:
        descriptor, temporary = tempfile.mkstemp(dir=self.directory, suffix=".tmp")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

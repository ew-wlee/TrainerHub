"""Persistent identities are scoped to a Steam installation, not just an AppID."""

from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..models import SteamGame


class ModError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


class ScanCancelled(Exception):
    pass


def installation_key(game: SteamGame) -> str:
    identity = f"{game.appid}:{os.path.normcase(str(Path(game.install_path).resolve()))}"
    return hashlib.sha256(identity.encode()).hexdigest()[:24]


@dataclass
class DetectionRule:
    game_key: str
    root: str  # relative to the game directory
    mode: str = "folders"  # folders | packages
    source: str = "user"

    @property
    def key(self) -> str:
        return f"{self.game_key}:{self.root.casefold()}:{self.mode}"


@dataclass
class ModRecord:
    id: str
    game: SteamGame
    root: str
    entries: list[str]
    name: str
    version: str = ""
    state: str = "pending"
    confirmed: bool = False
    evidence: str = "candidate"
    reason: str = "unconfirmed"
    inventory: dict[str, str] = field(default_factory=dict)

    @property
    def game_key(self) -> str:
        return installation_key(self.game)

    @property
    def manageable(self) -> bool:
        return self.confirmed and self.state in {"enabled", "disabled"} and not self.reason

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> ModRecord:
        value = dict(value)
        value["game"] = SteamGame(**value["game"])
        return cls(**value)


@dataclass
class ModScanReport:
    games: list[SteamGame] = field(default_factory=list)
    records: list[ModRecord] = field(default_factory=list)
    rules: list[DetectionRule] = field(default_factory=list)
    issues: dict[str, list[str]] = field(default_factory=dict)
    library_status: dict[str, str] = field(default_factory=dict)

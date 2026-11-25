"""Catalogue source adapters."""

from .base import BaseSource, SourceError, build_sources
from .custom_json import CustomJsonSource
from .fling import FlingSource
from .xiaoxing import XiaoxingSource

__all__ = [
    "BaseSource",
    "CustomJsonSource",
    "FlingSource",
    "SourceError",
    "XiaoxingSource",
    "build_sources",
]

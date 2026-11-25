"""Qt-free business layer: models, storage, search, sources, download pipeline."""

from .archive import ArchiveError, UnsafeArchive, extract, is_archive, sniff
from .config import Config
from .db import Database
from .downloader import Downloader, DownloadError, ExternalTarget
from .http import DownloadCancelled, HttpClient, NetworkError, SourceStructureError
from .library import LibraryService, open_in_file_manager
from .models import CatalogItem, DownloadTarget, InstalledItem, SourcePage
from .search import SearchEngine, SearchHit
from .updater import UpdateCandidate, UpdateService

__all__ = [
    "ArchiveError",
    "CatalogItem",
    "Config",
    "Database",
    "DownloadCancelled",
    "DownloadError",
    "DownloadTarget",
    "Downloader",
    "ExternalTarget",
    "HttpClient",
    "InstalledItem",
    "LibraryService",
    "NetworkError",
    "SearchEngine",
    "SearchHit",
    "SourcePage",
    "SourceStructureError",
    "UnsafeArchive",
    "UpdateCandidate",
    "UpdateService",
    "extract",
    "is_archive",
    "open_in_file_manager",
    "sniff",
]

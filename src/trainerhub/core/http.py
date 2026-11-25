"""HTTP plumbing: browser-ish headers, polite rate limiting, retries, streaming."""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 TrainerHub/0.1"
)

RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}


class NetworkError(RuntimeError):
    """Transport-level failure after retries were exhausted."""


class SourceStructureError(RuntimeError):
    """The remote page/JSON no longer looks the way the adapter expects."""


class RateLimiter:
    def __init__(self, min_interval: float = 0.5) -> None:
        self.min_interval = max(0.0, min_interval)
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        if self.min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            delay = self.min_interval - (now - self._last)
            if delay > 0:
                time.sleep(delay)
            self._last = time.monotonic()


class HttpClient:
    def __init__(
        self,
        *,
        timeout: float = 20.0,
        max_retries: int = 2,
        min_interval: float = 0.5,
        proxy: str | None = None,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self._limiter = RateLimiter(min_interval)
        self._client = httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers={
                "User-Agent": DEFAULT_UA,
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
            proxy=proxy or None,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- core request -----------------------------------------------------
    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self._limiter.wait()
            try:
                response = self._client.request(method, url, **kwargs)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
            else:
                if response.status_code in RETRY_STATUS:
                    last_error = NetworkError(f"HTTP {response.status_code} for {url}")
                elif response.status_code >= 400:
                    raise NetworkError(f"HTTP {response.status_code} for {url}")
                else:
                    return response
            if attempt < self.max_retries:
                time.sleep(0.6 * (attempt + 1) + random.uniform(0, 0.4))
        raise NetworkError(f"request failed: {url} ({last_error})")

    def get_json(self, url: str, params: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        response = self._request("GET", url, params=params, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise SourceStructureError(f"expected JSON from {url}") from exc

    def get_text(self, url: str, **kwargs: Any) -> str:
        return self._request("GET", url, **kwargs).text

    # -- streaming download ----------------------------------------------
    def download(
        self,
        url: str,
        dest: Path,
        *,
        headers: dict[str, str] | None = None,
        progress: Callable[[int, int], None] | None = None,
        cancel: threading.Event | None = None,
        chunk_size: int = 64 * 1024,
    ) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_suffix(dest.suffix + ".part")
        self._limiter.wait()
        try:
            with self._client.stream("GET", url, headers=headers or {}) as response:
                if response.status_code >= 400:
                    raise NetworkError(f"HTTP {response.status_code} for {url}")
                total = int(response.headers.get("Content-Length") or 0)
                received = 0
                with part.open("wb") as stream:
                    for chunk in response.iter_bytes(chunk_size):
                        if cancel is not None and cancel.is_set():
                            raise DownloadCancelled(url)
                        if not chunk:
                            continue
                        stream.write(chunk)
                        received += len(chunk)
                        if progress:
                            progress(received, total)
        except DownloadCancelled:
            part.unlink(missing_ok=True)
            raise
        except (httpx.HTTPError, OSError) as exc:
            part.unlink(missing_ok=True)
            raise NetworkError(f"download failed: {url} ({exc})") from exc
        part.replace(dest)
        return dest


class DownloadCancelled(RuntimeError):
    """Raised when the user cancels an in-flight download."""

"""Small HTTP wrapper for external data fetches."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
from time import sleep as default_sleep
from time import time as default_time
from typing import Any
from typing import Callable
from typing import Dict
from typing import Optional

import requests


class ConnectorError(RuntimeError):
    """Raised when a remote data source cannot be fetched or parsed."""


class HttpClient:
    """Simple requests-based client with browser-like headers."""

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        timeout_seconds: int = 20,
        max_retries: int = 2,
        backoff_seconds: float = 0.75,
        sleep_func: Optional[Callable[[float], None]] = None,
        cache_enabled: Optional[bool] = None,
        cache_dir: Optional[str] = None,
        cache_ttl_seconds: Optional[int] = None,
        now_func: Optional[Callable[[], float]] = None,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, int(max_retries))
        self.backoff_seconds = max(0.0, float(backoff_seconds))
        self.sleep_func = sleep_func or default_sleep
        self.now_func = now_func or default_time
        self.cache_enabled = _resolve_cache_enabled(cache_enabled)
        self.cache_dir = _resolve_cache_dir(cache_dir) if self.cache_enabled else None
        self.cache_ttl_seconds = _resolve_cache_ttl(cache_ttl_seconds)
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/134.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "*/*",
            }
        )

    def get_json(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        text = self.get_text(url, params=params, headers=headers)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ConnectorError("Expected JSON object from {url}".format(url=url)) from exc
        if not isinstance(payload, dict):
            raise ConnectorError("Expected JSON object from {url}".format(url=url))
        return payload

    def get_text(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> str:
        cache_entry = self._read_cache("GET", url, params=params, headers=headers)
        if self._is_cache_fresh(cache_entry):
            return str(cache_entry.get("text", ""))

        try:
            response = self._request("GET", url, params=params, headers=headers)
        except ConnectorError:
            if cache_entry is not None:
                return str(cache_entry.get("text", ""))
            raise

        try:
            _raise_for_bad_response(response, url)
        except ConnectorError:
            if cache_entry is not None and _is_retryable_status(response.status_code):
                return str(cache_entry.get("text", ""))
            raise

        self._write_cache(
            "GET",
            url,
            params=params,
            headers=headers,
            status_code=response.status_code,
            text=response.text,
        )
        return response.text

    def _request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> requests.Response:
        last_response: Optional[requests.Response] = None

        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.request(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            except requests.RequestException as exc:
                if attempt >= self.max_retries:
                    raise ConnectorError(
                        "Request failed for {url} after {attempts} attempt(s): {error}".format(
                            url=url,
                            attempts=attempt + 1,
                            error=str(exc),
                        )
                    ) from exc
                self._sleep_before_retry(attempt)
                continue

            last_response = response
            if not _is_retryable_status(response.status_code) or attempt >= self.max_retries:
                return response

            self._sleep_before_retry(attempt)

        if last_response is None:
            raise ConnectorError("Request failed for {url}: no response".format(url=url))
        return last_response

    def _sleep_before_retry(self, attempt: int) -> None:
        if self.backoff_seconds <= 0:
            return
        delay = self.backoff_seconds * (2**attempt)
        self.sleep_func(delay)

    def _read_cache(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not self.cache_enabled or self.cache_dir is None:
            return None
        path = self._cache_path(method, url, params=params, headers=headers)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _write_cache(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        status_code: int,
        text: str,
    ) -> None:
        if not self.cache_enabled or self.cache_dir is None:
            return

        path = self._cache_path(method, url, params=params, headers=headers)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "created_at_epoch": self.now_func(),
            "method": method,
            "url": url,
            "params": params or {},
            "headers": headers or {},
            "status_code": int(status_code),
            "text": text,
        }
        temp_path = path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        temp_path.replace(path)

    def _cache_path(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Path:
        assert self.cache_dir is not None
        signature = json.dumps(
            {
                "method": method,
                "url": url,
                "params": params or {},
                "headers": headers or {},
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        digest = sha256(signature.encode("utf-8")).hexdigest()
        return self.cache_dir / "{digest}.json".format(digest=digest)

    def _is_cache_fresh(self, entry: Optional[Dict[str, Any]]) -> bool:
        if entry is None:
            return False
        created_at = entry.get("created_at_epoch")
        if created_at is None:
            return False
        try:
            age_seconds = float(self.now_func()) - float(created_at)
        except (TypeError, ValueError):
            return False
        return age_seconds <= float(self.cache_ttl_seconds)


def _raise_for_bad_response(response: requests.Response, url: str) -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        snippet = response.text[:240].strip().replace("\n", " ")
        raise ConnectorError(
            "Request failed for {url}: {code} {reason} {snippet}".format(
                url=url,
                code=response.status_code,
                reason=response.reason,
                snippet=snippet,
            )
        ) from exc


def _is_retryable_status(status_code: int) -> bool:
    return status_code in {408, 425, 429, 500, 502, 503, 504}


def _resolve_cache_enabled(cache_enabled: Optional[bool]) -> bool:
    if cache_enabled is not None:
        return bool(cache_enabled)
    disabled = os.getenv("STOCK_REPORT_HTTP_CACHE_DISABLED", "").strip().lower()
    return disabled not in {"1", "true", "yes", "on"}


def _resolve_cache_dir(cache_dir: Optional[str]) -> Path:
    configured = cache_dir or os.getenv("STOCK_REPORT_HTTP_CACHE_DIR") or "data/raw/http_cache"
    return Path(configured)


def _resolve_cache_ttl(cache_ttl_seconds: Optional[int]) -> int:
    if cache_ttl_seconds is not None:
        return max(0, int(cache_ttl_seconds))
    configured = os.getenv("STOCK_REPORT_HTTP_CACHE_TTL_SECONDS", "21600")
    try:
        return max(0, int(configured))
    except ValueError:
        return 21600

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from stock_auto.csv_utils import write_bars_to_csv
from stock_auto.domain.models import Bar


def _normalize_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _format_rfc3339(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class AlpacaCredentials:
    api_key: str
    secret_key: str


class AlpacaHistoricalBarsClient:
    def __init__(
        self,
        credentials: AlpacaCredentials,
        *,
        base_url: str = "https://data.alpaca.markets/v2",
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        self.credentials = credentials
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

    def fetch_stock_bars(
        self,
        *,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str = "1Min",
        feed: str = "iex",
        adjustment: str = "split",
        limit: int = 10000,
    ) -> List[Bar]:
        endpoint = f"{self.base_url}/stocks/bars"
        page_token: Optional[str] = None
        collected: List[Bar] = []

        while True:
            query = {
                "symbols": symbol,
                "timeframe": timeframe,
                "start": _format_rfc3339(start),
                "end": _format_rfc3339(end),
                "limit": str(limit),
                "adjustment": adjustment,
                "feed": feed,
                "sort": "asc",
            }
            if page_token:
                query["page_token"] = page_token

            payload = self._request_json(endpoint, query)
            page_bars = payload.get("bars", {}).get(symbol, [])
            for item in page_bars:
                collected.append(
                    Bar(
                        symbol=symbol,
                        timestamp=_normalize_timestamp(item["t"]),
                        open=float(item["o"]),
                        high=float(item["h"]),
                        low=float(item["l"]),
                        close=float(item["c"]),
                        volume=float(item.get("v", 0.0)),
                    )
                )

            page_token = payload.get("next_page_token")
            if not page_token:
                break

        return collected

    def _request_json(self, endpoint: str, query: Dict[str, str]) -> Dict[str, object]:
        url = f"{endpoint}?{urlencode(query)}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "APCA-API-KEY-ID": self.credentials.api_key,
                "APCA-API-SECRET-KEY": self.credentials.secret_key,
            },
        )

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                should_retry = exc.code in {429, 500, 502, 503, 504} and attempt < self.max_retries
                last_error = exc
                if should_retry:
                    time.sleep(self.retry_delay_seconds * attempt)
                    continue
                message = exc.read().decode("utf-8", errors="ignore")
                raise RuntimeError(f"Alpaca request failed with HTTP {exc.code}: {message}") from exc
            except URLError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay_seconds * attempt)
                    continue
                raise RuntimeError(f"Alpaca request failed: {exc.reason}") from exc

        raise RuntimeError(f"Alpaca request failed after retries: {last_error}")  # pragma: no cover

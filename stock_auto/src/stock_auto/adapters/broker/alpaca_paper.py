from __future__ import annotations

import json
import time
from typing import Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from stock_auto.adapters.market_data.alpaca_historical import AlpacaCredentials


class AlpacaPaperTradingClient:
    def __init__(
        self,
        credentials: AlpacaCredentials,
        *,
        base_url: str = "https://paper-api.alpaca.markets/v2",
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        self.credentials = credentials
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

    def get_account(self) -> Dict[str, object]:
        return self._request_json("GET", "/account")

    def list_orders(
        self,
        *,
        status: str = "open",
        limit: int = 100,
        nested: bool = True,
        symbols: Optional[List[str]] = None,
    ) -> List[Dict[str, object]]:
        query = {
            "status": status,
            "limit": str(limit),
            "nested": "true" if nested else "false",
        }
        if symbols:
            query["symbols"] = ",".join(symbols)
        response = self._request_json("GET", "/orders", query=query)
        assert isinstance(response, list)
        return response

    def get_order(self, order_id: str, *, nested: bool = True) -> Dict[str, object]:
        return self._request_json(
            "GET",
            f"/orders/{order_id}",
            query={"nested": "true" if nested else "false"},
        )

    def list_positions(self) -> List[Dict[str, object]]:
        response = self._request_json("GET", "/positions")
        assert isinstance(response, list)
        return response

    def submit_order(self, payload: Dict[str, object]) -> Dict[str, object]:
        return self._request_json("POST", "/orders", payload=payload)

    def cancel_order(self, order_id: str) -> Optional[Dict[str, object]]:
        return self._request_json("DELETE", f"/orders/{order_id}")

    def cancel_all_orders(self) -> List[Dict[str, object]]:
        response = self._request_json("DELETE", "/orders")
        assert isinstance(response, list)
        return response

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        query: Optional[Dict[str, str]] = None,
        payload: Optional[Dict[str, object]] = None,
    ):
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"

        data = None
        headers = {
            "Accept": "application/json",
            "APCA-API-KEY-ID": self.credentials.api_key,
            "APCA-API-SECRET-KEY": self.credentials.secret_key,
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(url, data=data, headers=headers, method=method)

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    body = response.read().decode("utf-8")
                    return json.loads(body) if body else None
            except HTTPError as exc:
                should_retry = exc.code in {429, 500, 502, 503, 504} and attempt < self.max_retries
                last_error = exc
                if should_retry:
                    time.sleep(self.retry_delay_seconds * attempt)
                    continue
                message = exc.read().decode("utf-8", errors="ignore")
                raise RuntimeError(f"Alpaca paper request failed with HTTP {exc.code}: {message}") from exc
            except URLError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay_seconds * attempt)
                    continue
                raise RuntimeError(f"Alpaca paper request failed: {exc.reason}") from exc

        raise RuntimeError(f"Alpaca paper request failed after retries: {last_error}")  # pragma: no cover

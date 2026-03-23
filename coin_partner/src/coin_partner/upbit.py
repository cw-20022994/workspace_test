from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from coin_partner.models import Candle


logger = logging.getLogger(__name__)


class UpbitAPIError(RuntimeError):
    pass


@dataclass
class FillResult:
    market: str
    side: str
    volume: float
    average_price: float
    fee_krw: float
    order_id: Optional[str]
    raw: Dict[str, Any]


class UpbitClient:
    def __init__(
        self,
        base_url: str,
        timezone: str,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        timeout_seconds: int = 10,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.access_key = access_key
        self.secret_key = secret_key
        self.timeout_seconds = timeout_seconds
        self.tz = ZoneInfo(timezone)

    def get_minute_candles(self, market: str, unit: int, count: int = 200) -> List[Candle]:
        payload = self._request("GET", f"/candles/minutes/{unit}", params={"market": market, "count": count})
        candles: List[Candle] = []
        for row in reversed(payload):
            start_time = datetime.fromisoformat(row["candle_date_time_kst"]).replace(tzinfo=self.tz)
            candles.append(
                Candle(
                    market=market,
                    unit_minutes=unit,
                    start_time=start_time,
                    open_price=float(row["opening_price"]),
                    high_price=float(row["high_price"]),
                    low_price=float(row["low_price"]),
                    close_price=float(row["trade_price"]),
                    volume=float(row["candle_acc_trade_volume"]),
                    turnover=float(row["candle_acc_trade_price"]),
                )
            )
        return candles

    def get_tickers(self, markets: List[str]) -> Dict[str, float]:
        payload = self._request("GET", "/ticker", params={"markets": ",".join(markets)})
        return {row["market"]: float(row["trade_price"]) for row in payload}

    def get_accounts(self) -> List[Dict[str, Any]]:
        return self._request("GET", "/accounts", private=True)

    def get_krw_balance(self) -> float:
        for row in self.get_accounts():
            if row.get("currency") == "KRW":
                return float(row.get("balance", 0.0))
        return 0.0

    def create_market_buy(self, market: str, price_krw: float) -> FillResult:
        body = {
            "market": market,
            "side": "bid",
            "price": str(int(price_krw)),
            "ord_type": "price",
        }
        order = self._request("POST", "/orders", body=body, private=True)
        order_id = order.get("uuid")
        final_order = self._wait_for_order(order_id) if order_id else order
        return self._extract_fill(final_order, market, "bid")

    def create_market_sell(self, market: str, volume: float) -> FillResult:
        body = {
            "market": market,
            "side": "ask",
            "volume": f"{volume:.16f}".rstrip("0").rstrip("."),
            "ord_type": "market",
        }
        order = self._request("POST", "/orders", body=body, private=True)
        order_id = order.get("uuid")
        final_order = self._wait_for_order(order_id) if order_id else order
        return self._extract_fill(final_order, market, "ask")

    def get_order(self, order_id: str) -> Dict[str, Any]:
        return self._request("GET", "/order", params={"uuid": order_id}, private=True)

    def _wait_for_order(self, order_id: str, attempts: int = 5, delay_seconds: float = 0.4) -> Dict[str, Any]:
        last_payload: Optional[Dict[str, Any]] = None
        for _ in range(attempts):
            payload = self.get_order(order_id)
            last_payload = payload
            if payload.get("state") == "done":
                return payload
            time.sleep(delay_seconds)
        if last_payload is None:
            raise UpbitAPIError(f"order polling failed for {order_id}")
        return last_payload

    def _extract_fill(self, payload: Dict[str, Any], market: str, side: str) -> FillResult:
        executed_volume = float(payload.get("executed_volume") or 0.0)
        paid_fee = float(payload.get("paid_fee") or 0.0)
        trades = payload.get("trades") or []

        total_funds = 0.0
        for trade in trades:
            if trade.get("funds") is not None:
                total_funds += float(trade["funds"])
            elif trade.get("price") is not None and trade.get("volume") is not None:
                total_funds += float(trade["price"]) * float(trade["volume"])

        if total_funds == 0.0 and payload.get("price") is not None and executed_volume > 0:
            total_funds = float(payload["price"])

        average_price = total_funds / executed_volume if executed_volume > 0 and total_funds > 0 else float(payload.get("price") or 0.0)
        return FillResult(
            market=market,
            side=side,
            volume=executed_volume,
            average_price=average_price,
            fee_krw=paid_fee,
            order_id=payload.get("uuid"),
            raw=payload,
        )

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
        private: bool = False,
    ) -> Any:
        params = params or {}
        body = body or {}
        query_string = ""
        if method == "GET" and params:
            query_string = self._build_query_string(params)
            url = f"{self.base_url}{path}?{query_string}"
            body_bytes = None
        else:
            url = f"{self.base_url}{path}"
            body_bytes = json.dumps(body).encode("utf-8") if body else None
            query_string = self._build_query_string(body) if body else ""

        headers = {"Accept": "application/json"}
        if body_bytes is not None:
            headers["Content-Type"] = "application/json"
        if private:
            headers["Authorization"] = f"Bearer {self._create_jwt(query_string)}"

        request = Request(url, data=body_bytes, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise UpbitAPIError(f"HTTP {exc.code} {path}: {detail}") from exc
        except URLError as exc:
            raise UpbitAPIError(f"connection error for {path}: {exc}") from exc

    def _build_query_string(self, params: Dict[str, Any]) -> str:
        filtered = {key: value for key, value in params.items() if value is not None}
        return unquote(urlencode(filtered, doseq=True))

    def _create_jwt(self, query_string: str = "") -> str:
        if not self.access_key or not self.secret_key:
            raise UpbitAPIError("private API requires access_key and secret_key")
        payload = {"access_key": self.access_key, "nonce": str(uuid.uuid4())}
        if query_string:
            payload["query_hash"] = hashlib.sha512(query_string.encode("utf-8")).hexdigest()
            payload["query_hash_alg"] = "SHA512"
        return _hs512_jwt(payload, self.secret_key)


def _hs512_jwt(payload: Dict[str, Any], secret_key: str) -> str:
    header = {"alg": "HS512", "typ": "JWT"}
    header_encoded = _base64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_encoded = _base64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_encoded}.{payload_encoded}".encode("utf-8")
    signature = hmac.new(secret_key.encode("utf-8"), signing_input, hashlib.sha512).digest()
    return f"{header_encoded}.{payload_encoded}.{_base64url(signature)}"


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")

from __future__ import annotations

from datetime import datetime
from typing import Dict, List
from zoneinfo import ZoneInfo

from stock_auto.adapters.auth.kis_auth import KISAuthSession
from stock_auto.domain.models import Bar


class KISOverseasStockDataClient:
    MINUTE_CHART_ENDPOINT = "/uapi/overseas-price/v1/quotations/inquire-time-itemchartprice"
    MINUTE_CHART_TR_ID = "HHDFS76950200"
    PRICE_ENDPOINT = "/uapi/overseas-price/v1/quotations/price"
    PRICE_TR_ID = "HHDFS00000300"
    ASKING_PRICE_ENDPOINT = "/uapi/overseas-price/v1/quotations/inquire-asking-price"
    ASKING_PRICE_TR_ID = "HHDFS76200100"

    def __init__(self, auth_session: KISAuthSession) -> None:
        self.auth_session = auth_session

    def fetch_recent_minute_bars(
        self,
        *,
        symbol: str,
        quote_exchange_code: str = "NAS",
        interval_minutes: int = 1,
        max_records: int = 120,
        include_previous_day: bool = True,
        market_timezone: str = "America/New_York",
    ) -> List[Bar]:
        tz = ZoneInfo(market_timezone)
        collected: Dict[datetime, Bar] = {}
        next_flag = ""
        key_buffer = ""
        remaining = max_records

        while remaining > 0:
            record_count = min(120, remaining)
            response = self.auth_session.request(
                "GET",
                self.MINUTE_CHART_ENDPOINT,
                tr_id=self.MINUTE_CHART_TR_ID,
                params={
                    "AUTH": "",
                    "EXCD": quote_exchange_code,
                    "SYMB": symbol,
                    "NMIN": str(interval_minutes),
                    "PINC": "1" if include_previous_day else "0",
                    "NEXT": next_flag,
                    "NREC": str(record_count),
                    "FILL": "",
                    "KEYB": key_buffer,
                },
            )
            if not response.is_ok():
                raise RuntimeError(
                    f"KIS minute bars request failed: {response.error_code()} {response.error_message()}"
                )

            rows = response.body.get("output2") or []
            if not rows:
                break

            for row in rows:
                bar = self._parse_chart_row(symbol, row, tz)
                collected[bar.timestamp] = bar

            remaining = max_records - len(collected)
            meta = response.body.get("output1") or {}
            tr_cont = response.headers.get("tr_cont", "")
            more_flag = str(meta.get("more", "")).upper()
            if remaining <= 0 or (tr_cont not in ("M", "F") and more_flag not in ("Y", "M", "1")):
                break

            last_row = rows[-1]
            key_buffer = f"{last_row.get('kymd', '')}{last_row.get('khms', '')}"
            if not key_buffer.strip():
                break
            next_flag = "1"

        return sorted(collected.values(), key=lambda item: item.timestamp)

    def fetch_current_price(
        self,
        *,
        symbol: str,
        quote_exchange_code: str = "NAS",
    ) -> Dict[str, object]:
        response = self.auth_session.request(
            "GET",
            self.PRICE_ENDPOINT,
            tr_id=self.PRICE_TR_ID,
            params={
                "AUTH": "",
                "EXCD": quote_exchange_code,
                "SYMB": symbol,
            },
        )
        if not response.is_ok():
            raise RuntimeError(
                f"KIS current price request failed: {response.error_code()} {response.error_message()}"
            )
        return self._merge_outputs(response.body)

    def fetch_asking_price(
        self,
        *,
        symbol: str,
        quote_exchange_code: str = "NAS",
    ) -> Dict[str, object]:
        response = self.auth_session.request(
            "GET",
            self.ASKING_PRICE_ENDPOINT,
            tr_id=self.ASKING_PRICE_TR_ID,
            params={
                "AUTH": "",
                "EXCD": quote_exchange_code,
                "SYMB": symbol,
            },
        )
        if not response.is_ok():
            raise RuntimeError(
                f"KIS asking price request failed: {response.error_code()} {response.error_message()}"
            )
        return self._merge_outputs(response.body)

    def fetch_quote_snapshot(
        self,
        *,
        symbol: str,
        quote_exchange_code: str = "NAS",
    ) -> Dict[str, object]:
        price = self.fetch_current_price(symbol=symbol, quote_exchange_code=quote_exchange_code)
        book = self.fetch_asking_price(symbol=symbol, quote_exchange_code=quote_exchange_code)
        snapshot = dict(price)
        snapshot.update(book)
        snapshot["symbol"] = symbol
        snapshot["quote_exchange_code"] = quote_exchange_code
        return snapshot

    def _parse_chart_row(self, symbol: str, row: dict, market_tz: ZoneInfo) -> Bar:
        timestamp = datetime.strptime(
            f"{row['xymd']}{row['xhms']}",
            "%Y%m%d%H%M%S",
        ).replace(tzinfo=market_tz)
        return Bar(
            symbol=symbol,
            timestamp=timestamp,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["last"]),
            volume=float(row.get("evol", 0.0)),
        )

    def _merge_outputs(self, payload: Dict[str, object]) -> Dict[str, object]:
        merged: Dict[str, object] = {}
        for key in ("output", "output1", "output2", "output3"):
            value = payload.get(key)
            if isinstance(value, dict):
                merged.update(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        merged.update(item)
        return merged

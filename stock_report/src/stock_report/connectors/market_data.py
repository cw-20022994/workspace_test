"""Market data connectors for US and Korea daily price history."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from io import StringIO
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

from bs4 import BeautifulSoup

from stock_report.connectors.http import ConnectorError
from stock_report.connectors.http import HttpClient

STOOQ_DAILY_URL = "https://stooq.com/q/d/l/"
NAVER_DAILY_URL = "https://finance.naver.com/item/sise_day.naver"
YAHOO_CHART_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"


@dataclass(frozen=True)
class PriceBar:
    """Normalized daily OHLCV bar."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    adjclose: float
    volume: float


@dataclass(frozen=True)
class PriceHistory:
    """Price history plus source metadata."""

    symbol: str
    currency: str
    exchange_name: str
    instrument_type: str
    short_name: str
    regular_market_price: Optional[float]
    bars: List[PriceBar]


class YahooChartClient:
    """Fetch daily bars from Yahoo's chart endpoint."""

    def __init__(self, http_client: Optional[HttpClient] = None) -> None:
        self.http_client = http_client or HttpClient()

    def fetch_history(
        self,
        symbol: str,
        range_value: str = "1y",
        interval: str = "1d",
    ) -> PriceHistory:
        payload = self.http_client.get_json(
            YAHOO_CHART_URL.format(symbol=symbol),
            params={
                "range": range_value,
                "interval": interval,
                "includePrePost": "false",
                "events": "div,splits",
            },
        )

        chart = payload.get("chart", {})
        error = chart.get("error")
        if error:
            raise ConnectorError(
                "Yahoo chart error for {symbol}: {error}".format(
                    symbol=symbol, error=error
                )
            )

        results = chart.get("result") or []
        if not results:
            raise ConnectorError(
                "Yahoo chart returned no results for {symbol}".format(symbol=symbol)
            )

        result = results[0]
        meta = dict(result.get("meta") or {})
        timestamps = list(result.get("timestamp") or [])
        quote_sets = result.get("indicators", {}).get("quote", [])
        quote = quote_sets[0] if quote_sets else {}
        adjclose_sets = result.get("indicators", {}).get("adjclose", [])
        adjclose_values = adjclose_sets[0].get("adjclose", []) if adjclose_sets else []

        bars = []
        for index, raw_ts in enumerate(timestamps):
            close = _value_at(quote.get("close"), index)
            open_price = _value_at(quote.get("open"), index)
            high = _value_at(quote.get("high"), index)
            low = _value_at(quote.get("low"), index)
            volume = _value_at(quote.get("volume"), index)
            adjclose = _value_at(adjclose_values, index)

            if None in (close, open_price, high, low, volume):
                continue

            bars.append(
                PriceBar(
                    timestamp=datetime.fromtimestamp(int(raw_ts), tz=timezone.utc),
                    open=float(open_price),
                    high=float(high),
                    low=float(low),
                    close=float(close),
                    adjclose=float(adjclose if adjclose is not None else close),
                    volume=float(volume),
                )
            )

        if not bars:
            raise ConnectorError(
                "Yahoo chart returned no usable bars for {symbol}".format(symbol=symbol)
            )

        return PriceHistory(
            symbol=str(meta.get("symbol", symbol)),
            currency=str(meta.get("currency", "USD")),
            exchange_name=str(meta.get("exchangeName", "unknown")),
            instrument_type=str(meta.get("instrumentType", "UNKNOWN")),
            short_name=str(meta.get("shortName") or meta.get("longName") or symbol),
            regular_market_price=_safe_float(meta.get("regularMarketPrice")),
            bars=bars,
        )


def _value_at(values: Any, index: int) -> Optional[float]:
    if not isinstance(values, list) or index >= len(values):
        return None
    return _safe_float(values[index])


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


class StooqUsChartClient:
    """Fetch US daily bars from Stooq CSV endpoints."""

    def __init__(self, http_client: Optional[HttpClient] = None) -> None:
        self.http_client = http_client or HttpClient()

    def fetch_history(self, symbol: str, range_value: str = "1y") -> PriceHistory:
        stooq_symbol = _to_stooq_symbol(symbol)
        text = self.http_client.get_text(
            STOOQ_DAILY_URL,
            params={"s": stooq_symbol, "i": "d"},
        )
        if text.strip().lower().startswith("no data"):
            raise ConnectorError("Stooq returned no data for {symbol}".format(symbol=symbol))

        reader = csv.DictReader(StringIO(text))
        bars = []
        for row in reader:
            try:
                timestamp = datetime.strptime(row["Date"], "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
                close = float(row["Close"])
                bars.append(
                    PriceBar(
                        timestamp=timestamp,
                        open=float(row["Open"]),
                        high=float(row["High"]),
                        low=float(row["Low"]),
                        close=close,
                        adjclose=close,
                        volume=float(row["Volume"]),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue

        if not bars:
            raise ConnectorError("Stooq returned no usable rows for {symbol}".format(symbol=symbol))

        bars = bars[-_target_bars_for_range(range_value) :]
        return PriceHistory(
            symbol=symbol,
            currency="USD",
            exchange_name="US",
            instrument_type="UNKNOWN",
            short_name=symbol,
            regular_market_price=bars[-1].close,
            bars=bars,
        )


class NaverKoreaChartClient:
    """Fetch Korea daily bars from Naver Finance pages."""

    def __init__(self, http_client: Optional[HttpClient] = None) -> None:
        self.http_client = http_client or HttpClient()

    def fetch_history(self, symbol: str, range_value: str = "1y") -> PriceHistory:
        code = symbol.split(".", 1)[0]
        target_bars = _target_bars_for_range(range_value)
        max_pages = max(1, int(target_bars / 10) + 3)
        rows = []

        headers = {
            "Referer": "https://finance.naver.com/item/main.naver?code={code}".format(
                code=code
            )
        }
        for page in range(1, max_pages + 1):
            html = self.http_client.get_text(
                NAVER_DAILY_URL,
                params={"code": code, "page": page},
                headers=headers,
            )
            parsed_rows = _parse_naver_daily_rows(html)
            if not parsed_rows:
                break
            rows.extend(parsed_rows)

        if not rows:
            raise ConnectorError("Naver returned no usable rows for {symbol}".format(symbol=symbol))

        deduped = {}
        for bar in rows:
            deduped[bar.timestamp] = bar
        rows = [deduped[key] for key in sorted(deduped)]
        rows = rows[-target_bars:]
        return PriceHistory(
            symbol=symbol,
            currency="KRW",
            exchange_name="KRX",
            instrument_type="EQUITY",
            short_name=symbol,
            regular_market_price=rows[-1].close,
            bars=rows,
        )


class MarketDataClient:
    """Choose a market data source based on symbol format."""

    def __init__(
        self,
        us_client: Optional[StooqUsChartClient] = None,
        us_fallback_client: Optional[YahooChartClient] = None,
        korea_client: Optional[NaverKoreaChartClient] = None,
    ) -> None:
        self.us_client = us_client or StooqUsChartClient()
        self.us_fallback_client = us_fallback_client or YahooChartClient()
        self.korea_client = korea_client or NaverKoreaChartClient()

    def fetch_history(self, symbol: str, range_value: str = "1y") -> PriceHistory:
        if symbol.upper().endswith(".KS"):
            return self.korea_client.fetch_history(symbol, range_value=range_value)
        try:
            return self.us_client.fetch_history(symbol, range_value=range_value)
        except ConnectorError as primary_error:
            try:
                return self.us_fallback_client.fetch_history(
                    symbol,
                    range_value=range_value,
                )
            except ConnectorError as fallback_error:
                raise ConnectorError(
                    "US market data failed for {symbol}. Primary source error: {primary}. "
                    "Fallback source error: {fallback}".format(
                        symbol=symbol,
                        primary=str(primary_error),
                        fallback=str(fallback_error),
                    )
                ) from fallback_error


def _to_stooq_symbol(symbol: str) -> str:
    if "." in symbol:
        return symbol.lower()
    return "{symbol}.us".format(symbol=symbol.lower())


def _target_bars_for_range(range_value: str) -> int:
    mapping = {
        "3mo": 66,
        "6mo": 132,
        "1y": 260,
        "2y": 520,
        "5y": 1300,
        "max": 5000,
    }
    return mapping.get(range_value, 260)


def _parse_naver_daily_rows(html: str) -> List[PriceBar]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="type2")
    if table is None:
        return []

    rows = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(cells) != 7:
            continue
        if "." not in cells[0]:
            continue
        try:
            timestamp = datetime.strptime(cells[0], "%Y.%m.%d").replace(
                tzinfo=timezone.utc
            )
            close = float(cells[1].replace(",", ""))
            open_price = float(cells[3].replace(",", ""))
            high = float(cells[4].replace(",", ""))
            low = float(cells[5].replace(",", ""))
            volume = float(cells[6].replace(",", ""))
        except ValueError:
            continue

        rows.append(
            PriceBar(
                timestamp=timestamp,
                open=open_price,
                high=high,
                low=low,
                close=close,
                adjclose=close,
                volume=volume,
            )
        )
    return rows

"""ETF overview and holdings connectors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from datetime import datetime
from datetime import timezone
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
import re

from bs4 import BeautifulSoup

from stock_report.connectors.http import ConnectorError
from stock_report.connectors.http import HttpClient

STOCKANALYSIS_ETF_URL = "https://stockanalysis.com/etf/{symbol}/"


@dataclass(frozen=True)
class EtfSnapshot:
    """Normalized ETF metadata and holdings summary."""

    metrics: Dict[str, Any]
    as_of: Optional[str]
    age_days: Optional[int]
    source: str


class StockAnalysisEtfClient:
    """Fetch ETF overview data from StockAnalysis ETF pages."""

    def __init__(self, http_client: Optional[HttpClient] = None) -> None:
        self.http_client = http_client or HttpClient()

    def fetch_etf(self, symbol: str) -> EtfSnapshot:
        html = self.http_client.get_text(STOCKANALYSIS_ETF_URL.format(symbol=symbol.lower()))
        soup = BeautifulSoup(html, "html.parser")

        metrics = _drop_none(
            {
                "asset_class": _extract_label_value(soup, "Asset Class"),
                "category": _extract_label_value(soup, "Category"),
                "region": _extract_label_value(soup, "Region"),
                "provider": _extract_label_value(soup, "ETF Provider") or _extract_provider_from_jsonld(html),
                "index_tracked": _extract_label_value(soup, "Index Tracked"),
                "expense_ratio": _parse_percent(_extract_js_string(html, "expenseRatio")),
                "aum": _parse_money_to_number(_extract_js_string(html, "aum")),
                "pe_ratio": _parse_float(_extract_js_string(html, "peRatio")),
                "dividend_yield": _parse_percent(_extract_js_string(html, "dividendYield")),
                "beta": _parse_float(_extract_js_string(html, "beta")),
                "holdings_count": _extract_js_int(html, "holdings"),
                "inception": _extract_js_string(html, "inception"),
            }
        )

        top_holdings, top_10_weight = _extract_top_holdings(soup)
        if top_holdings:
            metrics["top_holdings"] = top_holdings
        if top_10_weight is not None:
            metrics["top_10_weight"] = top_10_weight
        if not metrics:
            raise ConnectorError(
                "StockAnalysis ETF page did not expose recognizable ETF metrics for {symbol}.".format(
                    symbol=symbol
                )
            )

        as_of = _extract_updated_date(html)

        return EtfSnapshot(
            metrics=metrics,
            as_of=as_of,
            age_days=_age_days_from_iso(as_of),
            source="StockAnalysis ETF",
        )


class EtfDataClient:
    """ETF data client wrapper."""

    def __init__(
        self,
        stockanalysis_client: Optional[StockAnalysisEtfClient] = None,
    ) -> None:
        self.stockanalysis_client = stockanalysis_client or StockAnalysisEtfClient()

    def fetch_etf(self, symbol: str) -> EtfSnapshot:
        return self.stockanalysis_client.fetch_etf(symbol)


def _extract_label_value(soup: BeautifulSoup, label: str) -> Optional[str]:
    node = soup.find("span", string=re.compile(r"^{label}$".format(label=re.escape(label))))
    if node is None:
        return None
    parent = node.parent
    if parent is None:
        return None

    values = []
    for child in parent.find_all(["span", "a"], recursive=False):
        text = child.get_text(" ", strip=True)
        if not text or text == label:
            continue
        values.append(text)

    if values:
        return values[0]
    return None


def _extract_provider_from_jsonld(html: str) -> Optional[str]:
    match = re.search(r'"provider":\{"@type":"Organization","name":"([^"]+)"\}', html)
    if not match:
        return None
    return match.group(1)


def _extract_js_string(html: str, key: str) -> Optional[str]:
    match = re.search(r'{key}:"([^"]+)"'.format(key=re.escape(key)), html)
    if not match:
        return None
    return match.group(1)


def _extract_js_int(html: str, key: str) -> Optional[int]:
    match = re.search(r'{key}:(\d+)'.format(key=re.escape(key)), html)
    if not match:
        return None
    return int(match.group(1))


def _extract_top_holdings(
    soup: BeautifulSoup,
) -> tuple[List[Dict[str, Any]], Optional[float]]:
    heading = soup.find(["h2", "h3"], string=re.compile(r"Top 10 Holdings", re.IGNORECASE))
    if heading is None:
        return [], None

    header_block = heading.parent
    top_weight = None
    if header_block is not None:
        text = header_block.get_text(" ", strip=True)
        match = re.search(r"(\d+(?:\.\d+)?)%\s+of assets", text)
        if match:
            top_weight = float(match.group(1))

    table = heading.find_parent("div")
    if table is not None:
        table = table.find("table")
    if table is None:
        table = heading.find_next("table")
    if table is None:
        return [], top_weight

    holdings = []
    for row in table.select("tbody tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        name = cells[0].get_text(" ", strip=True)
        symbol = cells[1].get_text(" ", strip=True)
        weight = _parse_percent(cells[2].get_text(" ", strip=True))
        holdings.append(
            _drop_none(
                {
                    "name": name,
                    "symbol": symbol,
                    "weight": weight,
                }
            )
        )

    return holdings[:10], top_weight


def _extract_updated_date(html: str) -> Optional[str]:
    match = re.search(r"Updated ([A-Z][a-z]+ \d{1,2}, \d{4})", html)
    if not match:
        return None
    parsed = _parse_us_date(match.group(1))
    if parsed is None:
        return None
    return parsed.isoformat()


def _parse_percent(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    cleaned = value.replace("%", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_float(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    cleaned = value.replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_money_to_number(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    cleaned = value.replace("$", "").replace(",", "").strip()
    suffixes = {
        "T": 1_000_000_000_000.0,
        "B": 1_000_000_000.0,
        "M": 1_000_000.0,
        "K": 1_000.0,
    }
    suffix = cleaned[-1]
    multiplier = suffixes.get(suffix, 1.0)
    if multiplier != 1.0:
        cleaned = cleaned[:-1]
    try:
        return float(cleaned) * multiplier
    except ValueError:
        return None


def _parse_us_date(value: str) -> Optional[date]:
    for pattern in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    return None


def _age_days_from_iso(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    try:
        as_of = datetime.fromisoformat(value).date()
    except ValueError:
        return None
    return (datetime.now(timezone.utc).date() - as_of).days


def _drop_none(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}

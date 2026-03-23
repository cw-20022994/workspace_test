"""Fundamentals connectors for US and Korea equities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from datetime import datetime
from datetime import timezone
import re
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

from bs4 import BeautifulSoup

from stock_report.connectors.http import ConnectorError
from stock_report.connectors.http import HttpClient
from stock_report.models import AssetDefinition

NAVER_MAIN_URL = "https://finance.naver.com/item/main.naver"
STOCKANALYSIS_FINANCIALS_URL = "https://stockanalysis.com/stocks/{symbol}/financials/"
STOCKANALYSIS_RATIOS_URL = "https://stockanalysis.com/stocks/{symbol}/financials/ratios/"


@dataclass(frozen=True)
class FundamentalsSnapshot:
    """Normalized fundamentals payload plus freshness metadata."""

    metrics: Dict[str, Any]
    as_of: Optional[str]
    age_days: Optional[int]
    source: str


class StockAnalysisFundamentalsClient:
    """Fetch US equity fundamentals from StockAnalysis pages."""

    def __init__(self, http_client: Optional[HttpClient] = None) -> None:
        self.http_client = http_client or HttpClient()

    def fetch_fundamentals(self, symbol: str) -> FundamentalsSnapshot:
        slug = _to_stockanalysis_symbol(symbol)
        financials_html = self.http_client.get_text(
            STOCKANALYSIS_FINANCIALS_URL.format(symbol=slug)
        )
        ratios_html = self.http_client.get_text(
            STOCKANALYSIS_RATIOS_URL.format(symbol=slug)
        )

        financials_block = _extract_stockanalysis_block(financials_html)
        ratios_block = _extract_stockanalysis_block(ratios_html)

        metrics = _drop_none(
            {
                "revenue_growth": _to_percent(
                    _extract_stockanalysis_first_number(financials_block, "revenueGrowth")
                ),
                "earnings_growth": _to_percent(
                    _extract_stockanalysis_first_number(financials_block, "netIncomeGrowth")
                ),
                "gross_margin": _to_percent(
                    _extract_stockanalysis_first_number(financials_block, "grossMargin")
                ),
                "operating_margin": _to_percent(
                    _extract_stockanalysis_first_number(financials_block, "operatingMargin")
                ),
                "forward_pe": _extract_stockanalysis_first_number(
                    ratios_block, "peForward"
                ),
                "ev_to_sales": _extract_stockanalysis_first_number(
                    ratios_block, "evrevenue"
                ),
                "net_debt_to_ebitda": _extract_stockanalysis_first_number(
                    ratios_block, "netdebtebitda"
                ),
                "current_ratio": _extract_stockanalysis_first_number(
                    ratios_block, "currentratio"
                ),
                "roe": _to_percent(
                    _extract_stockanalysis_first_number(ratios_block, "roe")
                ),
                "market_cap": _extract_stockanalysis_first_number(
                    ratios_block, "marketCap"
                ),
            }
        )

        as_of = _extract_stockanalysis_as_of(ratios_html) or _extract_stockanalysis_as_of(
            financials_html
        )
        return FundamentalsSnapshot(
            metrics=metrics,
            as_of=as_of,
            age_days=_age_days_from_iso(as_of),
            source="StockAnalysis",
        )


class NaverKoreaFundamentalsClient:
    """Fetch Korea equity fundamentals from Naver Finance."""

    def __init__(self, http_client: Optional[HttpClient] = None) -> None:
        self.http_client = http_client or HttpClient()

    def fetch_fundamentals(self, symbol: str) -> FundamentalsSnapshot:
        code = symbol.split(".", 1)[0]
        html = self.http_client.get_text(
            NAVER_MAIN_URL,
            params={"code": code},
            headers={
                "Referer": "https://finance.naver.com/item/main.naver?code={code}".format(
                    code=code
                )
            },
        )
        soup = BeautifulSoup(html, "html.parser")
        annual_headers, rows = _parse_naver_financial_table(soup)
        valuation_metrics = _parse_naver_valuation_box(soup)

        metrics = _drop_none(
            {
                "revenue_growth": _growth_from_series(rows.get("매출액", [])),
                "earnings_growth": _growth_from_series(rows.get("당기순이익", [])),
                "operating_margin": _latest_actual_value(rows.get("영업이익률", [])),
                "roe": _latest_actual_value(rows.get("ROE(지배주주)", [])),
                "quick_ratio": _ratio_percent_to_multiple(
                    _latest_actual_value(rows.get("당좌비율", []))
                ),
                "debt_ratio": _latest_actual_value(rows.get("부채비율", [])),
                "eps": valuation_metrics.get("eps"),
                "pbr": valuation_metrics.get("pbr"),
                "forward_pe": valuation_metrics.get("forward_pe"),
            }
        )

        as_of = _period_to_iso(_latest_actual_period(annual_headers))
        return FundamentalsSnapshot(
            metrics=metrics,
            as_of=as_of,
            age_days=_age_days_from_iso(as_of),
            source="Naver Finance",
        )


class FundamentalsClient:
    """Choose a fundamentals source based on asset metadata."""

    def __init__(
        self,
        us_client: Optional[StockAnalysisFundamentalsClient] = None,
        korea_client: Optional[NaverKoreaFundamentalsClient] = None,
    ) -> None:
        self.us_client = us_client or StockAnalysisFundamentalsClient()
        self.korea_client = korea_client or NaverKoreaFundamentalsClient()

    def fetch_fundamentals(self, asset: AssetDefinition) -> FundamentalsSnapshot:
        if asset.asset_type != "stock":
            return FundamentalsSnapshot(metrics={}, as_of=None, age_days=None, source="n/a")
        if asset.symbol.upper().endswith(".KS") or asset.market.upper() == "KR":
            return self.korea_client.fetch_fundamentals(asset.symbol)
        return self.us_client.fetch_fundamentals(asset.symbol)


def _extract_stockanalysis_block(html: str) -> str:
    match = re.search(r"financialData:\{(.*?)\},map:\[", html, flags=re.DOTALL)
    if not match:
        raise ConnectorError("StockAnalysis financialData block was not found.")
    return match.group(1)


def _extract_stockanalysis_first_number(block: str, key: str) -> Optional[float]:
    match = re.search(
        r"{key}:\[(.*?)\](?:,|$)".format(key=re.escape(key)),
        block,
        flags=re.DOTALL,
    )
    if not match:
        return None

    tokens = [token.strip() for token in match.group(1).split(",")]
    for token in tokens:
        value = _parse_js_scalar(token)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _extract_stockanalysis_as_of(html: str) -> Optional[str]:
    match = re.search(r'lastTrailingDate:"([^"]+)"', html)
    if match:
        parsed = _parse_us_date(match.group(1))
        if parsed is not None:
            return parsed.isoformat()

    match = re.search(r'sourceText:"Updated ([A-Z][a-z]{2} \d{1,2}, \d{4})\.', html)
    if not match:
        return None
    parsed = _parse_us_date(match.group(1))
    if parsed is None:
        return None
    return parsed.isoformat()


def _parse_us_date(value: str) -> Optional[date]:
    for pattern in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    return None


def _parse_naver_financial_table(
    soup: BeautifulSoup,
) -> tuple[List[str], Dict[str, List[Optional[float]]]]:
    table = soup.find(
        "table",
        attrs={
            "summary": re.compile("기업실적분석", flags=re.IGNORECASE),
        },
    )
    if table is None:
        raise ConnectorError("Naver financial summary table was not found.")

    header_rows = table.select("thead tr")
    if len(header_rows) < 2:
        raise ConnectorError("Naver financial summary header is incomplete.")

    annual_headers = [
        _normalize_whitespace(th.get_text(" ", strip=True))
        for th in header_rows[1].find_all("th")[:4]
    ]

    row_values: Dict[str, List[Optional[float]]] = {}
    for tr in table.select("tbody tr"):
        header = tr.find("th")
        if header is None:
            continue
        label = _normalize_whitespace(header.get_text(" ", strip=True))
        cells = tr.find_all("td")
        if len(cells) < 4:
            continue
        row_values[label] = [_parse_numeric_cell(td.get_text(" ", strip=True)) for td in cells[:4]]

    return annual_headers, row_values


def _parse_naver_valuation_box(soup: BeautifulSoup) -> Dict[str, Optional[float]]:
    def _text(selector: str) -> Optional[float]:
        node = soup.select_one(selector)
        if node is None:
            return None
        return _parse_numeric_cell(node.get_text(" ", strip=True))

    return {
        "forward_pe": _text("#_cns_per") or _text("#_per"),
        "eps": _text("#_eps"),
        "pbr": _text("#_pbr"),
    }


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def _parse_numeric_cell(value: str) -> Optional[float]:
    text = value.strip()
    if not text or text == "&nbsp;":
        return None
    text = text.replace(",", "")
    text = text.replace("(E)", "")
    if text in {"-", "N/A", "n/a"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_js_scalar(token: str) -> Optional[Any]:
    cleaned = token.strip()
    if cleaned in {"", "null", "void 0", "undefined"}:
        return None
    if cleaned == "true":
        return True
    if cleaned == "false":
        return False
    if cleaned.startswith('"') and cleaned.endswith('"'):
        return cleaned[1:-1]
    try:
        return float(cleaned)
    except ValueError:
        return None


def _to_stockanalysis_symbol(symbol: str) -> str:
    return symbol.lower().replace(".", "-")


def _to_percent(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(value * 100.0, 2)


def _ratio_percent_to_multiple(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(value / 100.0, 4)


def _latest_actual_period(headers: List[str]) -> Optional[str]:
    if len(headers) < 3:
        return None
    return headers[2]


def _latest_actual_value(values: List[Optional[float]]) -> Optional[float]:
    if len(values) < 3:
        return None
    return values[2]


def _growth_from_series(values: List[Optional[float]]) -> Optional[float]:
    if len(values) < 3:
        return None
    latest = values[2]
    previous = values[1]
    if latest is None or previous in (None, 0):
        return None
    return round(((latest / previous) - 1.0) * 100.0, 2)


def _period_to_iso(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    match = re.search(r"(\d{4})\.(\d{2})", value)
    if not match:
        return None
    year = int(match.group(1))
    month = int(match.group(2))
    if month == 12:
        day = 31
    elif month in {1, 3, 5, 7, 8, 10}:
        day = 31
    elif month in {4, 6, 9, 11}:
        day = 30
    else:
        leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        day = 29 if leap else 28
    return date(year, month, day).isoformat()


def _age_days_from_iso(as_of: Optional[str]) -> Optional[int]:
    if not as_of:
        return None
    try:
        parsed = datetime.fromisoformat(as_of)
    except ValueError:
        try:
            parsed = datetime.strptime(as_of, "%Y-%m-%d")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return (now.date() - parsed.date()).days


def _drop_none(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}

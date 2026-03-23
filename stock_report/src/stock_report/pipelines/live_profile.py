"""Build a live analysis profile from fetched market data and news."""

from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone
from math import sqrt
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

from stock_report.connectors.etf_data import EtfDataClient
from stock_report.connectors.etf_data import EtfSnapshot
from stock_report.connectors.fundamentals import FundamentalsClient
from stock_report.connectors.fundamentals import FundamentalsSnapshot
from stock_report.connectors.http import ConnectorError
from stock_report.connectors.market_data import PriceBar
from stock_report.connectors.market_data import PriceHistory
from stock_report.connectors.market_data import MarketDataClient
from stock_report.connectors.news import GoogleNewsClient
from stock_report.models import AnalysisInput
from stock_report.models import AssetDefinition
from stock_report.models import NewsItem
from stock_report.models import Watchlist

HBF_THEMES = {"hbf_memory_storage", "korea_hbm_hbf"}


class LiveAnalysisBuilder:
    """Fetch live inputs and convert them into AnalysisInput."""

    def __init__(
        self,
        market_data_client: Optional[MarketDataClient] = None,
        news_client: Optional[GoogleNewsClient] = None,
        fundamentals_client: Optional[FundamentalsClient] = None,
        etf_client: Optional[EtfDataClient] = None,
    ) -> None:
        self.market_data_client = market_data_client or MarketDataClient()
        self.news_client = news_client or GoogleNewsClient()
        self.fundamentals_client = fundamentals_client or FundamentalsClient()
        self.etf_client = etf_client or EtfDataClient()
        self._history_cache: Dict[tuple[str, str], PriceHistory] = {}
        self._fundamentals_cache: Dict[str, FundamentalsSnapshot] = {}
        self._etf_cache: Dict[str, EtfSnapshot] = {}

    def build(
        self,
        watchlist: Watchlist,
        asset: AssetDefinition,
        benchmark_symbol: Optional[str] = None,
        history_range: str = "1y",
        news_days: int = 7,
        max_news_items: Optional[int] = None,
    ) -> AnalysisInput:
        benchmark = benchmark_symbol or str(watchlist.defaults.get("benchmark_symbol", "SPY"))
        asset_history = self._fetch_history(asset.symbol, range_value=history_range)
        benchmark_history = self._fetch_history(benchmark, range_value=history_range)
        limit = max_news_items or int(watchlist.reporting.get("max_news_items", 5))
        news_items = self.news_client.fetch_news(asset, days=news_days, limit=limit)
        fundamentals_snapshot = self._fetch_fundamentals(asset)
        etf_snapshot = self._fetch_etf(asset)

        prices = _build_price_metrics(asset_history, benchmark_history)
        freshness = _build_freshness(
            asset_history,
            news_items,
            news_days,
            fundamentals_snapshot,
            etf_snapshot,
        )
        theme_signals = _build_theme_signals(asset, news_items)
        etf = _build_etf_metrics(asset, etf_snapshot)
        risk_flags = _build_risk_flags(asset, prices, news_items, theme_signals, etf)

        return AnalysisInput(
            asset_type=asset.asset_type,
            report_time_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            benchmark_symbol=benchmark,
            prices=prices,
            fundamentals=fundamentals_snapshot.metrics,
            etf=etf,
            news=news_items,
            risk_flags=risk_flags,
            freshness=freshness,
            theme_signals=theme_signals,
            notes=(
                "Live profile generated from Stooq or Naver market data, Google News RSS, "
                "fundamentals from StockAnalysis or Naver Finance when available, "
                "and ETF overview or top-holdings data from StockAnalysis ETF pages when available."
            ),
        )

    def _fetch_history(
        self,
        symbol: str,
        range_value: str,
    ) -> PriceHistory:
        key = (symbol.upper(), range_value)
        cached = self._history_cache.get(key)
        if cached is not None:
            return cached
        history = self.market_data_client.fetch_history(
            symbol,
            range_value=range_value,
        )
        self._history_cache[key] = history
        return history

    def _fetch_fundamentals(self, asset: AssetDefinition) -> FundamentalsSnapshot:
        key = asset.symbol.upper()
        cached = self._fundamentals_cache.get(key)
        if cached is not None:
            return cached
        snapshot = _fetch_fundamentals_safe(self.fundamentals_client, asset)
        self._fundamentals_cache[key] = snapshot
        return snapshot

    def _fetch_etf(self, asset: AssetDefinition) -> EtfSnapshot:
        key = asset.symbol.upper()
        cached = self._etf_cache.get(key)
        if cached is not None:
            return cached
        snapshot = _fetch_etf_safe(self.etf_client, asset)
        self._etf_cache[key] = snapshot
        return snapshot


def _build_price_metrics(
    asset_history: PriceHistory,
    benchmark_history: PriceHistory,
) -> Dict[str, Any]:
    closes = [bar.adjclose for bar in asset_history.bars]
    benchmark_closes = [bar.adjclose for bar in benchmark_history.bars]

    latest_price = closes[-1]
    metrics = {
        "currency": asset_history.currency,
        "exchange_name": asset_history.exchange_name,
        "instrument_type": asset_history.instrument_type,
        "latest_price": round(latest_price, 4),
        "return_5d": _calc_return(closes, 5),
        "return_20d": _calc_return(closes, 20),
        "return_60d": _calc_return(closes, 60),
        "return_252d": _calc_return(closes, 252),
        "rs_20d": _relative_strength(closes, benchmark_closes, 20),
        "rs_60d": _relative_strength(closes, benchmark_closes, 60),
        "price_vs_ma20": _price_vs_ma(closes, 20),
        "price_vs_ma50": _price_vs_ma(closes, 50),
        "price_vs_ma200": _price_vs_ma(closes, 200),
        "drawdown": _drawdown(closes),
        "volatility": _annualized_volatility(closes),
    }
    return metrics


def _build_freshness(
    asset_history: PriceHistory,
    news_items: List[NewsItem],
    news_days: int,
    fundamentals_snapshot: FundamentalsSnapshot,
    etf_snapshot: EtfSnapshot,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    last_bar = asset_history.bars[-1].timestamp.astimezone(timezone.utc)
    newest_news = _newest_news_datetime(news_items)
    start_date = now.date() - timedelta(days=news_days)

    freshness = {
        "price_data_as_of": last_bar.date().isoformat(),
        "price_data_age_days": (now.date() - last_bar.date()).days,
        "fundamentals_data_as_of": fundamentals_snapshot.as_of or "n/a",
        "fundamentals_data_age_days": fundamentals_snapshot.age_days,
        "etf_data_as_of": etf_snapshot.as_of or "n/a",
        "etf_data_age_days": etf_snapshot.age_days,
        "news_window": "{start} to {end}".format(
            start=start_date.isoformat(),
            end=(now.date()).isoformat(),
        ),
        "news_data_age_days": news_days if newest_news is None else (now.date() - newest_news.date()).days,
    }
    if newest_news is not None:
        freshness["news_window"] = "{start} to {end}".format(
            start=start_date.isoformat(),
            end=now.date().isoformat(),
        )
    return freshness


def _fetch_fundamentals_safe(
    fundamentals_client: FundamentalsClient,
    asset: AssetDefinition,
) -> FundamentalsSnapshot:
    try:
        return fundamentals_client.fetch_fundamentals(asset)
    except ConnectorError:
        return FundamentalsSnapshot(metrics={}, as_of=None, age_days=None, source="unavailable")


def _fetch_etf_safe(
    etf_client: EtfDataClient,
    asset: AssetDefinition,
) -> EtfSnapshot:
    if asset.asset_type != "etf":
        return EtfSnapshot(metrics={}, as_of=None, age_days=None, source="n/a")
    try:
        return etf_client.fetch_etf(asset.symbol)
    except ConnectorError:
        return EtfSnapshot(metrics={}, as_of=None, age_days=None, source="unavailable")


def _newest_news_datetime(news_items: List[NewsItem]) -> Optional[datetime]:
    parsed = []
    for item in news_items:
        try:
            parsed.append(datetime.fromisoformat(item.published_at))
        except ValueError:
            continue
    if not parsed:
        return None
    return max(parsed)


def _build_theme_signals(asset: AssetDefinition, news_items: List[NewsItem]) -> Dict[str, Any]:
    if asset.theme not in HBF_THEMES:
        return {}

    titles = [item.headline.lower() for item in news_items]
    sources = {item.source for item in news_items if item.source}

    standardization_progress = any(
        keyword in title
        for title in titles
        for keyword in ("standardization", "interoperability", "jedec", "consortium")
    )
    ecosystem_partners = sum(
        1
        for title in titles
        if any(keyword in title for keyword in ("partner", "partnership", "collaboration", "ecosystem"))
    )
    ai_inference_mentions = sum(
        1 for title in titles if "inference" in title or "ai" in title
    )
    commercial_sampling = any(
        keyword in title
        for title in titles
        for keyword in ("sample", "sampling", "qualification")
    )
    shipment_evidence = any(
        keyword in title
        for title in titles
        for keyword in ("shipment", "shipments", "ramp", "production", "volume")
    )
    concept_only_news_count = sum(
        1
        for title in titles
        if ("hbf" in title or "high bandwidth flash" in title)
        and not any(
            keyword in title
            for keyword in (
                "standardization",
                "interoperability",
                "partner",
                "sampling",
                "shipment",
                "production",
                "ramp",
            )
        )
    )

    return {
        "standardization_progress": standardization_progress,
        "ecosystem_partners": ecosystem_partners,
        "ai_inference_mentions": ai_inference_mentions,
        "commercial_sampling": commercial_sampling,
        "shipment_evidence": shipment_evidence,
        "concept_only_news_count": concept_only_news_count,
        "single_source_hype": bool(news_items) and len(sources) <= 1,
    }


def _build_risk_flags(
    asset: AssetDefinition,
    prices: Dict[str, Any],
    news_items: List[NewsItem],
    theme_signals: Dict[str, Any],
    etf_metrics: Dict[str, Any],
) -> List[str]:
    flags = []
    if prices.get("volatility") is not None and float(prices["volatility"]) >= 40.0:
        flags.append("Elevated realized volatility relative to a typical large-cap profile.")
    if prices.get("drawdown") is not None and float(prices["drawdown"]) <= -20.0:
        flags.append("The asset remains in a deep drawdown from its recent high.")
    if len(news_items) < 3:
        flags.append("Recent headline coverage is sparse, so the narrative may be incomplete.")
    if asset.theme in HBF_THEMES and not theme_signals.get("commercial_sampling") and not theme_signals.get("shipment_evidence"):
        flags.append("HBF commercialization evidence is still limited.")
    if asset.theme in HBF_THEMES and theme_signals.get("single_source_hype"):
        flags.append("Recent HBF narrative appears concentrated in a narrow set of sources.")
    if asset.asset_type == "etf":
        top_10_weight = _safe_float(etf_metrics.get("top_10_weight"))
        if top_10_weight is not None and top_10_weight >= 50.0:
            flags.append(
                "Top 10 ETF holdings account for about {value:.1f}% of assets.".format(
                    value=top_10_weight
                )
            )

        sector_bias = str(etf_metrics.get("sector_bias", "")).lower()
        if sector_bias and any(
            keyword in sector_bias
            for keyword in ("technology", "semiconductor", "nasdaq 100", "small-cap")
        ):
            flags.append(
                "ETF exposure is narrower than a broad-market benchmark and can diverge sharply from SPY."
            )
    return flags


def _build_etf_metrics(
    asset: AssetDefinition,
    etf_snapshot: EtfSnapshot,
) -> Dict[str, Any]:
    if asset.asset_type != "etf":
        return {}

    metrics = dict(etf_snapshot.metrics)
    metrics.setdefault("category", asset.role or asset.theme)

    sector_bias = _infer_etf_sector_bias(asset, metrics)
    concentration = _classify_etf_concentration(metrics)
    holdings_note = _build_etf_holdings_note(metrics, sector_bias)

    if sector_bias:
        metrics["sector_bias"] = sector_bias
    if concentration:
        metrics["concentration"] = concentration
    if holdings_note:
        metrics["holdings_note"] = holdings_note

    return metrics


def _infer_etf_sector_bias(asset: AssetDefinition, metrics: Dict[str, Any]) -> Optional[str]:
    index_tracked = str(metrics.get("index_tracked", "")).lower()
    role = str(asset.role or "").lower()

    if role in {"primary_benchmark", "alternate_benchmark"} or "s&p 500" in index_tracked:
        return "broad U.S. large-cap benchmark exposure"
    if role == "growth_proxy" or "nasdaq-100" in index_tracked or "nasdaq 100" in index_tracked:
        return "growth-heavy Nasdaq 100 exposure"
    if role == "small_cap_proxy" or "russell 2000" in index_tracked:
        return "small-cap U.S. equity exposure"
    if role == "sector_proxy" or "technology select sector" in index_tracked:
        return "technology sector exposure"
    if role == "semiconductor_proxy" or "semiconductor" in index_tracked:
        return "semiconductor sector exposure"

    category = metrics.get("category")
    if category:
        return "{value} exposure".format(value=str(category))
    return None


def _classify_etf_concentration(metrics: Dict[str, Any]) -> Optional[str]:
    top_10_weight = _safe_float(metrics.get("top_10_weight"))
    if top_10_weight is None:
        return None
    if top_10_weight >= 55.0:
        return "high top-holdings concentration"
    if top_10_weight >= 35.0:
        return "moderate top-holdings concentration"
    return "broad diversification across top holdings"


def _build_etf_holdings_note(
    metrics: Dict[str, Any],
    sector_bias: Optional[str],
) -> Optional[str]:
    parts = []
    top_holdings = metrics.get("top_holdings") or []
    leaders = []
    if isinstance(top_holdings, list):
        for item in top_holdings[:3]:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "").strip()
            name = str(item.get("name") or "").strip()
            leaders.append(symbol or name)
    if leaders:
        parts.append("Top holdings include {value}".format(value=", ".join(leaders)))

    top_10_weight = _safe_float(metrics.get("top_10_weight"))
    if top_10_weight is not None:
        parts.append(
            "top 10 account for {value:.1f}% of assets".format(value=top_10_weight)
        )

    index_tracked = str(metrics.get("index_tracked") or "").strip()
    if index_tracked:
        parts.append("tracks {value}".format(value=index_tracked))
    elif sector_bias:
        parts.append(str(sector_bias))

    if not parts:
        return None
    return "; ".join(parts)


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _calc_return(closes: List[float], window: int) -> Optional[float]:
    if len(closes) <= window:
        return None
    previous = closes[-window - 1]
    if previous == 0:
        return None
    return round(((closes[-1] / previous) - 1.0) * 100.0, 2)


def _relative_strength(
    closes: List[float],
    benchmark_closes: List[float],
    window: int,
) -> Optional[float]:
    asset_return = _calc_return(closes, window)
    benchmark_return = _calc_return(benchmark_closes, window)
    if asset_return is None or benchmark_return is None:
        return None
    return round(asset_return - benchmark_return, 2)


def _price_vs_ma(closes: List[float], window: int) -> Optional[float]:
    if len(closes) < window:
        return None
    moving_average = sum(closes[-window:]) / float(window)
    if moving_average == 0:
        return None
    return round(closes[-1] / moving_average, 4)


def _drawdown(closes: List[float]) -> Optional[float]:
    if not closes:
        return None
    peak = max(closes)
    if peak == 0:
        return None
    return round(((closes[-1] / peak) - 1.0) * 100.0, 2)


def _annualized_volatility(closes: List[float]) -> Optional[float]:
    if len(closes) < 2:
        return None
    returns = []
    for previous, current in zip(closes[:-1], closes[1:]):
        if previous == 0:
            continue
        returns.append((current / previous) - 1.0)
    if len(returns) < 2:
        return None
    mean_return = sum(returns) / float(len(returns))
    variance = sum((value - mean_return) ** 2 for value in returns) / float(len(returns) - 1)
    return round((variance ** 0.5) * sqrt(252.0) * 100.0, 2)

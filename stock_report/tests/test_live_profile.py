"""Live profile builder tests."""

from datetime import datetime
from datetime import timezone
import unittest

from stock_report.connectors.etf_data import EtfSnapshot
from stock_report.connectors.fundamentals import FundamentalsSnapshot
from stock_report.connectors.market_data import PriceBar
from stock_report.connectors.market_data import PriceHistory
from stock_report.models import AssetDefinition
from stock_report.models import NewsItem
from stock_report.models import Watchlist
from stock_report.pipelines.live_profile import LiveAnalysisBuilder


class StubMarketDataClient:
    def __init__(self, payloads):
        self.payloads = payloads

    def fetch_history(self, symbol, range_value="1y", interval="1d"):
        return self.payloads[symbol]


class StubNewsClient:
    def __init__(self, news_items):
        self.news_items = news_items

    def fetch_news(self, asset, days=7, limit=5):
        return self.news_items[:limit]


class StubFundamentalsClient:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def fetch_fundamentals(self, asset):
        return self.snapshot


class StubEtfClient:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def fetch_etf(self, symbol):
        return self.snapshot


class LiveProfileTests(unittest.TestCase):
    def test_build_creates_live_analysis_with_theme_signals(self) -> None:
        asset = AssetDefinition(
            symbol="SNDK",
            name="Sandisk",
            asset_type="stock",
            theme="hbf_memory_storage",
        )
        watchlist = Watchlist(
            version=1,
            defaults={"benchmark_symbol": "SPY"},
            assets={"SNDK": asset, "SPY": AssetDefinition(symbol="SPY", name="SPY", asset_type="etf", theme="primary_benchmark")},
            theme_notes={},
            reporting={"max_news_items": 5},
        )
        bars = _bars([100, 101, 102, 103, 105, 106, 108, 110, 111, 112, 113, 115, 117, 119, 120, 123, 124, 126, 127, 129, 131, 133])
        benchmark_bars = _bars([100, 100.5, 101, 101.2, 101.4, 101.8, 102, 102.5, 102.6, 103, 103.5, 104, 104.4, 104.8, 105, 105.1, 105.3, 105.5, 105.7, 106, 106.2, 106.5])
        market_client = StubMarketDataClient(
            {
                "SNDK": PriceHistory(
                    symbol="SNDK",
                    currency="USD",
                    exchange_name="NMS",
                    instrument_type="EQUITY",
                    short_name="Sandisk",
                    regular_market_price=133.0,
                    bars=bars,
                ),
                "SPY": PriceHistory(
                    symbol="SPY",
                    currency="USD",
                    exchange_name="PCX",
                    instrument_type="ETF",
                    short_name="SPY",
                    regular_market_price=106.5,
                    bars=benchmark_bars,
                ),
            }
        )
        news_client = StubNewsClient(
            [
                NewsItem(
                    headline="Sandisk expands HBF standardization partnership for AI inference",
                    source="Example Source",
                    published_at="2026-03-16T23:03:09+00:00",
                    impact="positive",
                    materiality=0.9,
                    tags=["standardization", "partnership", "ai_inference"],
                ),
                NewsItem(
                    headline="Sandisk starts customer sampling for high bandwidth flash platform",
                    source="Another Source",
                    published_at="2026-03-17T10:00:00+00:00",
                    impact="positive",
                    materiality=0.8,
                    tags=["product_launch"],
                ),
            ]
        )
        builder = LiveAnalysisBuilder(
            market_data_client=market_client,
            news_client=news_client,
            fundamentals_client=StubFundamentalsClient(
                FundamentalsSnapshot(
                    metrics={
                        "revenue_growth": 48.0,
                        "earnings_growth": 56.0,
                        "operating_margin": 21.5,
                        "forward_pe": 18.4,
                    },
                    as_of="2026-02-25",
                    age_days=21,
                    source="stub",
                )
            ),
        )

        analysis = builder.build(watchlist=watchlist, asset=asset)

        self.assertEqual(analysis.asset_type, "stock")
        self.assertIsNotNone(analysis.prices["return_20d"])
        self.assertGreater(analysis.prices["rs_20d"], 0.0)
        self.assertEqual(analysis.fundamentals["forward_pe"], 18.4)
        self.assertEqual(analysis.freshness["fundamentals_data_as_of"], "2026-02-25")
        self.assertTrue(analysis.theme_signals["standardization_progress"])
        self.assertTrue(analysis.theme_signals["commercial_sampling"])
        self.assertEqual(analysis.benchmark_symbol, "SPY")

    def test_build_populates_live_etf_metrics(self) -> None:
        asset = AssetDefinition(
            symbol="QQQ",
            name="Invesco QQQ Trust",
            asset_type="etf",
            theme="growth_proxy",
            role="growth_proxy",
        )
        watchlist = Watchlist(
            version=1,
            defaults={"benchmark_symbol": "SPY"},
            assets={
                "QQQ": asset,
                "SPY": AssetDefinition(
                    symbol="SPY",
                    name="SPY",
                    asset_type="etf",
                    theme="primary_benchmark",
                    role="primary_benchmark",
                ),
            },
            theme_notes={},
            reporting={"max_news_items": 5},
        )
        market_client = StubMarketDataClient(
            {
                "QQQ": PriceHistory(
                    symbol="QQQ",
                    currency="USD",
                    exchange_name="NMS",
                    instrument_type="ETF",
                    short_name="QQQ",
                    regular_market_price=452.0,
                    bars=_bars([400, 403, 405, 408, 410, 412, 416, 418, 420, 424, 427, 430, 434, 438, 441, 444, 447, 449, 450, 451, 452, 453]),
                ),
                "SPY": PriceHistory(
                    symbol="SPY",
                    currency="USD",
                    exchange_name="PCX",
                    instrument_type="ETF",
                    short_name="SPY",
                    regular_market_price=520.0,
                    bars=_bars([500, 501, 502, 503, 504, 505, 506, 507, 509, 510, 511, 512, 513, 514, 515, 516, 517, 518, 518, 519, 520, 521]),
                ),
            }
        )
        builder = LiveAnalysisBuilder(
            market_data_client=market_client,
            news_client=StubNewsClient([]),
            fundamentals_client=StubFundamentalsClient(
                FundamentalsSnapshot(metrics={}, as_of=None, age_days=None, source="n/a")
            ),
            etf_client=StubEtfClient(
                EtfSnapshot(
                    metrics={
                        "category": "Large Growth",
                        "provider": "Invesco",
                        "expense_ratio": 0.18,
                        "aum": 312_000_000_000.0,
                        "holdings_count": 101,
                        "top_10_weight": 51.2,
                        "index_tracked": "NASDAQ-100 Index",
                        "top_holdings": [
                            {"name": "Microsoft", "symbol": "MSFT", "weight": 8.9},
                            {"name": "NVIDIA", "symbol": "NVDA", "weight": 8.4},
                            {"name": "Apple", "symbol": "AAPL", "weight": 8.1},
                        ],
                    },
                    as_of="2026-03-17",
                    age_days=1,
                    source="stub",
                )
            ),
        )

        analysis = builder.build(watchlist=watchlist, asset=asset)

        self.assertEqual(analysis.asset_type, "etf")
        self.assertEqual(analysis.etf["provider"], "Invesco")
        self.assertEqual(analysis.etf["holdings_count"], 101)
        self.assertEqual(analysis.etf["sector_bias"], "growth-heavy Nasdaq 100 exposure")
        self.assertEqual(analysis.etf["concentration"], "moderate top-holdings concentration")
        self.assertIn("MSFT, NVDA, AAPL", analysis.etf["holdings_note"])
        self.assertEqual(analysis.freshness["etf_data_as_of"], "2026-03-17")
        self.assertTrue(
            any(
                "ETF exposure is narrower than a broad-market benchmark" in item
                for item in analysis.risk_flags
            )
        )


def _bars(closes):
    base = datetime(2026, 2, 1, tzinfo=timezone.utc)
    items = []
    for index, close in enumerate(closes):
        items.append(
            PriceBar(
                timestamp=base.replace(day=min(index + 1, 28)),
                open=float(close) - 1.0,
                high=float(close) + 1.0,
                low=float(close) - 2.0,
                close=float(close),
                adjclose=float(close),
                volume=1000.0 + index,
            )
        )
    return items


if __name__ == "__main__":
    unittest.main()

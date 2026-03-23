"""Backtest labeling tests."""

from datetime import datetime
from datetime import timedelta
from datetime import timezone
import unittest

from stock_report.analysis.backtest import build_backtest_aggregate
from stock_report.analysis.backtest import build_backtest_snapshot
from stock_report.connectors.market_data import PriceBar
from stock_report.connectors.market_data import PriceHistory


class StubMarketDataClient:
    def __init__(self, payloads):
        self.payloads = payloads

    def fetch_history(self, symbol, range_value="2y"):
        return self.payloads[symbol]


class BacktestTests(unittest.TestCase):
    def test_build_backtest_snapshot_computes_forward_and_pending_labels(self) -> None:
        scorecards = [
            {
                "asset": {
                    "symbol": "AAA",
                    "name": "Alpha",
                    "display_name": "Alpha (AAA)",
                    "asset_type": "stock",
                    "market": "US",
                    "theme": "ai_compute",
                    "benchmark_symbol": "SPY",
                },
                "scores": {
                    "total_score": 78.0,
                    "base_total_score": 74.0,
                    "confidence_score": 82.0,
                    "verdict": "review",
                },
                "freshness": {
                    "price_data_as_of": "2026-01-10",
                },
            }
        ]
        client = StubMarketDataClient(
            {
                "AAA": _history("AAA", [100, 101, 102, 103, 104, 105, 107, 108, 109, 110, 112, 113, 114, 116, 118]),
                "SPY": _history("SPY", [100, 100.2, 100.5, 100.7, 101, 101.3, 101.6, 102, 102.4, 102.8, 103, 103.3, 103.5, 103.8, 104]),
            }
        )

        snapshot = build_backtest_snapshot(
            batch_date="2026-01-10",
            generated_at_utc="2026-02-01T00:00:00+00:00",
            benchmark_symbol="SPY",
            scorecards=scorecards,
            horizons=[5, 20],
            history_range="2y",
            market_data_client=client,
        )

        result = snapshot["results"][0]
        horizon_5d = result["horizons"]["5d"]
        horizon_20d = result["horizons"]["20d"]

        self.assertEqual(horizon_5d["asset"]["status"], "complete")
        self.assertAlmostEqual(horizon_5d["asset"]["return_pct"], 7.27, places=2)
        self.assertAlmostEqual(horizon_5d["benchmark"]["return_pct"], 1.17, places=2)
        self.assertAlmostEqual(horizon_5d["excess_return"], 6.1, places=2)
        self.assertEqual(horizon_5d["evaluation"]["verdict_alignment"], "aligned")

        self.assertEqual(horizon_20d["asset"]["status"], "pending")
        self.assertIsNone(horizon_20d["excess_return"])
        self.assertEqual(snapshot["summary_by_horizon"]["5d"]["review"]["completed"], 1)
        self.assertEqual(snapshot["summary_by_horizon"]["20d"]["review"]["completed"], 0)
        self.assertIn("readable_ko", snapshot)

    def test_build_backtest_aggregate_summarizes_verdicts_and_score_bands(self) -> None:
        snapshots = [
            {
                "batch_date": "2026-03-01",
                "horizons": [5],
                "results": [
                    {
                        "symbol": "AAA",
                        "name": "Alpha",
                        "display_name": "Alpha (AAA)",
                        "verdict": "review",
                        "total_score": 74.0,
                        "horizons": {
                            "5d": {
                                "asset": {"status": "complete", "return_pct": 8.0},
                                "benchmark": {"status": "complete", "return_pct": 3.0},
                                "excess_return": 5.0,
                                "evaluation": {"verdict_alignment": "aligned"},
                            }
                        },
                    },
                    {
                        "symbol": "BBB",
                        "name": "Beta",
                        "display_name": "Beta (BBB)",
                        "verdict": "hold",
                        "total_score": 58.0,
                        "horizons": {
                            "5d": {
                                "asset": {"status": "complete", "return_pct": 1.0},
                                "benchmark": {"status": "complete", "return_pct": 2.0},
                                "excess_return": -1.0,
                                "evaluation": {"verdict_alignment": "aligned"},
                            }
                        },
                    },
                ],
            },
            {
                "batch_date": "2026-03-02",
                "horizons": [5],
                "results": [
                    {
                        "symbol": "CCC",
                        "name": "Gamma",
                        "display_name": "Gamma (CCC)",
                        "verdict": "review",
                        "total_score": 82.0,
                        "horizons": {
                            "5d": {
                                "asset": {"status": "complete", "return_pct": -2.0},
                                "benchmark": {"status": "complete", "return_pct": 1.0},
                                "excess_return": -3.0,
                                "evaluation": {"verdict_alignment": "misaligned"},
                            }
                        },
                    }
                ],
            },
        ]

        summary = build_backtest_aggregate(
            snapshots=snapshots,
            generated_at_utc="2026-03-18T00:00:00+00:00",
        )

        review_5d = summary["verdict_summary_by_horizon"]["5d"]["review"]
        band_70s = summary["score_band_summary_by_horizon"]["5d"]["70-79"]
        band_80s = summary["score_band_summary_by_horizon"]["5d"]["80-100"]

        self.assertEqual(summary["counts"]["snapshots_included"], 2)
        self.assertEqual(summary["counts"]["observations_total"], 3)
        self.assertEqual(review_5d["completed"], 2)
        self.assertAlmostEqual(review_5d["avg_excess_return"], 1.0, places=2)
        self.assertAlmostEqual(review_5d["alignment_rate"], 50.0, places=2)
        self.assertEqual(band_70s["completed"], 1)
        self.assertAlmostEqual(band_70s["avg_excess_return"], 5.0, places=2)
        self.assertEqual(band_80s["completed"], 1)
        self.assertAlmostEqual(band_80s["avg_excess_return"], -3.0, places=2)
        self.assertIn("readable_ko", summary)


def _history(symbol, closes):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = []
    for index, close in enumerate(closes):
        timestamp = start + timedelta(days=index)
        bars.append(
            PriceBar(
                timestamp=timestamp,
                open=float(close),
                high=float(close),
                low=float(close),
                close=float(close),
                adjclose=float(close),
                volume=1_000_000.0,
            )
        )
    return PriceHistory(
        symbol=symbol,
        currency="USD",
        exchange_name="NMS",
        instrument_type="EQUITY",
        short_name=symbol,
        regular_market_price=float(closes[-1]),
        bars=bars,
    )


if __name__ == "__main__":
    unittest.main()

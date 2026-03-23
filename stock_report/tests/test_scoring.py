"""Scoring tests."""

from pathlib import Path
import json
import unittest

from stock_report.analysis.scoring import score_asset
from stock_report.models import AnalysisInput
from stock_report.models import AssetDefinition
from stock_report.models import NewsItem
from stock_report.watchlist import load_watchlist


class ScoringTests(unittest.TestCase):
    def test_hbf_theme_gets_positive_overlay_when_evidence_is_present(self) -> None:
        root = Path(__file__).resolve().parents[1]
        watchlist = load_watchlist(str(root / "config" / "watchlist.example.yaml"))
        asset = watchlist.get_asset("SNDK")
        payload = json.loads((root / "examples" / "profiles" / "sndk.json").read_text())
        analysis = AnalysisInput.from_dict(payload)

        scores = score_asset(asset, analysis, theme_notes=watchlist.theme_notes)

        self.assertGreater(scores.theme_overlay, 0.0)
        self.assertEqual(scores.verdict, "review")
        self.assertIn("standardization progress", scores.overlay_rationale)

    def test_etf_confidence_uses_etf_inputs_instead_of_stock_growth_fields(self) -> None:
        asset = AssetDefinition(
            symbol="SPY",
            name="SPDR S&P 500 ETF Trust",
            asset_type="etf",
            theme="primary_benchmark",
            role="primary_benchmark",
        )
        analysis = AnalysisInput(
            asset_type="etf",
            benchmark_symbol="SPY",
            prices={
                "return_20d": 2.4,
                "return_60d": 6.8,
                "rs_20d": 0.5,
                "price_vs_ma50": 1.04,
                "drawdown": -4.2,
                "volatility": 16.0,
            },
            fundamentals={},
            etf={
                "category": "Large Blend",
                "expense_ratio": 0.09,
                "holdings_count": 503,
                "top_10_weight": 34.6,
            },
            news=[
                NewsItem(
                    headline="ETF sees steady inflows",
                    source="Example",
                    published_at="2026-03-17T10:00:00+00:00",
                    impact="neutral",
                    materiality=0.3,
                    tags=[],
                ),
                NewsItem(
                    headline="Large-cap index remains resilient",
                    source="Example",
                    published_at="2026-03-16T10:00:00+00:00",
                    impact="neutral",
                    materiality=0.3,
                    tags=[],
                ),
                NewsItem(
                    headline="ETF fees remain competitive",
                    source="Example",
                    published_at="2026-03-15T10:00:00+00:00",
                    impact="positive",
                    materiality=0.3,
                    tags=[],
                ),
            ],
            freshness={
                "price_data_age_days": 1,
                "fundamentals_data_age_days": None,
                "news_data_age_days": 1,
            },
        )

        scores = score_asset(asset, analysis)

        self.assertNotIn("fundamentals.revenue_growth", scores.missing_inputs)
        self.assertNotIn("fundamentals.earnings_growth", scores.missing_inputs)
        self.assertEqual(scores.missing_inputs, [])
        self.assertGreater(scores.fundamentals_score, 50.0)
        self.assertIn("high", scores.confidence_label)

    def test_custom_scoring_profile_changes_verdict_thresholds(self) -> None:
        asset = AssetDefinition(
            symbol="TEST",
            name="Test Asset",
            asset_type="stock",
            theme="ai_compute",
        )
        analysis = AnalysisInput(
            asset_type="stock",
            prices={
                "return_20d": 12.0,
                "return_60d": 18.0,
                "rs_20d": 6.0,
                "rs_60d": 7.0,
                "price_vs_ma20": 1.08,
                "price_vs_ma50": 1.12,
                "price_vs_ma200": 1.16,
                "drawdown": -4.0,
                "volatility": 16.0,
            },
            fundamentals={
                "revenue_growth": 28.0,
                "earnings_growth": 24.0,
                "operating_margin": 22.0,
                "forward_pe": 20.0,
            },
            news=[
                NewsItem(
                    headline="Test Asset beats revenue guidance",
                    source="Example",
                    published_at="2026-03-18T10:00:00+00:00",
                    impact="positive",
                    materiality=0.8,
                    tags=["earnings", "guidance"],
                )
            ],
            freshness={
                "price_data_age_days": 1,
                "fundamentals_data_age_days": 30,
                "news_data_age_days": 1,
            },
        )

        default_scores = score_asset(asset, analysis)
        strict_scores = score_asset(
            asset,
            analysis,
            scoring_profile={
                "verdict_thresholds": {
                    "review_min": 80.0,
                    "hold_min": 60.0,
                }
            },
        )

        self.assertGreaterEqual(default_scores.total_score, 60.0)
        self.assertEqual(default_scores.verdict, "review")
        self.assertEqual(strict_scores.verdict, "hold")


if __name__ == "__main__":
    unittest.main()

"""CLI integration tests."""

from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from stock_report.cli import main
from stock_report.analysis.scoring_profile import dump_scoring_profile
from stock_report.connectors.market_data import PriceBar
from stock_report.connectors.market_data import PriceHistory
from stock_report.models import AnalysisInput
from stock_report.models import NewsItem
from stock_report.notifications.telegram import TelegramNotifier


class CliTests(unittest.TestCase):
    def test_single_symbol_report_writes_markdown_and_json(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmpdir:
            markdown_path = Path(tmpdir) / "sndk.md"
            json_path = Path(tmpdir) / "sndk.json"

            result = main(
                [
                    "single-symbol",
                    "--watchlist",
                    str(root / "config" / "watchlist.example.yaml"),
                    "--symbol",
                    "SNDK",
                    "--input",
                    str(root / "examples" / "profiles" / "sndk.json"),
                    "--markdown-output",
                    str(markdown_path),
                    "--json-output",
                    str(json_path),
                ]
            )

            self.assertEqual(result, 0)
            markdown = markdown_path.read_text(encoding="utf-8")
            payload = json.loads(json_path.read_text(encoding="utf-8"))

            self.assertIn("# Sandisk (SNDK) 리서치 리포트", markdown)
            self.assertIn("테마 가감점", markdown)
            self.assertEqual(payload["asset"]["symbol"], "SNDK")
            self.assertGreater(payload["scores"]["theme_overlay"], 0.0)
            self.assertIn("readable_ko", payload)
            self.assertIn("guide_ko", payload)

    def test_daily_batch_writes_dated_summary_and_symbol_outputs(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "daily"
            builder = StubBatchBuilder()

            with patch("stock_report.cli.LiveAnalysisBuilder", return_value=builder):
                result = main(
                    [
                        "daily-batch",
                        "--watchlist",
                        str(root / "config" / "watchlist.example.yaml"),
                        "--output-dir",
                        str(output_dir),
                        "--date",
                        "2026-03-18",
                        "--symbols",
                        "SPY",
                        "SNDK",
                    ]
                )

            batch_root = output_dir / "2026-03-18"
            summary_markdown = (batch_root / "summary.md").read_text(encoding="utf-8")
            summary_payload = json.loads(
                (batch_root / "summary.json").read_text(encoding="utf-8")
            )
            spy_markdown = (batch_root / "markdown" / "spy.md").read_text(encoding="utf-8")
            sndk_profile = json.loads(
                (batch_root / "profiles" / "sndk.json").read_text(encoding="utf-8")
            )

            self.assertEqual(result, 0)
            self.assertEqual(builder.calls, ["SPY", "SNDK"])
            self.assertIn("# 일간 배치 요약 - 2026-03-18", summary_markdown)
            self.assertEqual(summary_payload["counts"]["requested"], 2)
            self.assertEqual(summary_payload["counts"]["failed"], 0)
            self.assertEqual(summary_payload["leaders"][0]["symbol"], "SNDK")
            self.assertIn("# SPDR S&P 500 ETF Trust (SPY) 리서치 리포트", spy_markdown)
            self.assertEqual(sndk_profile["benchmark_symbol"], "SPY")
            self.assertIn("readable_ko", summary_payload)
            self.assertIn("readable_ko", sndk_profile)

    def test_backtest_labels_writes_snapshot_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            batch_root = Path(tmpdir) / "daily" / "2026-03-18"
            scorecard_dir = batch_root / "scorecards"
            scorecard_dir.mkdir(parents=True)
            (batch_root / "summary.json").write_text(
                json.dumps(
                    {
                        "batch_date": "2026-03-18",
                        "benchmark_symbol": "SPY",
                    }
                ),
                encoding="utf-8",
            )
            (scorecard_dir / "aaa.json").write_text(
                json.dumps(
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
                            "total_score": 74.0,
                            "base_total_score": 70.0,
                            "confidence_score": 81.0,
                            "verdict": "review",
                        },
                        "freshness": {
                            "price_data_as_of": "2026-03-05",
                        },
                    }
                ),
                encoding="utf-8",
            )

            output_dir = Path(tmpdir) / "backtests"
            market_client = StubBacktestMarketDataClient(
                {
                    "AAA": _history("AAA", [100, 101, 102, 103, 104, 105, 107, 109, 111, 113, 115, 116]),
                    "SPY": _history("SPY", [100, 100.3, 100.6, 101, 101.4, 101.8, 102.0, 102.4, 102.8, 103.0, 103.2, 103.4]),
                }
            )

            with patch("stock_report.cli.MarketDataClient", return_value=market_client):
                result = main(
                    [
                        "backtest-labels",
                        "--batch-dir",
                        str(batch_root),
                        "--output-dir",
                        str(output_dir),
                        "--horizons",
                        "5",
                    ]
                )

            snapshot_markdown = (output_dir / "2026-03-18" / "snapshot.md").read_text(
                encoding="utf-8"
            )
            snapshot_payload = json.loads(
                (output_dir / "2026-03-18" / "snapshot.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(result, 0)
            self.assertIn("# 백테스트 스냅샷 - 2026-03-18", snapshot_markdown)
            self.assertEqual(snapshot_payload["batch_date"], "2026-03-18")
            self.assertIn("readable_ko", snapshot_payload)
            self.assertEqual(
                snapshot_payload["results"][0]["horizons"]["5d"]["asset"]["status"],
                "complete",
            )

    def test_backtest_summary_writes_aggregate_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_root = Path(tmpdir) / "backtests"
            (input_root / "2026-03-01").mkdir(parents=True)
            (input_root / "2026-03-02").mkdir(parents=True)
            (input_root / "2026-03-01" / "snapshot.json").write_text(
                json.dumps(
                    {
                        "batch_date": "2026-03-01",
                        "horizons": [5],
                        "results": [
                            {
                                "symbol": "AAA",
                                "name": "Alpha",
                                "display_name": "Alpha (AAA)",
                                "verdict": "review",
                                "total_score": 76.0,
                                "horizons": {
                                    "5d": {
                                        "asset": {"status": "complete", "return_pct": 7.0},
                                        "benchmark": {"status": "complete", "return_pct": 2.0},
                                        "excess_return": 5.0,
                                        "evaluation": {"verdict_alignment": "aligned"},
                                    }
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (input_root / "2026-03-02" / "snapshot.json").write_text(
                json.dumps(
                    {
                        "batch_date": "2026-03-02",
                        "horizons": [5],
                        "results": [
                            {
                                "symbol": "BBB",
                                "name": "Beta",
                                "display_name": "Beta (BBB)",
                                "verdict": "hold",
                                "total_score": 55.0,
                                "horizons": {
                                    "5d": {
                                        "asset": {"status": "complete", "return_pct": 1.0},
                                        "benchmark": {"status": "complete", "return_pct": 1.5},
                                        "excess_return": -0.5,
                                        "evaluation": {"verdict_alignment": "aligned"},
                                    }
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            output_dir = Path(tmpdir) / "aggregate"
            result = main(
                [
                    "backtest-summary",
                    "--input-dir",
                    str(input_root),
                    "--output-dir",
                    str(output_dir),
                ]
            )

            summary_markdown = (output_dir / "summary.md").read_text(encoding="utf-8")
            summary_payload = json.loads(
                (output_dir / "summary.json").read_text(encoding="utf-8")
            )

            self.assertEqual(result, 0)
            self.assertIn("# 백테스트 집계 요약", summary_markdown)
            self.assertEqual(summary_payload["counts"]["snapshots_included"], 2)
            self.assertIn("verdict_summary_by_horizon", summary_payload)
            self.assertIn("score_band_summary_by_horizon", summary_payload)
            self.assertIn("readable_ko", summary_payload)

    def test_calibration_report_writes_report_and_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            aggregate_path = Path(tmpdir) / "aggregate.json"
            aggregate_path.write_text(
                json.dumps(
                    {
                        "counts": {
                            "snapshots_included": 1,
                            "status_by_horizon": {"20d": {"pending": 2}},
                        },
                        "verdict_summary_by_horizon": {
                            "20d": {
                                "review": {"completed": 0, "avg_excess_return": None},
                                "hold": {"completed": 0, "avg_excess_return": None},
                            }
                        },
                        "score_band_summary_by_horizon": {
                            "20d": {
                                "50-59": {"completed": 0, "avg_excess_return": None},
                                "70-79": {"completed": 0, "avg_excess_return": None},
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            current_profile = Path(tmpdir) / "scoring.yaml"
            current_profile.write_text(
                dump_scoring_profile(
                    {
                        "weights": {
                            "trend": 0.35,
                            "fundamentals": 0.25,
                            "news": 0.20,
                            "risk": 0.20,
                        }
                    }
                ),
                encoding="utf-8",
            )

            output_dir = Path(tmpdir) / "calibration"
            result = main(
                [
                    "calibration-report",
                    "--aggregate-json",
                    str(aggregate_path),
                    "--current-profile",
                    str(current_profile),
                    "--output-dir",
                    str(output_dir),
                ]
            )

            report_markdown = (output_dir / "report.md").read_text(encoding="utf-8")
            proposed_profile = (output_dir / "proposed_scoring.yaml").read_text(
                encoding="utf-8"
            )

            self.assertEqual(result, 0)
            self.assertIn("# 점수 보정 리포트", report_markdown)
            self.assertIn("weights:", proposed_profile)

    def test_calibration_compare_writes_comparison_outputs(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmpdir:
            batch_root = Path(tmpdir) / "daily" / "2026-03-18" / "profiles"
            batch_root.mkdir(parents=True)
            source_profile = root / "examples" / "profiles" / "sndk.json"
            (batch_root / "sndk.json").write_text(
                source_profile.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            current_profile = Path(tmpdir) / "scoring.yaml"
            current_profile.write_text(
                dump_scoring_profile(
                    {
                        "weights": {
                            "trend": 0.35,
                            "fundamentals": 0.25,
                            "news": 0.20,
                            "risk": 0.20,
                        },
                        "verdict_thresholds": {
                            "review_min": 70.0,
                            "hold_min": 50.0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            proposed_profile = Path(tmpdir) / "proposed.yaml"
            proposed_profile.write_text(
                dump_scoring_profile(
                    {
                        "weights": {
                            "trend": 0.35,
                            "fundamentals": 0.25,
                            "news": 0.20,
                            "risk": 0.20,
                        },
                        "verdict_thresholds": {
                            "review_min": 80.0,
                            "hold_min": 60.0,
                        },
                    }
                ),
                encoding="utf-8",
            )

            output_dir = Path(tmpdir) / "calibration"
            result = main(
                [
                    "calibration-compare",
                    "--watchlist",
                    str(root / "config" / "watchlist.example.yaml"),
                    "--batch-dir",
                    str(batch_root.parent),
                    "--current-profile",
                    str(current_profile),
                    "--proposed-profile",
                    str(proposed_profile),
                    "--output-dir",
                    str(output_dir),
                ]
            )

            comparison_markdown = (output_dir / "comparison.md").read_text(
                encoding="utf-8"
            )
            comparison_payload = json.loads(
                (output_dir / "comparison.json").read_text(encoding="utf-8")
            )

            self.assertEqual(result, 0)
            self.assertIn("# 점수 보정 전후 비교", comparison_markdown)
            self.assertEqual(comparison_payload["counts"]["assets"], 1)
            self.assertIn("profile_changes", comparison_payload)

    def test_daily_refresh_writes_run_summary(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmpdir:
            daily_root = Path(tmpdir) / "daily"
            backtest_root = Path(tmpdir) / "backtests"
            aggregate_root = Path(tmpdir) / "aggregate"
            calibration_root = Path(tmpdir) / "calibration"
            automation_root = Path(tmpdir) / "automation"

            def stub_daily_batch(args):
                batch_root = Path(args.output_dir) / args.batch_date
                batch_root.mkdir(parents=True, exist_ok=True)
                (batch_root / "summary.json").write_text("{}", encoding="utf-8")
                return 0

            with patch("stock_report.cli._run_daily_batch", side_effect=stub_daily_batch), patch(
                "stock_report.cli._run_backtest_labels", return_value=0
            ) as backtest_labels, patch(
                "stock_report.cli._run_backtest_summary", return_value=0
            ) as backtest_summary, patch(
                "stock_report.cli._run_calibration_report", return_value=0
            ) as calibration_report, patch(
                "stock_report.cli._run_calibration_compare", return_value=0
            ) as calibration_compare, patch(
                "stock_report.cli.TelegramNotifier.from_env", return_value=None
            ):
                result = main(
                    [
                        "daily-refresh",
                        "--watchlist",
                        str(root / "config" / "watchlist.example.yaml"),
                        "--date",
                        "2026-03-19",
                        "--symbols",
                        "SPY",
                        "SNDK",
                        "--daily-output-dir",
                        str(daily_root),
                        "--backtest-output-dir",
                        str(backtest_root),
                        "--aggregate-output-dir",
                        str(aggregate_root),
                        "--calibration-output-dir",
                        str(calibration_root),
                        "--automation-output-dir",
                        str(automation_root),
                    ]
                )

            summary_markdown = (
                automation_root / "2026-03-19" / "summary.md"
            ).read_text(encoding="utf-8")
            summary_payload = json.loads(
                (automation_root / "2026-03-19" / "summary.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(result, 0)
            self.assertIn("# 일일 자동 실행 요약 - 2026-03-19", summary_markdown)
            self.assertEqual(len(summary_payload["steps"]), 6)
            self.assertEqual(summary_payload["steps"][-1]["name"], "telegram_notify")
            self.assertEqual(summary_payload["steps"][-1]["status"], "skipped")
            self.assertIn("readable_ko", summary_payload)
            self.assertIn("guide_ko", summary_payload)
            self.assertEqual(backtest_labels.call_count, 1)
            self.assertTrue(backtest_summary.called)
            self.assertTrue(calibration_report.called)
            self.assertTrue(calibration_compare.called)

    def test_telegram_test_sends_message(self) -> None:
        notifier = StubTelegramNotifier()

        with patch(
            "stock_report.cli.TelegramNotifier.from_env",
            return_value=notifier,
        ):
            result = main(["telegram-test", "--message", "테스트 메시지"])

        self.assertEqual(result, 0)
        self.assertEqual(notifier.messages, ["테스트 메시지"])

    def test_telegram_test_requires_environment(self) -> None:
        with patch("stock_report.cli.TelegramNotifier.from_env", return_value=None):
            result = main(["telegram-test"])

        self.assertEqual(result, 1)

    def test_telegram_test_reads_runtime_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_env = Path(tmpdir) / "runtime.env"
            runtime_env.write_text(
                "\n".join(
                    [
                        "STOCK_REPORT_TELEGRAM_BOT_TOKEN=test-bot-token",
                        "STOCK_REPORT_TELEGRAM_CHAT_ID=123456",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(
                "os.environ",
                {"STOCK_REPORT_RUNTIME_ENV_FILE": str(runtime_env)},
                clear=True,
            ), patch.object(
                TelegramNotifier,
                "send_message",
                autospec=True,
            ) as send_message:
                result = main(["telegram-test", "--message", "런타임 파일 테스트"])

        self.assertEqual(result, 0)
        self.assertEqual(send_message.call_count, 1)
        self.assertEqual(send_message.call_args.args[1], "런타임 파일 테스트")


class StubBatchBuilder:
    def __init__(self) -> None:
        self.calls = []

    def build(
        self,
        watchlist,
        asset,
        benchmark_symbol=None,
        history_range="1y",
        news_days=7,
        max_news_items=None,
    ):
        self.calls.append(asset.symbol)
        if asset.asset_type == "etf":
            return AnalysisInput(
                asset_type="etf",
                report_time_utc="2026-03-18T00:00:00+00:00",
                benchmark_symbol=benchmark_symbol or "SPY",
                prices={
                    "return_5d": 1.2,
                    "return_20d": 2.4,
                    "return_60d": 5.5,
                    "rs_20d": 0.3,
                    "price_vs_ma20": 1.01,
                    "price_vs_ma50": 1.03,
                    "price_vs_ma200": 1.08,
                    "drawdown": -2.5,
                    "volatility": 14.0,
                },
                etf={
                    "category": "Large Blend",
                    "provider": "State Street",
                    "expense_ratio": 0.09,
                    "aum": 600_000_000_000.0,
                    "holdings_count": 504,
                    "top_10_weight": 37.1,
                    "sector_bias": "broad U.S. large-cap benchmark exposure",
                    "concentration": "moderate top-holdings concentration",
                    "holdings_note": "Top holdings include NVDA, AAPL, MSFT",
                },
                news=[
                    NewsItem(
                        headline="SPY ETF sees steady inflows",
                        source="Example",
                        published_at="2026-03-17T10:00:00+00:00",
                        impact="neutral",
                        materiality=0.4,
                        tags=[],
                    )
                ],
                freshness={
                    "price_data_as_of": "2026-03-17",
                    "price_data_age_days": 1,
                    "fundamentals_data_as_of": "n/a",
                    "fundamentals_data_age_days": None,
                    "etf_data_as_of": "2026-03-17",
                    "etf_data_age_days": 1,
                    "news_window": "2026-03-11 to 2026-03-18",
                    "news_data_age_days": 1,
                },
            )

        return AnalysisInput(
            asset_type="stock",
            report_time_utc="2026-03-18T00:00:00+00:00",
            benchmark_symbol=benchmark_symbol or "SPY",
            prices={
                "return_5d": 2.2,
                "return_20d": 7.4,
                "return_60d": 15.5,
                "rs_20d": 4.3,
                "price_vs_ma20": 1.04,
                "price_vs_ma50": 1.08,
                "price_vs_ma200": 1.18,
                "drawdown": -6.5,
                "volatility": 28.0,
            },
            fundamentals={
                "revenue_growth": 48.0,
                "earnings_growth": 56.0,
                "operating_margin": 21.5,
                "forward_pe": 18.4,
            },
            news=[
                NewsItem(
                    headline="Sandisk expands HBF standardization partnership",
                    source="Example",
                    published_at="2026-03-17T10:00:00+00:00",
                    impact="positive",
                    materiality=0.8,
                    tags=["standardization"],
                )
            ],
            freshness={
                "price_data_as_of": "2026-03-17",
                "price_data_age_days": 1,
                "fundamentals_data_as_of": "2026-02-25",
                "fundamentals_data_age_days": 21,
                "etf_data_as_of": "n/a",
                "etf_data_age_days": None,
                "news_window": "2026-03-11 to 2026-03-18",
                "news_data_age_days": 1,
            },
            theme_signals={
                "standardization_progress": True,
                "commercial_sampling": True,
                "shipment_evidence": False,
                "ecosystem_partners": 1,
                "ai_inference_mentions": 1,
                "concept_only_news_count": 0,
                "single_source_hype": False,
            },
        )


class StubBacktestMarketDataClient:
    def __init__(self, payloads) -> None:
        self.payloads = payloads

    def fetch_history(self, symbol, range_value="2y"):
        return self.payloads[symbol]


class StubTelegramNotifier:
    def __init__(self) -> None:
        self.messages = []

    def send_message(self, text: str) -> None:
        self.messages.append(text)


def _history(symbol, closes):
    start = datetime(2026, 3, 1, tzinfo=timezone.utc)
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

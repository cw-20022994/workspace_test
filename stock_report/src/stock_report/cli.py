"""Command-line interface for the first runnable report flow."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional

from stock_report.analysis.backtest import build_backtest_aggregate
from stock_report.analysis.backtest import build_backtest_snapshot
from stock_report.analysis.calibration import build_score_profile_comparison
from stock_report.analysis.calibration import build_scoring_calibration_report
from stock_report.analysis.scoring import score_asset
from stock_report.analysis.scoring_profile import dump_scoring_profile
from stock_report.analysis.scoring_profile import load_scoring_profile
from stock_report.connectors.market_data import MarketDataClient
from stock_report.models import AnalysisInput
from stock_report.models import AssetDefinition
from stock_report.notifications.telegram import TelegramNotifier
from stock_report.notifications.telegram import TelegramNotifyError
from stock_report.notifications.telegram import build_daily_refresh_message
from stock_report.notifications.telegram import build_test_message
from stock_report.pipelines.live_profile import LiveAnalysisBuilder
from stock_report.rendering.automation import build_daily_refresh_guide_ko
from stock_report.rendering.automation import build_daily_refresh_readable_ko
from stock_report.rendering.automation import render_daily_refresh_markdown
from stock_report.rendering.backtest import render_backtest_aggregate_markdown
from stock_report.rendering.backtest import render_backtest_markdown
from stock_report.rendering.batch import build_daily_summary_payload
from stock_report.rendering.batch import render_daily_summary_markdown
from stock_report.rendering.calibration import render_calibration_comparison_markdown
from stock_report.rendering.calibration import render_calibration_markdown
from stock_report.rendering.localization import asset_type_label_ko
from stock_report.rendering.localization import build_profile_guide_ko
from stock_report.rendering.localization import display_name
from stock_report.rendering.localization import impact_label_ko
from stock_report.rendering.localization import market_label_ko
from stock_report.rendering.localization import news_category_label_ko
from stock_report.rendering.localization import news_priority_label_ko
from stock_report.rendering.localization import theme_label_ko
from stock_report.rendering.localization import translate_text_ko
from stock_report.rendering.markdown import build_scorecard
from stock_report.rendering.markdown import render_markdown_report
from stock_report.watchlist import load_watchlist


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stock-report")
    subparsers = parser.add_subparsers(dest="command", required=True)

    single_symbol = subparsers.add_parser(
        "single-symbol",
        help="Generate a deterministic report for one symbol from a JSON profile.",
    )
    single_symbol.add_argument(
        "--watchlist",
        required=True,
        help="Path to the watchlist YAML file.",
    )
    single_symbol.add_argument(
        "--symbol",
        required=True,
        help="Ticker symbol to render.",
    )
    single_symbol.add_argument(
        "--input",
        required=True,
        dest="input_path",
        help="Path to the analysis profile JSON file.",
    )
    single_symbol.add_argument(
        "--markdown-output",
        help="Optional output path for the Markdown report.",
    )
    single_symbol.add_argument(
        "--json-output",
        help="Optional output path for the JSON scorecard.",
    )

    live_symbol = subparsers.add_parser(
        "live-symbol",
        help="Fetch live price/news data and generate a report for one symbol.",
    )
    live_symbol.add_argument(
        "--watchlist",
        required=True,
        help="Path to the watchlist YAML file.",
    )
    live_symbol.add_argument(
        "--symbol",
        required=True,
        help="Ticker symbol to render.",
    )
    live_symbol.add_argument(
        "--benchmark",
        help="Optional benchmark override. Defaults to the watchlist benchmark.",
    )
    live_symbol.add_argument(
        "--history-range",
        default="1y",
        help="History range to fetch, for example 6mo, 1y, or 2y.",
    )
    live_symbol.add_argument(
        "--news-days",
        type=int,
        default=7,
        help="Recent news window in days.",
    )
    live_symbol.add_argument(
        "--profile-output",
        help="Optional output path for the fetched analysis profile JSON.",
    )
    live_symbol.add_argument(
        "--markdown-output",
        help="Optional output path for the Markdown report.",
    )
    live_symbol.add_argument(
        "--json-output",
        help="Optional output path for the JSON scorecard.",
    )

    daily_batch = subparsers.add_parser(
        "daily-batch",
        help="Fetch live data for a watchlist slice and write dated batch outputs.",
    )
    daily_batch.add_argument(
        "--watchlist",
        required=True,
        help="Path to the watchlist YAML file.",
    )
    daily_batch.add_argument(
        "--output-dir",
        default="reports/daily",
        help="Root output directory for dated batch folders.",
    )
    daily_batch.add_argument(
        "--benchmark",
        help="Optional benchmark override. Defaults to the watchlist benchmark.",
    )
    daily_batch.add_argument(
        "--history-range",
        default="1y",
        help="History range to fetch, for example 6mo, 1y, or 2y.",
    )
    daily_batch.add_argument(
        "--news-days",
        type=int,
        default=7,
        help="Recent news window in days.",
    )
    daily_batch.add_argument(
        "--date",
        dest="batch_date",
        help="Optional local batch date in YYYY-MM-DD format.",
    )
    daily_batch.add_argument(
        "--symbols",
        nargs="*",
        help="Optional symbol subset. Accepts space-separated values or comma-separated tokens.",
    )

    backtest_labels = subparsers.add_parser(
        "backtest-labels",
        help="Generate realized forward-return labels from an archived daily batch.",
    )
    backtest_labels.add_argument(
        "--batch-dir",
        required=True,
        help="Path to a daily batch folder that contains summary.json and scorecards/.",
    )
    backtest_labels.add_argument(
        "--output-dir",
        default="reports/backtests",
        help="Root output directory for dated backtest snapshot folders.",
    )
    backtest_labels.add_argument(
        "--history-range",
        default="2y",
        help="Price history range to fetch when labeling, for example 1y, 2y, or 5y.",
    )
    backtest_labels.add_argument(
        "--horizons",
        nargs="*",
        type=int,
        default=[5, 20, 60],
        help="Trading-day forward-return horizons to evaluate.",
    )

    backtest_summary = subparsers.add_parser(
        "backtest-summary",
        help="Aggregate multiple backtest snapshots into a calibration summary.",
    )
    backtest_summary.add_argument(
        "--input-dir",
        default="reports/backtests",
        help="Root folder that contains dated backtest snapshot folders.",
    )
    backtest_summary.add_argument(
        "--output-dir",
        default="reports/backtests/aggregate",
        help="Output folder for the aggregate summary files.",
    )
    backtest_summary.add_argument(
        "--date-from",
        help="Optional inclusive start date in YYYY-MM-DD.",
    )
    backtest_summary.add_argument(
        "--date-to",
        help="Optional inclusive end date in YYYY-MM-DD.",
    )

    calibration_report = subparsers.add_parser(
        "calibration-report",
        help="Generate a scoring calibration report from a backtest aggregate summary.",
    )
    calibration_report.add_argument(
        "--aggregate-json",
        default="reports/backtests/aggregate/summary.json",
        help="Path to a backtest aggregate summary JSON file.",
    )
    calibration_report.add_argument(
        "--current-profile",
        default="config/scoring.yaml",
        help="Path to the active scoring profile YAML file.",
    )
    calibration_report.add_argument(
        "--output-dir",
        default="reports/calibration/latest",
        help="Output folder for the calibration report and proposed profile.",
    )

    calibration_compare = subparsers.add_parser(
        "calibration-compare",
        help="Compare current and proposed scoring profiles on a saved daily batch.",
    )
    calibration_compare.add_argument(
        "--watchlist",
        required=True,
        help="Path to the watchlist YAML file.",
    )
    calibration_compare.add_argument(
        "--batch-dir",
        required=True,
        help="Path to a daily batch folder that contains profiles/.",
    )
    calibration_compare.add_argument(
        "--current-profile",
        default="config/scoring.yaml",
        help="Path to the active scoring profile YAML file.",
    )
    calibration_compare.add_argument(
        "--proposed-profile",
        default="reports/calibration/latest/proposed_scoring.yaml",
        help="Path to the proposed scoring profile YAML file.",
    )
    calibration_compare.add_argument(
        "--output-dir",
        default="reports/calibration/latest",
        help="Output folder for the comparison artifacts.",
    )

    daily_refresh = subparsers.add_parser(
        "daily-refresh",
        help="Run the full daily batch -> backtest -> calibration chain.",
    )
    daily_refresh.add_argument(
        "--watchlist",
        required=True,
        help="Path to the watchlist YAML file.",
    )
    daily_refresh.add_argument(
        "--date",
        dest="batch_date",
        help="Optional local batch date in YYYY-MM-DD format.",
    )
    daily_refresh.add_argument(
        "--symbols",
        nargs="*",
        help="Optional symbol subset. Accepts space-separated values or comma-separated tokens.",
    )
    daily_refresh.add_argument(
        "--benchmark",
        help="Optional benchmark override for the daily batch.",
    )
    daily_refresh.add_argument(
        "--history-range",
        default="1y",
        help="History range for the daily batch.",
    )
    daily_refresh.add_argument(
        "--news-days",
        type=int,
        default=7,
        help="Recent news window in days for the daily batch.",
    )
    daily_refresh.add_argument(
        "--daily-output-dir",
        default="reports/daily",
        help="Root output directory for daily batch folders.",
    )
    daily_refresh.add_argument(
        "--backtest-output-dir",
        default="reports/backtests",
        help="Root output directory for backtest snapshot folders.",
    )
    daily_refresh.add_argument(
        "--backtest-history-range",
        default="2y",
        help="Price history range to use when refreshing backtest labels.",
    )
    daily_refresh.add_argument(
        "--horizons",
        nargs="*",
        type=int,
        default=[5, 20, 60],
        help="Trading-day forward-return horizons for backtest labels.",
    )
    daily_refresh.add_argument(
        "--aggregate-output-dir",
        default="reports/backtests/aggregate",
        help="Output directory for the aggregate backtest summary.",
    )
    daily_refresh.add_argument(
        "--current-profile",
        default="config/scoring.yaml",
        help="Path to the active scoring profile YAML file.",
    )
    daily_refresh.add_argument(
        "--calibration-output-dir",
        default="reports/calibration/latest",
        help="Output directory for calibration artifacts.",
    )
    daily_refresh.add_argument(
        "--automation-output-dir",
        default="reports/automation",
        help="Output directory for the daily refresh run summary.",
    )

    telegram_test = subparsers.add_parser(
        "telegram-test",
        help="Send a manual Telegram test message using environment variables.",
    )
    telegram_test.add_argument(
        "--message",
        help="Optional custom Telegram message text.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _load_runtime_env_defaults()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "single-symbol":
        return _run_single_symbol(args)
    if args.command == "live-symbol":
        return _run_live_symbol(args)
    if args.command == "daily-batch":
        return _run_daily_batch(args)
    if args.command == "backtest-labels":
        return _run_backtest_labels(args)
    if args.command == "backtest-summary":
        return _run_backtest_summary(args)
    if args.command == "calibration-report":
        return _run_calibration_report(args)
    if args.command == "calibration-compare":
        return _run_calibration_compare(args)
    if args.command == "daily-refresh":
        return _run_daily_refresh(args)
    if args.command == "telegram-test":
        return _run_telegram_test(args)

    parser.error("Unsupported command.")
    return 2


def _run_single_symbol(args: argparse.Namespace) -> int:
    watchlist = load_watchlist(args.watchlist)
    asset = watchlist.get_asset(args.symbol)

    payload = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
    analysis = AnalysisInput.from_dict(payload)

    if not analysis.report_time_utc:
        analysis.report_time_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    if not analysis.benchmark_symbol:
        analysis.benchmark_symbol = str(
            watchlist.defaults.get("benchmark_symbol", "SPY")
        )
    if not analysis.asset_type:
        analysis.asset_type = asset.asset_type

    return _render_outputs(
        watchlist=watchlist,
        asset_symbol=args.symbol,
        analysis=analysis,
        markdown_output=args.markdown_output,
        json_output=args.json_output,
    )


def _run_live_symbol(args: argparse.Namespace) -> int:
    watchlist = load_watchlist(args.watchlist)
    asset = watchlist.get_asset(args.symbol)
    builder = LiveAnalysisBuilder()
    analysis = builder.build(
        watchlist=watchlist,
        asset=asset,
        benchmark_symbol=args.benchmark,
        history_range=args.history_range,
        news_days=args.news_days,
    )

    if args.profile_output:
        _write_text(
            args.profile_output,
            json.dumps(_analysis_to_dict(analysis, asset=asset), indent=2, sort_keys=True),
        )

    return _render_outputs(
        watchlist=watchlist,
        asset_symbol=args.symbol,
        analysis=analysis,
        markdown_output=args.markdown_output,
        json_output=args.json_output,
    )


def _run_daily_batch(args: argparse.Namespace) -> int:
    watchlist = load_watchlist(args.watchlist)
    benchmark = args.benchmark or str(watchlist.defaults.get("benchmark_symbol", "SPY"))
    batch_date = args.batch_date or _local_batch_date()
    output_root = Path(args.output_dir) / batch_date
    markdown_dir = output_root / "markdown"
    json_dir = output_root / "scorecards"
    profile_dir = output_root / "profiles"

    builder = LiveAnalysisBuilder()
    results = []

    for symbol in _resolve_symbols(watchlist, args.symbols):
        asset = watchlist.get_asset(symbol)
        try:
            analysis = builder.build(
                watchlist=watchlist,
                asset=asset,
                benchmark_symbol=args.benchmark,
                history_range=args.history_range,
                news_days=args.news_days,
            )
            outputs = _build_rendered_outputs(
                watchlist=watchlist,
                asset=asset,
                analysis=analysis,
            )

            markdown_path = markdown_dir / "{symbol}.md".format(symbol=asset.symbol.lower())
            json_path = json_dir / "{symbol}.json".format(symbol=asset.symbol.lower())
            profile_path = profile_dir / "{symbol}.json".format(symbol=asset.symbol.lower())

            _write_text(markdown_path, outputs["markdown"])
            _write_text(json_path, json.dumps(outputs["scorecard"], indent=2, sort_keys=True))
            _write_text(
                profile_path,
                json.dumps(_analysis_to_dict(analysis, asset=asset), indent=2, sort_keys=True),
            )

            results.append(
                {
                    "status": "success",
                    "symbol": asset.symbol,
                    "name": asset.name,
                    "asset_type": asset.asset_type,
                    "market": asset.market,
                    "theme": asset.theme,
                    "verdict": outputs["scores"].verdict,
                    "total_score": outputs["scores"].total_score,
                    "confidence_score": outputs["scores"].confidence_score,
                    "confidence_label": outputs["scores"].confidence_label,
                    "top_news_headline": _top_news_headline(analysis),
                    "markdown_path": str(markdown_path.relative_to(output_root)),
                    "json_path": str(json_path.relative_to(output_root)),
                    "profile_path": str(profile_path.relative_to(output_root)),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "status": "error",
                    "symbol": asset.symbol,
                    "name": asset.name,
                    "asset_type": asset.asset_type,
                    "market": asset.market,
                    "theme": asset.theme,
                    "error": str(exc),
                }
            )

    summary = build_daily_summary_payload(
        batch_date=batch_date,
        generated_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        benchmark_symbol=benchmark,
        history_range=args.history_range,
        news_days=args.news_days,
        results=results,
    )

    _write_text(output_root / "summary.md", render_daily_summary_markdown(summary))
    _write_text(output_root / "summary.json", json.dumps(summary, indent=2, sort_keys=True))

    return 0 if summary["counts"]["failed"] == 0 else 1


def _run_backtest_labels(args: argparse.Namespace) -> int:
    batch_dir = Path(args.batch_dir)
    summary_path = batch_dir / "summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(
            "summary.json was not found under {path}".format(path=batch_dir)
        )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    scorecards = _load_scorecards(batch_dir / "scorecards")
    batch_date = str(summary.get("batch_date") or batch_dir.name)
    benchmark_symbol = str(summary.get("benchmark_symbol") or "SPY")

    snapshot = build_backtest_snapshot(
        batch_date=batch_date,
        generated_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        benchmark_symbol=benchmark_symbol,
        scorecards=scorecards,
        horizons=args.horizons,
        history_range=args.history_range,
        market_data_client=MarketDataClient(),
    )

    output_root = Path(args.output_dir) / batch_date
    _write_text(output_root / "snapshot.md", render_backtest_markdown(snapshot))
    _write_text(
        output_root / "snapshot.json",
        json.dumps(snapshot, indent=2, sort_keys=True),
    )
    return 0


def _run_backtest_summary(args: argparse.Namespace) -> int:
    snapshots = _load_backtest_snapshots(Path(args.input_dir))
    summary = build_backtest_aggregate(
        snapshots=snapshots,
        generated_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        date_from=args.date_from,
        date_to=args.date_to,
    )

    output_root = Path(args.output_dir)
    _write_text(output_root / "summary.md", render_backtest_aggregate_markdown(summary))
    _write_text(
        output_root / "summary.json",
        json.dumps(summary, indent=2, sort_keys=True),
    )
    return 0


def _run_calibration_report(args: argparse.Namespace) -> int:
    aggregate_summary = json.loads(
        Path(args.aggregate_json).read_text(encoding="utf-8")
    )
    current_profile = load_scoring_profile(args.current_profile)
    report = build_scoring_calibration_report(
        aggregate_summary=aggregate_summary,
        current_profile=current_profile,
        generated_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    )

    output_root = Path(args.output_dir)
    _write_text(output_root / "report.md", render_calibration_markdown(report))
    _write_text(output_root / "report.json", json.dumps(report, indent=2, sort_keys=True))
    _write_text(
        output_root / "proposed_scoring.yaml",
        dump_scoring_profile(report["proposed_profile"]).rstrip(),
    )
    return 0


def _run_calibration_compare(args: argparse.Namespace) -> int:
    watchlist = load_watchlist(args.watchlist)
    batch_profiles = _load_batch_profiles(Path(args.batch_dir) / "profiles")
    comparison = build_score_profile_comparison(
        watchlist=watchlist,
        batch_profiles=batch_profiles,
        current_profile=load_scoring_profile(args.current_profile),
        proposed_profile=load_scoring_profile(args.proposed_profile),
    )

    output_root = Path(args.output_dir)
    _write_text(
        output_root / "comparison.md",
        render_calibration_comparison_markdown(comparison),
    )
    _write_text(
        output_root / "comparison.json",
        json.dumps(comparison, indent=2, sort_keys=True),
    )
    return 0


def _run_daily_refresh(args: argparse.Namespace) -> int:
    run_date = args.batch_date or _local_batch_date()
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    steps = []
    outputs = {}
    watchlist = load_watchlist(args.watchlist)

    daily_args = argparse.Namespace(
        watchlist=args.watchlist,
        output_dir=args.daily_output_dir,
        benchmark=args.benchmark,
        history_range=args.history_range,
        news_days=args.news_days,
        batch_date=run_date,
        symbols=args.symbols,
    )
    daily_code = _run_daily_batch(daily_args)
    daily_batch_dir = Path(args.daily_output_dir) / run_date
    steps.append(
        {
            "name": "daily_batch",
            "status": "success" if daily_code == 0 else "error",
            "detail": str(daily_batch_dir),
        }
    )
    outputs["daily_batch_dir"] = str(daily_batch_dir)

    backtest_status = "success"
    refreshed_batches = []
    for batch_dir in _list_daily_batch_dirs(Path(args.daily_output_dir)):
        label_args = argparse.Namespace(
            batch_dir=str(batch_dir),
            output_dir=args.backtest_output_dir,
            history_range=args.backtest_history_range,
            horizons=args.horizons,
        )
        code = _run_backtest_labels(label_args)
        refreshed_batches.append(batch_dir.name)
        if code != 0:
            backtest_status = "error"
    steps.append(
        {
            "name": "backtest_labels",
            "status": backtest_status,
            "detail": ", ".join(refreshed_batches) if refreshed_batches else "해당 없음",
        }
    )

    aggregate_args = argparse.Namespace(
        input_dir=args.backtest_output_dir,
        output_dir=args.aggregate_output_dir,
        date_from=None,
        date_to=None,
    )
    aggregate_code = _run_backtest_summary(aggregate_args)
    aggregate_summary_path = Path(args.aggregate_output_dir) / "summary.json"
    steps.append(
        {
            "name": "backtest_summary",
            "status": "success" if aggregate_code == 0 else "error",
            "detail": str(aggregate_summary_path),
        }
    )
    outputs["backtest_aggregate"] = str(aggregate_summary_path)

    calibration_report_args = argparse.Namespace(
        aggregate_json=str(aggregate_summary_path),
        current_profile=args.current_profile,
        output_dir=args.calibration_output_dir,
    )
    calibration_report_code = _run_calibration_report(calibration_report_args)
    calibration_report_path = Path(args.calibration_output_dir) / "report.json"
    steps.append(
        {
            "name": "calibration_report",
            "status": "success" if calibration_report_code == 0 else "error",
            "detail": str(calibration_report_path),
        }
    )
    outputs["calibration_report"] = str(calibration_report_path)

    calibration_compare_args = argparse.Namespace(
        watchlist=args.watchlist,
        batch_dir=str(daily_batch_dir),
        current_profile=args.current_profile,
        proposed_profile=str(
            Path(args.calibration_output_dir) / "proposed_scoring.yaml"
        ),
        output_dir=args.calibration_output_dir,
    )
    calibration_compare_code = _run_calibration_compare(calibration_compare_args)
    comparison_path = Path(args.calibration_output_dir) / "comparison.json"
    steps.append(
        {
            "name": "calibration_compare",
            "status": "success" if calibration_compare_code == 0 else "error",
            "detail": str(comparison_path),
        }
    )
    outputs["calibration_comparison"] = str(comparison_path)

    resolved_symbols = _resolve_symbols(watchlist, args.symbols) if args.symbols else []
    summary = _build_daily_refresh_summary(
        run_date=run_date,
        generated_at_utc=generated_at,
        symbols=resolved_symbols,
        steps=steps,
        outputs=outputs,
    )

    telegram_notifier = TelegramNotifier.from_env()
    if telegram_notifier is None:
        steps.append(
            {
                "name": "telegram_notify",
                "status": "skipped",
                "detail": "환경변수 미설정",
            }
        )
        outputs["telegram_notification"] = "skipped"
    else:
        daily_summary = _load_json_if_exists(daily_batch_dir / "summary.json")
        calibration_report = _load_json_if_exists(calibration_report_path)
        try:
            telegram_notifier.send_message(
                build_daily_refresh_message(
                    refresh_summary=summary,
                    daily_summary=daily_summary,
                    calibration_report=calibration_report,
                )
            )
        except TelegramNotifyError as exc:
            steps.append(
                {
                    "name": "telegram_notify",
                    "status": "error",
                    "detail": str(exc),
                }
            )
            outputs["telegram_notification"] = "error"
        else:
            steps.append(
                {
                    "name": "telegram_notify",
                    "status": "success",
                    "detail": "전송 완료",
                }
            )
            outputs["telegram_notification"] = "sent"

        summary = _build_daily_refresh_summary(
            run_date=run_date,
            generated_at_utc=generated_at,
            symbols=resolved_symbols,
            steps=steps,
            outputs=outputs,
        )

    if telegram_notifier is None:
        summary = _build_daily_refresh_summary(
            run_date=run_date,
            generated_at_utc=generated_at,
            symbols=resolved_symbols,
            steps=steps,
            outputs=outputs,
        )

    automation_root = Path(args.automation_output_dir) / run_date
    _write_text(automation_root / "summary.md", render_daily_refresh_markdown(summary))
    _write_text(
        automation_root / "summary.json",
        json.dumps(summary, indent=2, sort_keys=True),
    )

    return 0 if all(step["status"] in {"success", "skipped"} for step in steps) else 1


def _run_telegram_test(args: argparse.Namespace) -> int:
    notifier = TelegramNotifier.from_env()
    if notifier is None:
        print(
            "텔레그램 환경변수가 없습니다: "
            "STOCK_REPORT_TELEGRAM_BOT_TOKEN, STOCK_REPORT_TELEGRAM_CHAT_ID"
        )
        return 1

    try:
        notifier.send_message(args.message or build_test_message())
    except TelegramNotifyError as exc:
        print("텔레그램 전송 실패: {value}".format(value=exc))
        return 1

    print("텔레그램 테스트 메시지를 전송했습니다.")
    return 0


def _render_outputs(
    watchlist,
    asset_symbol: str,
    analysis: AnalysisInput,
    markdown_output: Optional[str],
    json_output: Optional[str],
) -> int:
    asset = watchlist.get_asset(asset_symbol)
    outputs = _build_rendered_outputs(
        watchlist=watchlist,
        asset=asset,
        analysis=analysis,
    )
    markdown = outputs["markdown"]
    scorecard = outputs["scorecard"]

    if markdown_output:
        _write_text(markdown_output, markdown)
    else:
        print(markdown)

    if json_output:
        _write_text(json_output, json.dumps(scorecard, indent=2, sort_keys=True))

    return 0


def _build_rendered_outputs(
    watchlist,
    asset,
    analysis: AnalysisInput,
) -> Dict[str, object]:
    scores = score_asset(asset, analysis, theme_notes=watchlist.theme_notes)
    markdown = render_markdown_report(watchlist, asset, analysis, scores)
    scorecard = build_scorecard(watchlist, asset, analysis, scores)
    return {
        "scores": scores,
        "markdown": markdown,
        "scorecard": scorecard,
    }


def _analysis_to_dict(
    analysis: AnalysisInput,
    asset: Optional[AssetDefinition] = None,
) -> dict:
    payload = {
        "asset_type": analysis.asset_type,
        "report_time_utc": analysis.report_time_utc,
        "benchmark_symbol": analysis.benchmark_symbol,
        "prices": analysis.prices,
        "fundamentals": analysis.fundamentals,
        "etf": analysis.etf,
        "news": [
            {
                "headline": item.headline,
                "summary_ko": item.summary_ko,
                "source": item.source,
                "published_at": item.published_at,
                "impact": item.impact,
                "category": item.category,
                "priority_score": item.priority_score,
                "materiality": item.materiality,
                "tags": item.tags,
            }
            for item in analysis.news
        ],
        "risk_flags": analysis.risk_flags,
        "freshness": analysis.freshness,
        "theme_signals": analysis.theme_signals,
        "notes": analysis.notes,
    }
    payload["guide_ko"] = build_profile_guide_ko()
    payload["readable_ko"] = _build_analysis_readable_ko(analysis, asset)
    return payload


def _write_text(path: str, content: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content + "\n", encoding="utf-8")


def _build_daily_refresh_summary(
    *,
    run_date: str,
    generated_at_utc: str,
    symbols: List[str],
    steps: List[Dict[str, str]],
    outputs: Dict[str, str],
) -> Dict[str, object]:
    payload: Dict[str, object] = {
        "run_date": run_date,
        "generated_at_utc": generated_at_utc,
        "symbols": symbols,
        "steps": steps,
        "outputs": outputs,
    }
    payload["guide_ko"] = build_daily_refresh_guide_ko()
    payload["readable_ko"] = build_daily_refresh_readable_ko(payload)
    return payload


def _load_json_if_exists(path: Path) -> Optional[Dict[str, object]]:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _load_runtime_env_defaults() -> None:
    env_path = os.getenv("STOCK_REPORT_RUNTIME_ENV_FILE", "config/runtime.env").strip()
    if not env_path:
        return

    path = Path(env_path)
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue

        normalized = value.strip()
        if len(normalized) >= 2 and normalized[0] == normalized[-1] and normalized[0] in {"'", '"'}:
            normalized = normalized[1:-1]
        os.environ[key] = normalized


def _load_scorecards(scorecard_dir: Path) -> List[Dict[str, object]]:
    if not scorecard_dir.exists():
        raise FileNotFoundError(
            "scorecards directory was not found under {path}".format(
                path=scorecard_dir
            )
        )

    payloads = []
    for path in sorted(scorecard_dir.glob("*.json")):
        payloads.append(json.loads(path.read_text(encoding="utf-8")))
    if not payloads:
        raise ValueError(
            "No scorecard JSON files were found under {path}".format(
                path=scorecard_dir
            )
        )
    return payloads


def _load_backtest_snapshots(input_dir: Path) -> List[Dict[str, object]]:
    if not input_dir.exists():
        raise FileNotFoundError(
            "Backtest input directory was not found: {path}".format(path=input_dir)
        )

    payloads = []
    direct_snapshot = input_dir / "snapshot.json"
    if direct_snapshot.exists():
        payloads.append(json.loads(direct_snapshot.read_text(encoding="utf-8")))
    else:
        for path in sorted(input_dir.rglob("snapshot.json")):
            payloads.append(json.loads(path.read_text(encoding="utf-8")))

    if not payloads:
        raise ValueError(
            "No snapshot.json files were found under {path}".format(path=input_dir)
        )
    return payloads


def _load_batch_profiles(profile_dir: Path) -> List[Dict[str, object]]:
    if not profile_dir.exists():
        raise FileNotFoundError(
            "profiles directory was not found under {path}".format(path=profile_dir)
        )

    payloads = []
    for path in sorted(profile_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        symbol = path.stem.upper()
        payloads.append({"symbol": symbol, "analysis": payload})
    if not payloads:
        raise ValueError(
            "No profile JSON files were found under {path}".format(path=profile_dir)
        )
    return payloads


def _list_daily_batch_dirs(root: Path) -> List[Path]:
    if not root.exists():
        return []
    batch_dirs = []
    for path in sorted(root.iterdir()):
        if not path.is_dir():
            continue
        if (path / "summary.json").exists():
            batch_dirs.append(path)
    return batch_dirs


def _resolve_symbols(watchlist, symbols: Optional[List[str]]) -> List[str]:
    if not symbols:
        return list(watchlist.assets.keys())

    resolved = []
    for item in symbols:
        for symbol in str(item).split(","):
            normalized = symbol.strip().upper()
            if not normalized:
                continue
            resolved.append(normalized)
    return resolved


def _local_batch_date() -> str:
    return datetime.now().astimezone().date().isoformat()


def _top_news_headline(analysis: AnalysisInput) -> Optional[str]:
    if not analysis.news:
        return None
    return analysis.news[0].summary_ko or analysis.news[0].headline


def _build_analysis_readable_ko(
    analysis: AnalysisInput,
    asset: Optional[AssetDefinition],
) -> Dict[str, object]:
    overview = {
        "비교기준": analysis.benchmark_symbol,
        "리포트생성시각_UTC": analysis.report_time_utc,
    }
    if asset is not None:
        overview.update(
            {
                "회사/종목명": asset.name,
                "티커": asset.symbol,
                "표시명": display_name(asset.name, asset.symbol),
                "자산구분": asset_type_label_ko(asset.asset_type),
                "시장": market_label_ko(asset.market),
                "테마": theme_label_ko(asset.theme),
            }
        )
    else:
        overview["자산구분"] = asset_type_label_ko(analysis.asset_type)

    return {
        "기본정보": overview,
        "가격요약": {
            "최근가격": analysis.prices.get("latest_price"),
            "최근5거래일수익률": _format_percent_value(analysis.prices.get("return_5d")),
            "최근20거래일수익률": _format_percent_value(analysis.prices.get("return_20d")),
            "20거래일상대강도": _format_percent_value(analysis.prices.get("rs_20d")),
            "실현변동성": _format_percent_value(analysis.prices.get("volatility")),
            "고점대비낙폭": _format_percent_value(analysis.prices.get("drawdown")),
        },
        "재무요약": {
            "매출성장률": _format_percent_value(analysis.fundamentals.get("revenue_growth")),
            "이익성장률": _format_percent_value(analysis.fundamentals.get("earnings_growth")),
            "영업이익률": _format_percent_value(analysis.fundamentals.get("operating_margin")),
            "선행PER": analysis.fundamentals.get("forward_pe"),
        },
        "ETF요약": {
            "ETF분류": translate_text_ko(analysis.etf.get("category")),
            "운용사": translate_text_ko(analysis.etf.get("provider")),
            "총보수": _format_percent_value(analysis.etf.get("expense_ratio")),
            "운용자산": analysis.etf.get("aum"),
            "보유종목수": analysis.etf.get("holdings_count"),
            "상위10개비중": _format_percent_value(analysis.etf.get("top_10_weight")),
            "집중도해석": translate_text_ko(analysis.etf.get("concentration")),
            "구성메모": translate_text_ko(analysis.etf.get("holdings_note")),
        },
        "주요뉴스": [
            {
                "한줄요약": item.summary_ko or "해당 없음",
                "제목": item.headline,
                "출처": item.source,
                "시각": item.published_at,
                "분류": news_category_label_ko(item.category),
                "중요도": news_priority_label_ko(item.priority_score),
                "영향": impact_label_ko(item.impact),
            }
            for item in analysis.news[:5]
        ],
        "위험요인": [translate_text_ko(item) for item in analysis.risk_flags],
        "데이터신선도": {
            "가격기준일": analysis.freshness.get("price_data_as_of"),
            "재무기준일": analysis.freshness.get("fundamentals_data_as_of"),
            "ETF기준일": analysis.freshness.get("etf_data_as_of"),
            "뉴스구간": analysis.freshness.get("news_window"),
        },
        "메모": translate_text_ko(analysis.notes),
    }


def _format_percent_value(value: Optional[object]) -> str:
    if value in (None, ""):
        return "해당 없음"
    return "{value:.1f}%".format(value=float(value))


if __name__ == "__main__":
    raise SystemExit(main())

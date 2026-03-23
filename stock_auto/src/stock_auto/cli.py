from __future__ import annotations

import argparse
import csv
import json
import os
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from stock_auto.adapters.auth.kis_auth import KISAuthSession, KISCredentials
from stock_auto.adapters.broker.alpaca_paper import AlpacaPaperTradingClient
from stock_auto.adapters.broker.kis_overseas import KISOverseasStockBrokerClient
from stock_auto.adapters.market_data.alpaca_historical import (
    AlpacaCredentials,
    AlpacaHistoricalBarsClient,
)
from stock_auto.adapters.market_data.kis_overseas import KISOverseasStockDataClient
from stock_auto.adapters.notify.telegram import TelegramBotClient, TelegramCredentials
from stock_auto.backtest.runner import BacktestRunner, load_bars_from_csv
from stock_auto.config import StrategyConfig
from stock_auto.csv_utils import write_bars_to_csv
from stock_auto.domain.models import Trade
from stock_auto.services.kis_bot import KISOverseasBot
from stock_auto.services.kis_monitor import KISExitMonitor, is_kis_state_terminal
from stock_auto.services.kis_state import (
    build_kis_trade_state,
    default_kis_state_path,
    load_kis_trade_state,
    save_kis_trade_state,
)
from stock_auto.services.kis_telegram import KISTelegramNotifier
from stock_auto.services.paper_bot import PaperTradingBot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stock_auto")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backtest = subparsers.add_parser("backtest", help="Run a CSV-based backtest")
    backtest.add_argument("--csv", required=True, dest="csv_path", help="Path to minute-bar CSV")
    backtest.add_argument("--config", dest="config_path", help="Path to JSON strategy config")
    backtest.add_argument(
        "--data-timezone",
        default="America/New_York",
        help="Timezone to assume when CSV timestamps are naive",
    )
    backtest.add_argument("--output-trades", help="Optional path to save executed trades as CSV")

    fetch = subparsers.add_parser("fetch-alpaca-bars", help="Download historical Alpaca stock bars to CSV")
    fetch.add_argument("--symbol", required=True, help="Ticker symbol, for example SPY")
    fetch.add_argument("--start-date", required=True, help="Inclusive UTC date, YYYY-MM-DD")
    fetch.add_argument("--end-date", required=True, help="Exclusive UTC date, YYYY-MM-DD")
    fetch.add_argument("--output", required=True, help="CSV output path")
    fetch.add_argument("--timeframe", default="1Min", help="Alpaca timeframe, default 1Min")
    fetch.add_argument("--feed", default="iex", help="Alpaca feed, default iex")
    fetch.add_argument("--adjustment", default="split", help="Alpaca adjustment mode, default split")
    fetch.add_argument("--limit", type=int, default=10000, help="Page size per API request")
    fetch.add_argument(
        "--output-timezone",
        default="America/New_York",
        help="Timezone used when writing timestamps to CSV",
    )
    fetch.add_argument("--api-key", help="Alpaca API key, defaults to APCA_API_KEY_ID")
    fetch.add_argument("--api-secret", help="Alpaca API secret, defaults to APCA_API_SECRET_KEY")

    fetch_kis = subparsers.add_parser("fetch-kis-bars", help="Download recent KIS overseas minute bars to CSV")
    fetch_kis.add_argument("--symbol", required=True, help="Ticker symbol, for example SPY")
    fetch_kis.add_argument("--quote-exchange", default="AMS", help="KIS quote exchange code, default AMS")
    fetch_kis.add_argument("--records", type=int, default=180, help="Maximum number of recent bars to request")
    fetch_kis.add_argument("--interval", type=int, default=1, help="Minute interval, default 1")
    fetch_kis.add_argument("--output", required=True, help="CSV output path")
    fetch_kis.add_argument(
        "--output-timezone",
        default="America/New_York",
        help="Timezone used when writing timestamps to CSV",
    )
    _add_kis_auth_args(fetch_kis)

    paper_account = subparsers.add_parser("paper-account", help="Fetch Alpaca paper account details")
    paper_account.add_argument("--api-key", help="Alpaca API key, defaults to APCA_API_KEY_ID")
    paper_account.add_argument("--api-secret", help="Alpaca API secret, defaults to APCA_API_SECRET_KEY")

    paper_orders = subparsers.add_parser("paper-list-orders", help="List Alpaca paper orders")
    paper_orders.add_argument("--status", default="open", help="Order status filter, default open")
    paper_orders.add_argument("--limit", type=int, default=50, help="Maximum number of orders")
    paper_orders.add_argument("--api-key", help="Alpaca API key, defaults to APCA_API_KEY_ID")
    paper_orders.add_argument("--api-secret", help="Alpaca API secret, defaults to APCA_API_SECRET_KEY")

    paper_positions = subparsers.add_parser("paper-list-positions", help="List Alpaca paper positions")
    paper_positions.add_argument("--api-key", help="Alpaca API key, defaults to APCA_API_KEY_ID")
    paper_positions.add_argument("--api-secret", help="Alpaca API secret, defaults to APCA_API_SECRET_KEY")

    paper_cancel = subparsers.add_parser("paper-cancel-order", help="Cancel a paper order by id")
    paper_cancel.add_argument("--order-id", required=True, help="Alpaca order id")
    paper_cancel.add_argument("--api-key", help="Alpaca API key, defaults to APCA_API_KEY_ID")
    paper_cancel.add_argument("--api-secret", help="Alpaca API secret, defaults to APCA_API_SECRET_KEY")

    paper_run = subparsers.add_parser("paper-run-once", help="Fetch today's bars, evaluate setup, and place a paper bracket order")
    paper_run.add_argument("--symbol", default="SPY", help="Ticker symbol, default SPY")
    paper_run.add_argument("--feed", default="iex", help="Historical data feed, default iex")
    paper_run.add_argument("--adjustment", default="split", help="Historical adjustment mode, default split")
    paper_run.add_argument("--config", dest="config_path", help="Path to JSON strategy config")
    paper_run.add_argument("--dry-run", action="store_true", help="Prepare payload without submitting order")
    paper_run.add_argument(
        "--now",
        help="Override current time with an ISO-8601 timestamp, useful for testing",
    )
    paper_run.add_argument("--api-key", help="Alpaca API key, defaults to APCA_API_KEY_ID")
    paper_run.add_argument("--api-secret", help="Alpaca API secret, defaults to APCA_API_SECRET_KEY")

    kis_balance = subparsers.add_parser("kis-balance", help="Fetch KIS overseas balance summary")
    kis_balance.add_argument("--country-code", default="840", help="Country code, default 840 for US")
    kis_balance.add_argument("--market-code", default="01", help="KIS market code, default 01 for NASDAQ")
    _add_kis_auth_args(kis_balance)

    kis_open_orders = subparsers.add_parser("kis-open-orders", help="List KIS overseas open orders")
    kis_open_orders.add_argument("--order-exchange", default="NASD", help="KIS order exchange code, default NASD")
    _add_kis_auth_args(kis_open_orders)

    kis_cancel = subparsers.add_parser("kis-cancel-order", help="Cancel a KIS overseas order by id")
    kis_cancel.add_argument("--symbol", required=True, help="Ticker symbol, for example SPY")
    kis_cancel.add_argument("--order-exchange", default="NASD", help="KIS order exchange code, default NASD")
    kis_cancel.add_argument("--order-id", required=True, help="Original KIS order number")
    kis_cancel.add_argument("--qty", required=True, type=int, help="Cancel quantity")
    _add_kis_auth_args(kis_cancel)

    kis_run = subparsers.add_parser(
        "kis-run-once",
        help="Fetch KIS minute bars, evaluate the setup, and optionally submit an entry-only order",
    )
    kis_run.add_argument("--symbol", default="SPY", help="Ticker symbol, default SPY")
    kis_run.add_argument("--quote-exchange", default="AMS", help="KIS quote exchange code, default AMS")
    kis_run.add_argument("--order-exchange", default="AMEX", help="KIS order exchange code, default AMEX")
    kis_run.add_argument("--country-code", default="840", help="Country code, default 840 for US")
    kis_run.add_argument("--market-code", default="05", help="KIS market code, default 05 for AMEX/NYSE Arca")
    kis_run.add_argument("--config", dest="config_path", help="Path to JSON strategy config")
    kis_run.add_argument(
        "--now",
        help="Override current time with an ISO-8601 timestamp, useful for testing",
    )
    kis_run.add_argument(
        "--submit-entry",
        action="store_true",
        help="Submit an entry order. Default is dry-run only because exit automation is separate.",
    )
    kis_run.add_argument("--state-path", help="Optional path to save KIS trade state JSON")
    _add_kis_auth_args(kis_run)

    kis_monitor = subparsers.add_parser(
        "kis-monitor-once",
        help="Load a saved KIS trade state and run one monitoring cycle",
    )
    kis_monitor.add_argument("--state-path", required=True, help="Path to a saved KIS trade state JSON")
    kis_monitor.add_argument(
        "--now",
        help="Override current time with an ISO-8601 timestamp, useful for testing",
    )
    kis_monitor.add_argument(
        "--submit-exit",
        action="store_true",
        help="Submit exit/cancel orders. Default is dry-run only.",
    )
    _add_kis_auth_args(kis_monitor)

    kis_monitor_loop = subparsers.add_parser(
        "kis-monitor-loop",
        help="Repeatedly monitor a saved KIS trade state until closed or max iterations",
    )
    kis_monitor_loop.add_argument("--state-path", required=True, help="Path to a saved KIS trade state JSON")
    kis_monitor_loop.add_argument("--poll-seconds", type=float, default=15.0, help="Seconds between polls")
    kis_monitor_loop.add_argument(
        "--max-iterations",
        type=int,
        default=0,
        help="Maximum poll iterations. 0 means run until terminal state.",
    )
    kis_monitor_loop.add_argument(
        "--submit-exit",
        action="store_true",
        help="Submit exit/cancel orders. Default is dry-run only.",
    )
    _add_kis_auth_args(kis_monitor_loop)

    telegram_updates = subparsers.add_parser(
        "telegram-get-updates",
        help="Fetch recent Telegram bot updates to inspect chat ids",
    )
    telegram_updates.add_argument("--limit", type=int, default=10, help="Maximum number of updates")
    telegram_updates.add_argument("--timeout", type=int, default=0, help="Long polling timeout in seconds")
    telegram_updates.add_argument(
        "--messages-only",
        action="store_true",
        help="Limit updates to message events for chat id discovery",
    )
    _add_telegram_args(telegram_updates, require_chat_id=False)

    telegram_test = subparsers.add_parser(
        "telegram-test",
        help="Send a Telegram test message",
    )
    telegram_test.add_argument(
        "--message",
        help="Custom Telegram test message",
    )
    telegram_test.add_argument(
        "--broker",
        default="한국투자증권",
        help="Broker label used when building the default test message",
    )
    telegram_test.add_argument(
        "--asset-class",
        default="미국주식",
        help="Asset class label used when building the default test message",
    )
    telegram_test.add_argument(
        "--symbol-tag",
        default="SPY",
        help="Symbol label used when building the default test message",
    )
    telegram_test.add_argument(
        "--parse-mode",
        choices=("Markdown", "MarkdownV2", "HTML"),
        help="Optional Telegram parse mode",
    )
    telegram_test.add_argument(
        "--disable-notification",
        action="store_true",
        help="Send the message silently",
    )
    _add_telegram_args(telegram_test, require_chat_id=False)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "backtest":
        config = StrategyConfig.from_file(Path(args.config_path)) if args.config_path else StrategyConfig()
        bars = load_bars_from_csv(
            path=Path(args.csv_path),
            default_symbol=config.symbol,
            assume_timezone=args.data_timezone,
        )
        report = BacktestRunner(config).run(bars)
        _print_report(report)
        if args.output_trades:
            _write_trades_csv(Path(args.output_trades), report.trades)
        return 0

    if args.command == "fetch-alpaca-bars":
        credentials = _resolve_alpaca_credentials(args.api_key, args.api_secret)
        client = AlpacaHistoricalBarsClient(credentials)
        start = _parse_utc_date(args.start_date)
        end = _parse_utc_date(args.end_date)
        bars = client.fetch_stock_bars(
            symbol=args.symbol,
            start=start,
            end=end,
            timeframe=args.timeframe,
            feed=args.feed,
            adjustment=args.adjustment,
            limit=args.limit,
        )
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        write_bars_to_csv(output_path, bars, output_timezone=args.output_timezone)
        print(f"Fetched bars     : {len(bars)}")
        print(f"Symbol           : {args.symbol}")
        print(f"Range            : {args.start_date} -> {args.end_date} (end exclusive)")
        print(f"Output           : {output_path}")
        return 0

    if args.command == "fetch-kis-bars":
        credentials = _resolve_kis_credentials(
            app_key=args.app_key,
            app_secret=args.app_secret,
            cano=args.cano,
            account_product_code=args.product_code,
            env=args.env,
            base_url=args.base_url,
        )
        auth_session = KISAuthSession(credentials)
        client = KISOverseasStockDataClient(auth_session)
        bars = client.fetch_recent_minute_bars(
            symbol=args.symbol,
            quote_exchange_code=args.quote_exchange,
            interval_minutes=args.interval,
            max_records=args.records,
            market_timezone="America/New_York",
        )
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        write_bars_to_csv(output_path, bars, output_timezone=args.output_timezone)
        print(f"Fetched bars     : {len(bars)}")
        print(f"Symbol           : {args.symbol}")
        print(f"Exchange         : {args.quote_exchange}")
        print(f"Output           : {output_path}")
        return 0

    if args.command == "paper-account":
        credentials = _resolve_alpaca_credentials(args.api_key, args.api_secret)
        client = AlpacaPaperTradingClient(credentials)
        print(json.dumps(client.get_account(), indent=2, sort_keys=True))
        return 0

    if args.command == "paper-list-orders":
        credentials = _resolve_alpaca_credentials(args.api_key, args.api_secret)
        client = AlpacaPaperTradingClient(credentials)
        orders = client.list_orders(status=args.status, limit=args.limit)
        print(json.dumps(orders, indent=2, sort_keys=True))
        return 0

    if args.command == "paper-list-positions":
        credentials = _resolve_alpaca_credentials(args.api_key, args.api_secret)
        client = AlpacaPaperTradingClient(credentials)
        print(json.dumps(client.list_positions(), indent=2, sort_keys=True))
        return 0

    if args.command == "paper-cancel-order":
        credentials = _resolve_alpaca_credentials(args.api_key, args.api_secret)
        client = AlpacaPaperTradingClient(credentials)
        print(json.dumps(client.cancel_order(args.order_id), indent=2, sort_keys=True))
        return 0

    if args.command == "paper-run-once":
        credentials = _resolve_alpaca_credentials(args.api_key, args.api_secret)
        config = StrategyConfig.from_file(Path(args.config_path)) if args.config_path else StrategyConfig(symbol=args.symbol)
        data_client = AlpacaHistoricalBarsClient(credentials)
        broker_client = AlpacaPaperTradingClient(credentials)
        bot = PaperTradingBot(config, data_client, broker_client)
        now = datetime.fromisoformat(args.now) if args.now else None
        result = bot.run_once(
            symbol=args.symbol,
            now=now,
            feed=args.feed,
            adjustment=args.adjustment,
            dry_run=args.dry_run,
        )
        payload = {
            "status": result.status,
            "message": result.message,
            "quantity": result.quantity,
            "setup": _serialize_setup(result.setup),
            "order_payload": result.order_payload,
            "order_response": result.order_response,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.command == "kis-balance":
        credentials = _resolve_kis_credentials(
            app_key=args.app_key,
            app_secret=args.app_secret,
            cano=args.cano,
            account_product_code=args.product_code,
            env=args.env,
            base_url=args.base_url,
        )
        auth_session = KISAuthSession(credentials)
        client = KISOverseasStockBrokerClient(auth_session)
        payload = client.get_present_balance(
            country_code=args.country_code,
            market_code=args.market_code,
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.command == "kis-open-orders":
        credentials = _resolve_kis_credentials(
            app_key=args.app_key,
            app_secret=args.app_secret,
            cano=args.cano,
            account_product_code=args.product_code,
            env=args.env,
            base_url=args.base_url,
        )
        auth_session = KISAuthSession(credentials)
        client = KISOverseasStockBrokerClient(auth_session)
        orders = client.list_open_orders(order_exchange_code=args.order_exchange)
        print(json.dumps(orders, indent=2, sort_keys=True))
        return 0

    if args.command == "kis-cancel-order":
        credentials = _resolve_kis_credentials(
            app_key=args.app_key,
            app_secret=args.app_secret,
            cano=args.cano,
            account_product_code=args.product_code,
            env=args.env,
            base_url=args.base_url,
        )
        auth_session = KISAuthSession(credentials)
        client = KISOverseasStockBrokerClient(auth_session)
        response = client.cancel_order(
            symbol=args.symbol,
            order_exchange_code=args.order_exchange,
            original_order_number=args.order_id,
            quantity=args.qty,
        )
        print(json.dumps(response, indent=2, sort_keys=True))
        return 0

    if args.command == "kis-run-once":
        notifier = _maybe_build_kis_telegram_notifier()
        credentials = _resolve_kis_credentials(
            app_key=args.app_key,
            app_secret=args.app_secret,
            cano=args.cano,
            account_product_code=args.product_code,
            env=args.env,
            base_url=args.base_url,
        )
        config = StrategyConfig.from_file(Path(args.config_path)) if args.config_path else StrategyConfig()
        config = replace(
            config,
            symbol=args.symbol,
            quote_exchange_code=args.quote_exchange,
            order_exchange_code=args.order_exchange,
            country_code=args.country_code,
            market_code=args.market_code,
        )
        auth_session = KISAuthSession(credentials)
        data_client = KISOverseasStockDataClient(auth_session)
        broker_client = KISOverseasStockBrokerClient(auth_session)
        bot = KISOverseasBot(config, data_client, broker_client)
        now = datetime.fromisoformat(args.now) if args.now else None
        state_path = Path(args.state_path) if args.state_path else None
        try:
            result = bot.run_once(
                symbol=args.symbol,
                quote_exchange_code=args.quote_exchange,
                order_exchange_code=args.order_exchange,
                now=now,
                dry_run=not args.submit_entry,
            )
            payload = {
                "status": result.status,
                "message": result.message,
                "quantity": result.quantity,
                "setup": _serialize_setup(result.setup),
                "order_payload": result.order_payload,
                "order_response": result.order_response,
            }
            state_path = _maybe_save_kis_trade_state(
                explicit_path=args.state_path,
                config=config,
                result=result,
                quote_exchange_code=args.quote_exchange,
                order_exchange_code=args.order_exchange,
                country_code=args.country_code,
                market_code=args.market_code,
                save_default=args.submit_entry,
                submitted=args.submit_entry,
                now=now,
            )
            if state_path is not None:
                payload["state_path"] = str(state_path)
            if notifier is not None:
                _safe_notify(
                    notifier.notify_run_once,
                    result=result,
                    state_path=state_path,
                    submitted=args.submit_entry,
                )
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        except Exception as exc:
            if notifier is not None:
                _safe_notify(
                    notifier.notify_error,
                    symbol=args.symbol,
                    command="kis-run-once",
                    error=exc,
                    state_path=state_path,
                )
            raise

    if args.command == "kis-monitor-once":
        notifier = _maybe_build_kis_telegram_notifier()
        credentials = _resolve_kis_credentials(
            app_key=args.app_key,
            app_secret=args.app_secret,
            cano=args.cano,
            account_product_code=args.product_code,
            env=args.env,
            base_url=args.base_url,
        )
        auth_session = KISAuthSession(credentials)
        data_client = KISOverseasStockDataClient(auth_session)
        broker_client = KISOverseasStockBrokerClient(auth_session)
        monitor = KISExitMonitor(data_client, broker_client)
        state_path = Path(args.state_path)
        state = load_kis_trade_state(state_path)
        now = datetime.fromisoformat(args.now) if args.now else None
        try:
            result = monitor.check_once(state, now=now, dry_run=not args.submit_exit)
            save_kis_trade_state(state_path, result.state)
            if notifier is not None:
                _safe_notify(
                    notifier.notify_monitor_result,
                    previous_state=state,
                    result=result,
                    state_path=state_path,
                )
            payload = {
                "status": result.status,
                "message": result.message,
                "state_path": str(state_path),
                "state": _serialize_kis_state(result.state),
                "quote": result.quote,
                "order_payload": result.order_payload,
                "order_response": result.order_response,
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        except Exception as exc:
            if notifier is not None:
                _safe_notify(
                    notifier.notify_error,
                    symbol=state.symbol,
                    command="kis-monitor-once",
                    error=exc,
                    state_path=state_path,
                )
            raise

    if args.command == "kis-monitor-loop":
        notifier = _maybe_build_kis_telegram_notifier()
        credentials = _resolve_kis_credentials(
            app_key=args.app_key,
            app_secret=args.app_secret,
            cano=args.cano,
            account_product_code=args.product_code,
            env=args.env,
            base_url=args.base_url,
        )
        auth_session = KISAuthSession(credentials)
        data_client = KISOverseasStockDataClient(auth_session)
        broker_client = KISOverseasStockBrokerClient(auth_session)
        monitor = KISExitMonitor(data_client, broker_client)
        state_path = Path(args.state_path)
        last_payload = None
        iteration = 0

        while True:
            iteration += 1
            state = load_kis_trade_state(state_path)
            try:
                result = monitor.check_once(state, dry_run=not args.submit_exit)
                save_kis_trade_state(state_path, result.state)
                if notifier is not None:
                    _safe_notify(
                        notifier.notify_monitor_result,
                        previous_state=state,
                        result=result,
                        state_path=state_path,
                    )
                last_payload = {
                    "iteration": iteration,
                    "status": result.status,
                    "message": result.message,
                    "state_path": str(state_path),
                    "state": _serialize_kis_state(result.state),
                    "quote": result.quote,
                    "order_payload": result.order_payload,
                    "order_response": result.order_response,
                }
            except Exception as exc:
                if notifier is not None:
                    _safe_notify(
                        notifier.notify_error,
                        symbol=state.symbol,
                        command="kis-monitor-loop",
                        error=exc,
                        state_path=state_path,
                    )
                raise

            if _should_stop_kis_monitor_loop(
                status=result.status,
                state=result.state,
                iteration=iteration,
                max_iterations=args.max_iterations,
            ):
                break
            time.sleep(max(args.poll_seconds, 0.0))

        print(json.dumps(last_payload, indent=2, sort_keys=True))
        return 0

    if args.command == "telegram-get-updates":
        credentials = _resolve_telegram_credentials(
            bot_token=args.bot_token,
            chat_id=args.chat_id,
        )
        client = TelegramBotClient(credentials)
        updates = client.get_updates(
            limit=args.limit,
            timeout=args.timeout,
            allowed_updates=["message"] if args.messages_only else None,
        )
        print(json.dumps(updates, indent=2, sort_keys=True))
        return 0

    if args.command == "telegram-test":
        credentials = _resolve_telegram_credentials(
            bot_token=args.bot_token,
            chat_id=args.chat_id,
        )
        client = TelegramBotClient(credentials)
        now = datetime.now(timezone.utc).isoformat()
        text = args.message or _build_telegram_test_message(
            broker=args.broker,
            asset_class=args.asset_class,
            symbol_tag=args.symbol_tag,
            timestamp=now,
        )
        result = client.send_message(
            text=text,
            parse_mode=args.parse_mode,
            disable_notification=args.disable_notification,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


def _parse_utc_date(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _add_kis_auth_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--app-key", help="KIS app key, defaults to KIS_APP_KEY")
    parser.add_argument("--app-secret", help="KIS app secret, defaults to KIS_APP_SECRET")
    parser.add_argument("--cano", help="KIS account number, defaults to KIS_CANO")
    parser.add_argument("--product-code", help="KIS account product code, defaults to KIS_ACNT_PRDT_CD")
    parser.add_argument("--env", choices=("demo", "real"), help="KIS environment, defaults to KIS_ENV or demo")
    parser.add_argument("--base-url", help="Optional KIS base URL override")


def _add_telegram_args(parser: argparse.ArgumentParser, *, require_chat_id: bool) -> None:
    parser.add_argument("--bot-token", help="Telegram bot token, defaults to TELEGRAM_BOT_TOKEN")
    parser.add_argument(
        "--chat-id",
        required=require_chat_id,
        help="Telegram chat id, defaults to TELEGRAM_CHAT_ID",
    )


def _resolve_alpaca_credentials(
    api_key: Optional[str],
    api_secret: Optional[str],
) -> AlpacaCredentials:
    resolved_key = api_key or os.getenv("APCA_API_KEY_ID")
    resolved_secret = api_secret or os.getenv("APCA_API_SECRET_KEY")
    if not resolved_key or not resolved_secret:
        raise SystemExit(
            "Alpaca credentials are required. Set APCA_API_KEY_ID/APCA_API_SECRET_KEY "
            "or pass --api-key and --api-secret."
        )
    return AlpacaCredentials(api_key=resolved_key, secret_key=resolved_secret)


def _resolve_kis_credentials(
    *,
    app_key: Optional[str],
    app_secret: Optional[str],
    cano: Optional[str],
    account_product_code: Optional[str],
    env: Optional[str],
    base_url: Optional[str],
) -> KISCredentials:
    resolved_app_key = app_key or os.getenv("KIS_APP_KEY")
    resolved_app_secret = app_secret or os.getenv("KIS_APP_SECRET")
    resolved_cano = cano or os.getenv("KIS_CANO")
    resolved_product_code = account_product_code or os.getenv("KIS_ACNT_PRDT_CD")
    resolved_env = env or os.getenv("KIS_ENV") or "demo"
    resolved_base_url = base_url or os.getenv("KIS_BASE_URL")

    if not resolved_app_key or not resolved_app_secret or not resolved_cano or not resolved_product_code:
        raise SystemExit(
            "KIS credentials are required. Set KIS_APP_KEY/KIS_APP_SECRET/KIS_CANO/KIS_ACNT_PRDT_CD "
            "or pass --app-key, --app-secret, --cano, and --product-code."
        )

    return KISCredentials(
        app_key=resolved_app_key,
        app_secret=resolved_app_secret,
        cano=resolved_cano,
        account_product_code=resolved_product_code,
        env=resolved_env,
        base_url=resolved_base_url,
    )


def _resolve_telegram_credentials(
    *,
    bot_token: Optional[str],
    chat_id: Optional[str],
) -> TelegramCredentials:
    resolved_bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
    resolved_chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if not resolved_bot_token:
        raise SystemExit(
            "Telegram bot token is required. Set TELEGRAM_BOT_TOKEN or pass --bot-token."
        )
    return TelegramCredentials(
        bot_token=resolved_bot_token,
        chat_id=resolved_chat_id,
    )


def _maybe_build_kis_telegram_notifier() -> Optional[KISTelegramNotifier]:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        return None
    client = TelegramBotClient(
        TelegramCredentials(
            bot_token=bot_token,
            chat_id=chat_id,
        )
    )
    return KISTelegramNotifier(client)


def _safe_notify(callback, /, *args, **kwargs) -> bool:
    try:
        callback(*args, **kwargs)
        return True
    except Exception:
        return False


def _serialize_setup(setup):
    if setup is None:
        return None
    return {
        "symbol": setup.symbol,
        "session_date": setup.session_date.isoformat(),
        "breakout_bar_time": setup.breakout_bar_time.isoformat(),
        "setup_bar_time": setup.setup_bar_time.isoformat(),
        "detect_time": setup.detect_time.isoformat(),
        "or_high": setup.or_high,
        "or_low": setup.or_low,
        "fvg_low": setup.fvg_low,
        "fvg_high": setup.fvg_high,
        "entry_price": setup.entry_price,
        "stop_price": setup.stop_price,
        "target_price": setup.target_price,
        "risk_per_share": setup.risk_per_share,
    }


def _serialize_kis_state(state):
    if state is None:
        return None
    return state.to_dict()


def _build_telegram_test_message(
    *,
    broker: str,
    asset_class: str,
    symbol_tag: str,
    timestamp: str,
) -> str:
    header = f"[{broker}] [{asset_class}] [{symbol_tag}]"
    return f"{header}\nstock_auto telegram test\nUTC: {timestamp}"


def _maybe_save_kis_trade_state(
    *,
    explicit_path: Optional[str],
    config: StrategyConfig,
    result,
    quote_exchange_code: str,
    order_exchange_code: str,
    country_code: str,
    market_code: str,
    save_default: bool,
    submitted: bool,
    now: Optional[datetime],
):
    if result.setup is None or result.quantity is None:
        return None
    if not explicit_path and not save_default:
        return None

    state_path = Path(explicit_path) if explicit_path else default_kis_state_path(
        Path("state"),
        symbol=result.setup.symbol,
        session_date=result.setup.session_date,
    )
    phase = "entry_submitted" if submitted and result.order_response else "entry_prepared"
    state = build_kis_trade_state(
        config=config,
        setup=result.setup,
        quantity=result.quantity,
        quote_exchange_code=quote_exchange_code,
        order_exchange_code=order_exchange_code,
        country_code=country_code,
        market_code=market_code,
        entry_order_response=result.order_response,
        phase=phase,
        status=result.status,
        message=result.message,
        now=now,
    )
    save_kis_trade_state(state_path, state)
    return state_path


def _should_stop_kis_monitor_loop(*, status: str, state, iteration: int, max_iterations: int) -> bool:
    if max_iterations > 0 and iteration >= max_iterations:
        return True
    if is_kis_state_terminal(state):
        return True
    return status in {
        "exit_signal_dry_run",
        "would_cancel_stale_entry",
        "would_cancel_remaining_entry",
        "entry_cancelled",
        "orphan_exit_order_exists",
        "conflicting_symbol_orders",
        "entry_not_submitted",
    }


def _print_report(report) -> None:
    print(f"Starting equity : {report.starting_equity:,.2f}")
    print(f"Ending equity   : {report.ending_equity:,.2f}")
    print(f"Total PnL       : {report.total_pnl:,.2f}")
    print(f"Return          : {report.return_pct * 100:.2f}%")
    print(f"Trades          : {report.total_trades}")
    print(f"Win rate        : {report.win_rate * 100:.2f}%")
    print(f"Average R       : {report.average_r:.2f}")
    print(f"Expectancy      : {report.expectancy:,.2f}")
    print(f"Profit factor   : {report.profit_factor:.2f}")
    print(f"Max drawdown    : {report.max_drawdown * 100:.2f}%")
    print(f"Daily notes     : {len(report.daily_notes)}")


def _write_trades_csv(path: Path, trades: Sequence[Trade]) -> None:
    fieldnames = [
        "symbol",
        "session_date",
        "detect_time",
        "entry_time",
        "exit_time",
        "entry_price",
        "exit_price",
        "stop_price",
        "target_price",
        "quantity",
        "pnl",
        "r_multiple",
        "exit_reason",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for trade in trades:
            writer.writerow(
                {
                    "symbol": trade.symbol,
                    "session_date": trade.session_date.isoformat(),
                    "detect_time": trade.detect_time.isoformat(),
                    "entry_time": trade.entry_time.isoformat(),
                    "exit_time": trade.exit_time.isoformat(),
                    "entry_price": f"{trade.entry_price:.4f}",
                    "exit_price": f"{trade.exit_price:.4f}",
                    "stop_price": f"{trade.stop_price:.4f}",
                    "target_price": f"{trade.target_price:.4f}",
                    "quantity": trade.quantity,
                    "pnl": f"{trade.pnl:.4f}",
                    "r_multiple": f"{trade.r_multiple:.4f}",
                    "exit_reason": trade.exit_reason,
                }
            )

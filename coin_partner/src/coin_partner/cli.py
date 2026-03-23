from __future__ import annotations

import argparse
import logging
from datetime import datetime
from pprint import pformat
from typing import Optional

from coin_partner.bot import TradingBot
from coin_partner.config import AppConfig
from coin_partner.risk import RiskManager
from coin_partner.state import StateStore
from coin_partner.telegram import TelegramNotifier
from coin_partner.upbit import UpbitAPIError, UpbitClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Upbit spot auto-trading bot")
    parser.add_argument("--config", default="config.toml", help="Path to TOML configuration")
    parser.add_argument("--once", action="store_true", help="Run a single cycle")
    parser.add_argument("--status", action="store_true", help="Print current stored state")
    parser.add_argument("--check-upbit", action="store_true", help="Run a read-only authenticated Upbit connection check")
    parser.add_argument("--manual-buy-market", help="Place a one-shot live market buy for the given market, e.g. KRW-BTC")
    parser.add_argument("--manual-buy-krw", type=int, help="KRW amount for the one-shot live market buy")
    parser.add_argument("--live-order-confirm", help="Exact confirmation token required for one-shot live orders")
    parser.add_argument("--import-order-id", help="Import a filled live order into local bot state by Upbit order UUID")
    args = parser.parse_args()

    config = AppConfig.load(args.config)
    logging.basicConfig(
        level=getattr(logging, config.bot.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    bot = TradingBot(config)
    if args.status:
        state = bot.store.load()
        print(pformat(state.to_dict()))
        return

    if args.check_upbit:
        check_upbit_connection(config)
        return

    if args.manual_buy_market or args.manual_buy_krw or args.live_order_confirm:
        run_manual_market_buy(
            config=config,
            market=args.manual_buy_market,
            amount_krw=args.manual_buy_krw,
            confirmation=args.live_order_confirm,
        )
        return

    if args.import_order_id:
        import_live_order(config, args.import_order_id)
        return

    if args.once:
        bot.run_once()
        return
    bot.run_forever()


def check_upbit_connection(config: AppConfig) -> None:
    client = UpbitClient(
        base_url=config.upbit.base_url,
        timezone=config.bot.timezone,
        access_key=config.upbit.access_key,
        secret_key=config.upbit.secret_key,
        timeout_seconds=config.upbit.request_timeout_seconds,
    )
    try:
        accounts = client.get_accounts()
    except UpbitAPIError as exc:
        raise SystemExit("Upbit connection check failed: {0}".format(exc))

    non_zero_assets = []
    krw_balance = 0.0
    for row in accounts:
        currency = str(row.get("currency", ""))
        balance = float(row.get("balance", 0.0))
        locked = float(row.get("locked", 0.0))
        total = balance + locked
        if currency == "KRW":
            krw_balance = total
        if total > 0:
            non_zero_assets.append(
                {
                    "currency": currency,
                    "balance": round(balance, 8),
                    "locked": round(locked, 8),
                    "unit_currency": row.get("unit_currency"),
                }
            )

    print("Upbit connection check succeeded.")
    print("accounts={0}".format(len(accounts)))
    print("krw_balance={0:,.0f}".format(krw_balance))
    print("non_zero_assets=")
    print(pformat(non_zero_assets))


def run_manual_market_buy(config: AppConfig, market: Optional[str], amount_krw: Optional[int], confirmation: Optional[str]) -> None:
    if not market or not amount_krw:
        raise SystemExit("--manual-buy-market and --manual-buy-krw must be provided together")
    if amount_krw < 5000:
        raise SystemExit("manual live buy amount must be at least 5000 KRW")

    expected_confirmation = build_live_buy_confirmation(market, amount_krw)
    if confirmation != expected_confirmation:
        raise SystemExit(
            "live order blocked. Re-run with --live-order-confirm '{0}'".format(expected_confirmation)
        )

    client = UpbitClient(
        base_url=config.upbit.base_url,
        timezone=config.bot.timezone,
        access_key=config.upbit.access_key,
        secret_key=config.upbit.secret_key,
        timeout_seconds=config.upbit.request_timeout_seconds,
    )

    try:
        krw_balance = client.get_krw_balance()
    except UpbitAPIError as exc:
        raise SystemExit("Upbit balance check failed before order: {0}".format(exc))

    if krw_balance < amount_krw:
        raise SystemExit(
            "not enough KRW balance for live buy. balance={0:,.0f} needed={1:,.0f}".format(
                krw_balance,
                amount_krw,
            )
        )

    print("Placing live market buy: market={0} krw={1:,.0f}".format(market, amount_krw))
    try:
        fill = client.create_market_buy(market, amount_krw)
    except UpbitAPIError as exc:
        raise SystemExit("Upbit live market buy failed: {0}".format(exc))

    print("Live market buy succeeded.")
    print("market={0}".format(fill.market))
    print("order_id={0}".format(fill.order_id))
    print("filled_volume={0:.8f}".format(fill.volume))
    print("average_price={0:,.0f}".format(fill.average_price))
    print("fee_krw={0:,.0f}".format(fill.fee_krw))


def build_live_buy_confirmation(market: str, amount_krw: int) -> str:
    return "BUY:{0}:{1}".format(market, amount_krw)


def is_fill_finalized_order_state(order_state: str) -> bool:
    return order_state in {"done", "cancel"}


def import_live_order(config: AppConfig, order_id: str) -> None:
    client = UpbitClient(
        base_url=config.upbit.base_url,
        timezone=config.bot.timezone,
        access_key=config.upbit.access_key,
        secret_key=config.upbit.secret_key,
        timeout_seconds=config.upbit.request_timeout_seconds,
    )
    store = StateStore(
        config.storage.state_file,
        timezone=config.bot.timezone,
        paper_starting_cash_krw=config.bot.paper_starting_cash_krw,
    )
    risk = RiskManager(config)
    notifier = TelegramNotifier.from_app_config(config)

    state = store.load()

    if len(state.positions) >= config.risk.max_open_positions:
        raise SystemExit(
            "local state already reached max open positions: count={0} max={1}".format(
                len(state.positions),
                config.risk.max_open_positions,
            )
        )
    for position in state.positions:
        if position.order_id == order_id:
            raise SystemExit("order is already imported into local state")

    try:
        order = client.get_order(order_id)
    except UpbitAPIError as exc:
        raise SystemExit("Upbit order lookup failed: {0}".format(exc))

    if str(order.get("side")) != "bid":
        raise SystemExit("only bid orders can be imported as open positions")

    order_state = str(order.get("state"))
    market = str(order.get("market"))
    executed_volume = float(order.get("executed_volume") or 0.0)
    paid_fee = float(order.get("paid_fee") or 0.0)
    if not is_fill_finalized_order_state(order_state):
        raise SystemExit("order is not fill-finalized yet; current state={0}".format(order_state))
    if executed_volume <= 0:
        raise SystemExit("order has no executed volume")

    total_funds = 0.0
    for trade in order.get("trades") or []:
        if trade.get("funds") is not None:
            total_funds += float(trade.get("funds"))
        elif trade.get("price") is not None and trade.get("volume") is not None:
            total_funds += float(trade.get("price")) * float(trade.get("volume"))

    if total_funds <= 0:
        raise SystemExit("order funds could not be calculated from response")

    average_price = total_funds / executed_volume
    created_at_raw = str(order.get("created_at"))
    opened_at = parse_exchange_datetime(created_at_raw)
    position = risk.build_position(
        market=market,
        entry_price=average_price,
        volume=executed_volume,
        invested_krw=total_funds,
        now=opened_at,
        order_id=order_id,
        entry_fee_krw=paid_fee,
    )
    state.positions.append(position)

    local_now = datetime.now(risk.tz)
    store.ensure_trading_day(state, local_now)
    if opened_at.astimezone(risk.tz).date() == state.daily.trading_date:
        state.daily.trade_count += 1
    state.history.append(
        {
            "type": "entry_import",
            "market": market,
            "at": opened_at.isoformat(),
            "order_id": order_id,
            "trade_count": state.daily.trade_count,
            "invested_krw": round(total_funds, 2),
            "entry_fee_krw": round(paid_fee, 2),
            "volume": round(executed_volume, 8),
        }
    )
    store.save(state)
    notifier.notify_entry(position, state)

    print("Imported live order into local state.")
    print("market={0}".format(position.market))
    print("order_id={0}".format(position.order_id))
    print("opened_at={0}".format(position.opened_at.isoformat()))
    print("entry_price={0:,.0f}".format(position.entry_price))
    print("invested_krw={0:,.0f}".format(position.invested_krw))
    print("volume={0:.8f}".format(position.volume))
    print("trade_count={0}".format(state.daily.trade_count))
    print("open_positions={0}".format(len(state.positions)))


def parse_exchange_datetime(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        raise SystemExit("unsupported exchange datetime format: {0}".format(value))


if __name__ == "__main__":
    main()

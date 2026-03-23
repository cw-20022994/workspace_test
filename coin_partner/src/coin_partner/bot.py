from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, time as clock_time
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from coin_partner.config import AppConfig
from coin_partner.models import BotState, Position
from coin_partner.risk import RiskManager
from coin_partner.state import StateStore
from coin_partner.strategy import SpotStrategy
from coin_partner.telegram import TelegramNotifier
from coin_partner.upbit import UpbitClient, UpbitAPIError


logger = logging.getLogger(__name__)


@dataclass
class PaperFill:
    market: str
    side: str
    volume: float
    average_price: float
    fee_krw: float


class TradingBot:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.tz = ZoneInfo(config.bot.timezone)
        self.client = UpbitClient(
            base_url=config.upbit.base_url,
            timezone=config.bot.timezone,
            access_key=config.upbit.access_key,
            secret_key=config.upbit.secret_key,
            timeout_seconds=config.upbit.request_timeout_seconds,
        )
        self.store = StateStore(
            config.storage.state_file,
            timezone=config.bot.timezone,
            paper_starting_cash_krw=config.bot.paper_starting_cash_krw,
        )
        self.strategy = SpotStrategy(config.strategy, config.bot.timezone)
        self.risk = RiskManager(config)
        self.notifier = TelegramNotifier.from_app_config(config)

    def run_forever(self) -> None:
        while True:
            self.run_once()
            time.sleep(self.config.bot.poll_interval_seconds)

    def run_once(self) -> None:
        now = datetime.now(self.tz)
        state = self.store.load()
        self._maybe_send_daily_summary(state, now)
        self.store.ensure_trading_day(state, now)
        tickers: Dict[str, float] = {}

        try:
            tickers = self.client.get_tickers(self.config.strategy.markets)
            self._handle_open_positions(state, tickers, now)
            self._handle_entry(state, tickers, now)
        except UpbitAPIError as exc:
            logger.exception("Upbit API call failed")
            self.notifier.notify_error("Upbit API call failed: {0}".format(exc), now)
        except Exception as exc:
            logger.exception("Unexpected bot error")
            self.notifier.notify_error("Unexpected bot error: {0}".format(exc), now)
        finally:
            self._maybe_send_heartbeat(state, now, tickers)
            self.store.save(state)

    def _handle_open_positions(self, state: BotState, tickers: Dict[str, float], now: datetime) -> None:
        if not state.positions:
            return

        remaining_positions: List[Position] = []
        for position in state.positions:
            market = position.market
            current_price = tickers.get(market)
            if current_price is None:
                logger.warning("No ticker price for open position market %s", market)
                remaining_positions.append(position)
                continue

            self.risk.arm_breakeven_if_needed(position, current_price)
            decision = self.risk.evaluate_exit(position, current_price, now)
            if not decision.should_exit:
                remaining_positions.append(position)
                continue

            if self.config.bot.mode == "paper":
                fill = self._paper_sell(position, current_price)
                state.paper_cash_krw += self._paper_exit_value(fill)
            else:
                fill = self.client.create_market_sell(market, position.volume)
            pnl_krw = self._realized_pnl(position, fill.average_price, fill.fee_krw)
            was_stopped = state.daily.stopped_for_day
            self.risk.register_exit(state, market, decision.reason or "unknown", pnl_krw, now)
            logger.info(
                "Exit %s %s at %.2f pnl=%.2f KRW reason=%s",
                market,
                fill.side,
                fill.average_price,
                pnl_krw,
                decision.reason,
            )
            self.notifier.notify_exit(
                position=position,
                exit_price=fill.average_price,
                reason=decision.reason or "unknown",
                pnl_krw=pnl_krw,
                state=state,
            )
            if not was_stopped and state.daily.stopped_for_day:
                self.notifier.notify_daily_stop(state)

        state.positions = remaining_positions

    def _handle_entry(self, state: BotState, tickers: Dict[str, float], now: datetime) -> None:
        if not self.config.bot.allow_new_entries:
            logger.info("New entries are disabled by config; managing exits only")
            return

        available_krw = self._available_krw(state)
        capital_limit_remaining_krw = self._capital_limit_remaining_krw(state)
        for market in self.config.strategy.markets:
            candles_5m = self.client.get_minute_candles(market, unit=5, count=200)
            candles_1h = self.client.get_minute_candles(market, unit=60, count=200)
            last_processed = self._parse_optional_datetime(state.last_processed_5m.get(market))
            current_price = tickers.get(market)
            if current_price is None:
                continue

            evaluation = self.strategy.evaluate_market(
                market=market,
                candles_5m=candles_5m,
                candles_1h=candles_1h,
                current_price=current_price,
                now=now,
                last_processed_5m_start=last_processed,
            )
            if evaluation.latest_completed_5m_start is not None:
                state.last_processed_5m[market] = evaluation.latest_completed_5m_start.isoformat()

            if not evaluation.decision.should_enter:
                reasons = evaluation.decision.reasons
                if reasons == ["already_processed"]:
                    logger.debug("No entry %s: %s", market, ",".join(reasons))
                else:
                    logger.info("No entry %s: %s", market, ",".join(reasons))
                continue

            allowed, reason = self.risk.can_enter(
                state,
                market,
                now,
                available_krw,
                capital_limit_remaining_krw=capital_limit_remaining_krw,
            )
            if not allowed:
                logger.info("Entry blocked for %s: %s", market, reason)
                if reason == "market_cooldown_active":
                    continue
                return

            if self.config.bot.mode == "paper":
                fill = self._paper_buy(market, current_price)
                state.paper_cash_krw -= self.config.strategy.entry_amount_krw + fill.fee_krw
                position = self.risk.build_position(
                    market=market,
                    entry_price=fill.average_price,
                    volume=fill.volume,
                    invested_krw=self.config.strategy.entry_amount_krw,
                    now=now,
                    entry_fee_krw=fill.fee_krw,
                )
            else:
                live_fill = self.client.create_market_buy(market, self.config.strategy.entry_amount_krw)
                position = self.risk.build_position(
                    market=market,
                    entry_price=live_fill.average_price,
                    volume=live_fill.volume,
                    invested_krw=self.config.strategy.entry_amount_krw,
                    now=now,
                    order_id=live_fill.order_id,
                    entry_fee_krw=live_fill.fee_krw,
                )

            state.positions.append(position)
            self.risk.register_entry(state, market)
            logger.info(
                "Enter %s at %.2f volume=%.8f open_positions=%d reasons=%s",
                market,
                position.entry_price,
                position.volume,
                len(state.positions),
                ",".join(evaluation.decision.reasons),
            )
            self.notifier.notify_entry(position, state)
            return

    def _maybe_send_daily_summary(self, state: BotState, now: datetime) -> None:
        summary_date = state.daily.trading_date
        already_sent = state.last_daily_summary_date == summary_date.isoformat()
        if already_sent:
            return

        local_day = now.astimezone(self.tz).date()
        summary_cutoff = clock_time(
            hour=self.config.telegram.daily_summary_hour,
            minute=self.config.telegram.daily_summary_minute,
        )
        now_local_time = now.astimezone(self.tz).time()

        should_send = False
        if summary_date < local_day:
            should_send = True
        elif summary_date == local_day and now_local_time >= summary_cutoff:
            should_send = True

        if not should_send:
            return

        wins, losses, best_trade, worst_trade = self._daily_trade_stats(state, summary_date)
        sent = self.notifier.notify_daily_summary(
            summary_date=summary_date.isoformat(),
            state=state,
            wins=wins,
            losses=losses,
            best_trade_pnl_krw=best_trade,
            worst_trade_pnl_krw=worst_trade,
        )
        if sent:
            state.last_daily_summary_date = summary_date.isoformat()

    def _maybe_send_heartbeat(
        self,
        state: BotState,
        now: datetime,
        tickers: Dict[str, float],
    ) -> None:
        if not (self.notifier.settings.enabled and self.notifier.settings.notify_heartbeat):
            return

        last_heartbeat = self._parse_optional_datetime(state.last_heartbeat_at)
        if last_heartbeat is not None:
            elapsed_seconds = (now - last_heartbeat).total_seconds()
            if elapsed_seconds < self.config.telegram.heartbeat_interval_minutes * 60:
                return

        mark_prices = {position.market: tickers.get(position.market) for position in state.positions}
        sent = self.notifier.notify_heartbeat(state=state, now=now, mark_prices=mark_prices)
        if sent:
            state.last_heartbeat_at = now.isoformat()

    def _daily_trade_stats(self, state: BotState, target_date: date) -> Tuple[int, int, float, float]:
        exit_pnls: List[float] = []
        target_iso = target_date.isoformat()
        for event in state.history:
            if event.get("type") != "exit":
                continue
            event_at = str(event.get("at", ""))
            if not event_at.startswith(target_iso):
                continue
            exit_pnls.append(float(event.get("pnl_krw", 0.0)))

        wins = sum(1 for value in exit_pnls if value > 0)
        losses = sum(1 for value in exit_pnls if value < 0)
        best_trade = max(exit_pnls) if exit_pnls else 0.0
        worst_trade = min(exit_pnls) if exit_pnls else 0.0
        return wins, losses, best_trade, worst_trade

    def _available_krw(self, state: BotState) -> float:
        if self.config.bot.mode == "paper":
            return state.paper_cash_krw
        krw_balance = self.client.get_krw_balance()
        capital_limit_remaining_krw = self._capital_limit_remaining_krw(state)
        if capital_limit_remaining_krw is None:
            return krw_balance
        return min(krw_balance, capital_limit_remaining_krw)

    def _capital_limit_remaining_krw(self, state: BotState) -> Optional[float]:
        if self.config.bot.mode != "live":
            return None
        if self.config.bot.live_capital_limit_krw is None:
            return None
        deployed_krw = sum(position.invested_krw + position.entry_fee_krw for position in state.positions)
        return max(self.config.bot.live_capital_limit_krw - deployed_krw, 0.0)

    def _paper_buy(self, market: str, market_price: float) -> PaperFill:
        entry_notional = self.config.strategy.entry_amount_krw
        fee = entry_notional * self.config.bot.paper_fee_rate
        buy_price = market_price * (1 + self.config.bot.paper_slippage_pct)
        volume = max(entry_notional / buy_price, 0.0)
        return PaperFill(
            market=market,
            side="bid",
            volume=volume,
            average_price=buy_price,
            fee_krw=fee,
        )

    def _paper_sell(self, position: Position, market_price: float) -> PaperFill:
        sell_price = market_price * (1 - self.config.bot.paper_slippage_pct)
        gross = position.volume * sell_price
        fee = gross * self.config.bot.paper_fee_rate
        return PaperFill(
            market=position.market,
            side="ask",
            volume=position.volume,
            average_price=sell_price,
            fee_krw=fee,
        )

    def _realized_pnl(self, position: Position, exit_price: float, exit_fee_krw: float) -> float:
        gross_exit = position.volume * exit_price
        net_exit = gross_exit - exit_fee_krw
        net_entry = position.invested_krw + position.entry_fee_krw
        return net_exit - net_entry

    def _paper_exit_value(self, fill: PaperFill) -> float:
        gross_exit = fill.volume * fill.average_price
        return gross_exit - fill.fee_krw

    def _parse_optional_datetime(self, value: Optional[str]) -> Optional[datetime]:
        return datetime.fromisoformat(value) if value else None

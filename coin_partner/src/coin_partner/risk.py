from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from coin_partner.config import AppConfig
from coin_partner.models import BotState, ExitDecision, Position


class RiskManager:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.tz = ZoneInfo(config.bot.timezone)

    def can_enter(
        self,
        state: BotState,
        market: str,
        now: datetime,
        available_krw: float,
        capital_limit_remaining_krw: Optional[float] = None,
    ) -> Tuple[bool, str]:
        daily = state.daily
        risk = self.config.risk
        strategy = self.config.strategy

        if any(position.market == market for position in state.positions):
            return False, "market_position_open"
        if len(state.positions) >= risk.max_open_positions:
            return False, "max_open_positions_reached"
        if daily.stopped_for_day:
            return False, "stopped_for_day"
        if risk.max_trades_per_day > 0 and daily.trade_count >= risk.max_trades_per_day:
            return False, "max_trades_reached"
        if daily.realized_pnl_krw <= -risk.daily_loss_limit_krw:
            return False, "daily_loss_limit_reached"
        if risk.max_consecutive_stop_losses > 0 and daily.consecutive_stop_losses >= risk.max_consecutive_stop_losses:
            return False, "max_consecutive_losses_reached"
        if daily.cooldown_until and now < daily.cooldown_until:
            return False, "global_cooldown_active"

        market_cooldown_raw = daily.market_cooldowns.get(market)
        if market_cooldown_raw:
            market_cooldown = datetime.fromisoformat(market_cooldown_raw)
            if now < market_cooldown:
                return False, "market_cooldown_active"

        required_cash = strategy.entry_amount_krw + risk.min_krw_balance_buffer
        if capital_limit_remaining_krw is not None and capital_limit_remaining_krw < required_cash:
            return False, "live_capital_limit_reached"
        if available_krw < required_cash:
            return False, "not_enough_cash"
        return True, "ok"

    def build_position(self, market: str, entry_price: float, volume: float, invested_krw: float, now: datetime, order_id: Optional[str] = None, entry_fee_krw: float = 0.0) -> Position:
        return Position(
            market=market,
            volume=volume,
            entry_price=entry_price,
            invested_krw=invested_krw,
            opened_at=now,
            stop_price=entry_price * (1 - self.config.risk.stop_loss_pct),
            take_profit_price=entry_price * (1 + self.config.risk.take_profit_pct),
            order_id=order_id,
            entry_fee_krw=entry_fee_krw,
        )

    def evaluate_exit(self, position: Position, current_price: float, now: datetime) -> ExitDecision:
        pnl_pct = (current_price / position.entry_price) - 1
        effective_stop = position.stop_price
        if pnl_pct >= self.config.risk.breakeven_trigger_pct:
            effective_stop = max(effective_stop, position.entry_price * (1 + self.config.risk.breakeven_offset_pct))

        if current_price <= effective_stop:
            return ExitDecision(True, "stop_loss", pnl_pct, effective_stop)
        if current_price >= position.take_profit_price:
            return ExitDecision(True, "take_profit", pnl_pct, effective_stop)

        early_exit = timedelta(minutes=self.config.risk.early_exit_check_minutes)
        if early_exit.total_seconds() > 0 and now - position.opened_at >= early_exit:
            if pnl_pct < self.config.risk.early_exit_min_pnl_pct:
                return ExitDecision(True, "stalled_trade_exit", pnl_pct, effective_stop)

        max_hold = timedelta(minutes=self.config.risk.max_hold_minutes)
        if now - position.opened_at >= max_hold:
            return ExitDecision(True, "time_exit", pnl_pct, effective_stop)
        return ExitDecision(False, pnl_pct=pnl_pct, stop_price=effective_stop)

    def arm_breakeven_if_needed(self, position: Position, current_price: float) -> None:
        pnl_pct = (current_price / position.entry_price) - 1
        if pnl_pct >= self.config.risk.breakeven_trigger_pct:
            position.breakeven_armed = True
            position.stop_price = max(
                position.stop_price,
                position.entry_price * (1 + self.config.risk.breakeven_offset_pct),
            )

    def register_entry(self, state: BotState, market: str) -> None:
        state.daily.trade_count += 1
        state.history.append(
            {
                "type": "entry",
                "market": market,
                "at": datetime.now(self.tz).isoformat(),
                "trade_count": state.daily.trade_count,
            }
        )

    def register_exit(self, state: BotState, market: str, reason: str, pnl_krw: float, now: datetime) -> None:
        daily = state.daily
        risk = self.config.risk
        daily.realized_pnl_krw += pnl_krw
        if pnl_krw < 0:
            daily.consecutive_stop_losses += 1
            daily.cooldown_until = now + timedelta(minutes=risk.cooldown_after_stop_minutes)
        else:
            daily.consecutive_stop_losses = 0
            daily.cooldown_until = now + timedelta(minutes=risk.cooldown_after_take_profit_minutes)

        daily.market_cooldowns[market] = (now + timedelta(minutes=risk.same_market_cooldown_minutes)).isoformat()
        if daily.realized_pnl_krw <= -risk.daily_loss_limit_krw:
            daily.stopped_for_day = True
        if risk.max_consecutive_stop_losses > 0 and daily.consecutive_stop_losses >= risk.max_consecutive_stop_losses:
            daily.stopped_for_day = True

        state.history.append(
            {
                "type": "exit",
                "market": market,
                "reason": reason,
                "at": now.isoformat(),
                "pnl_krw": round(pnl_krw, 2),
                "realized_pnl_krw": round(daily.realized_pnl_krw, 2),
                "stopped_for_day": daily.stopped_for_day,
            }
        )

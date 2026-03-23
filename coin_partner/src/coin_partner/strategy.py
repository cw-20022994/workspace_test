from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo

from coin_partner.config import StrategyConfig
from coin_partner.indicators import average, ema, rsi
from coin_partner.models import Candle, SignalDecision


@dataclass
class StrategyEvaluation:
    decision: SignalDecision
    latest_completed_5m_start: Optional[datetime]


class SpotStrategy:
    def __init__(self, config: StrategyConfig, timezone: str) -> None:
        self.config = config
        self.tz = ZoneInfo(timezone)

    def evaluate_market(
        self,
        market: str,
        candles_5m: List[Candle],
        candles_1h: List[Candle],
        current_price: float,
        now: datetime,
        last_processed_5m_start: Optional[datetime],
    ) -> StrategyEvaluation:
        completed_5m = self._completed_candles(candles_5m, now, 5)
        completed_1h = self._completed_candles(candles_1h, now, 60)

        latest_completed = completed_5m[-1].start_time if completed_5m else None
        if latest_completed is None:
            return StrategyEvaluation(
                decision=SignalDecision(market=market, should_enter=False, evaluated_candle_start=None, reasons=["not_enough_5m_candles"]),
                latest_completed_5m_start=None,
            )
        if last_processed_5m_start and latest_completed <= last_processed_5m_start:
            return StrategyEvaluation(
                decision=SignalDecision(market=market, should_enter=False, evaluated_candle_start=latest_completed, reasons=["already_processed"]),
                latest_completed_5m_start=latest_completed,
            )

        reasons: List[str] = []
        if len(completed_5m) < 25 or len(completed_1h) < 60:
            reasons.append("not_enough_history")
            return StrategyEvaluation(
                decision=SignalDecision(market=market, should_enter=False, evaluated_candle_start=latest_completed, reasons=reasons),
                latest_completed_5m_start=latest_completed,
            )

        closes_1h = [c.close_price for c in completed_1h]
        ema20_1h = ema(closes_1h, 20)
        ema50_1h = ema(closes_1h, 50)
        trend_ema20 = ema20_1h[-1]
        trend_ema50 = ema50_1h[-1]
        uses_relaxed_hourly_trend = market in self.config.relaxed_hourly_trend_markets
        if trend_ema20 is None or trend_ema50 is None:
            reasons.append("missing_hourly_ema")
        elif uses_relaxed_hourly_trend:
            if current_price <= trend_ema20:
                reasons.append("price_below_hourly_ema20")
            elif not self._ema_is_rising(ema20_1h, self.config.hourly_ema20_rising_bars):
                reasons.append("hourly_ema20_not_rising")
        else:
            if trend_ema20 <= trend_ema50:
                reasons.append("hourly_trend_down")
            elif current_price <= trend_ema20:
                reasons.append("price_below_hourly_ema20")

        closes_5m = [c.close_price for c in completed_5m]
        ema20_5m = ema(closes_5m, 20)
        latest_ema20_5m = ema20_5m[-1]
        if latest_ema20_5m is None:
            reasons.append("missing_5m_ema")

        latest_candle = completed_5m[-1]
        previous_candle = completed_5m[-2]
        if latest_ema20_5m is not None:
            pullback_gap = abs(latest_candle.low_price - latest_ema20_5m) / latest_ema20_5m
            if pullback_gap > self.config.ema_pullback_tolerance_pct:
                reasons.append("pullback_not_near_ema20")
            if latest_candle.close_price <= latest_ema20_5m:
                reasons.append("close_not_recovered_above_ema20")

        if latest_candle.close_price <= previous_candle.high_price:
            reasons.append("close_failed_prev_high_break")

        volume_baseline = average([c.volume for c in completed_5m[-21:-1]])
        if latest_candle.volume < volume_baseline * self.config.min_volume_ratio:
            reasons.append("volume_ratio_too_low")

        rsi_values = rsi(closes_5m, self.config.rsi_period)
        latest_rsi = rsi_values[-1]
        previous_rsi = rsi_values[-2]
        if latest_rsi is None or previous_rsi is None:
            reasons.append("missing_rsi")
        else:
            if latest_rsi < self.config.rsi_min or latest_rsi > self.config.rsi_max:
                reasons.append("rsi_out_of_range")
            if latest_rsi <= previous_rsi:
                reasons.append("rsi_not_rising")

        close_two_candles_ago = completed_5m[-3].close_price
        overheat_pct = (latest_candle.close_price / close_two_candles_ago) - 1
        if overheat_pct >= self.config.overheat_10m_limit_pct:
            reasons.append("overheat_10m")

        should_enter = not reasons
        return StrategyEvaluation(
            decision=SignalDecision(
                market=market,
                should_enter=should_enter,
                evaluated_candle_start=latest_completed,
                reasons=reasons or ["entry_signal_confirmed"],
            ),
            latest_completed_5m_start=latest_completed,
        )

    def _completed_candles(self, candles: List[Candle], now: datetime, unit_minutes: int) -> List[Candle]:
        if now.tzinfo is None:
            now = now.replace(tzinfo=self.tz)
        bucket_start = self._bucket_start(now, unit_minutes)
        return [candle for candle in candles if candle.start_time + timedelta(minutes=unit_minutes) <= bucket_start]

    def _bucket_start(self, when: datetime, unit_minutes: int) -> datetime:
        localized = when.astimezone(self.tz).replace(second=0, microsecond=0)
        minute = localized.minute - (localized.minute % unit_minutes)
        return localized.replace(minute=minute)

    def _ema_is_rising(self, values: List[Optional[float]], bars: int) -> bool:
        recent = values[-bars:]
        if len(recent) < bars or any(value is None for value in recent):
            return False
        return all(float(recent[index]) > float(recent[index - 1]) for index in range(1, len(recent)))

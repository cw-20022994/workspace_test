from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from typing import Iterable, List, Optional, Tuple

from stock_auto.config import StrategyConfig
from stock_auto.domain.models import Bar, DaySignalResult, FVGSetup, OpeningRange
from stock_auto.services.bar_builder import BarBuilder


class SignalEngine:
    def __init__(self, config: StrategyConfig, bar_builder: Optional[BarBuilder] = None) -> None:
        self.config = config
        self.bar_builder = bar_builder or BarBuilder()
        self.session_tz = ZoneInfo(config.session_timezone)

    def evaluate_day(self, symbol: str, minute_bars: Iterable[Bar]) -> DaySignalResult:
        ordered = sorted(minute_bars, key=lambda bar: bar.timestamp)
        if not ordered:
            raise ValueError("minute_bars must not be empty")

        session_date = ordered[0].timestamp.astimezone(self.session_tz).date()
        in_window = [
            bar
            for bar in ordered
            if self._in_signal_window(bar.timestamp)
        ]

        if not in_window:
            return DaySignalResult(
                symbol=symbol,
                session_date=session_date,
                opening_range=None,
                setup=None,
                skip_reason="no_bars_in_signal_window",
            )

        opening_range = self._build_opening_range(session_date, in_window)
        if opening_range is None:
            return DaySignalResult(
                symbol=symbol,
                session_date=session_date,
                opening_range=None,
                setup=None,
                skip_reason="opening_range_incomplete",
            )

        signal_bars = self.bar_builder.resample(in_window, self.config.signal_bar_minutes)
        setup, skip_reason = self.find_first_setup(symbol, session_date, signal_bars, opening_range)
        return DaySignalResult(
            symbol=symbol,
            session_date=session_date,
            opening_range=opening_range,
            setup=setup,
            skip_reason=skip_reason,
        )

    def find_first_setup(
        self,
        symbol: str,
        session_date: date,
        five_minute_bars: Iterable[Bar],
        opening_range: OpeningRange,
    ) -> Tuple[Optional[FVGSetup], Optional[str]]:
        bars = sorted(five_minute_bars, key=lambda bar: bar.timestamp)
        last_breakout_index: Optional[int] = None
        saw_breakout = False
        saw_fvg = False
        saw_filtered_setup = False

        for index, bar in enumerate(bars):
            if bar.timestamp.time() < self._opening_range_end_time():
                continue

            if self._is_body_breakout(bar, opening_range.high):
                last_breakout_index = index
                saw_breakout = True

            if index < 2 or last_breakout_index is None:
                continue

            if index - last_breakout_index > self.config.breakout_lookahead_bars:
                continue

            bar_a = bars[index - 2]
            bar_c = bars[index]

            if bar_c.low <= bar_a.high:
                continue

            saw_fvg = True
            fvg_low = bar_a.high
            fvg_high = bar_c.low
            fvg_size = fvg_high - fvg_low
            minimum_fvg_size = max(
                self.config.min_fvg_size_abs,
                bar_c.close * self.config.min_fvg_size_ratio,
            )

            if bar_c.close <= opening_range.high or fvg_size < minimum_fvg_size:
                saw_filtered_setup = True
                continue

            entry_price = fvg_high
            stop_price = bar_a.low
            risk_per_share = entry_price - stop_price
            stop_pct = risk_per_share / entry_price

            if stop_pct < self.config.min_stop_distance_pct or stop_pct > self.config.max_stop_distance_pct:
                saw_filtered_setup = True
                continue

            detect_time = bar_c.timestamp + timedelta(minutes=self.config.signal_bar_minutes)
            target_price = entry_price + (risk_per_share * self.config.risk_reward_ratio)
            setup = FVGSetup(
                symbol=symbol,
                session_date=session_date,
                breakout_bar_time=bars[last_breakout_index].timestamp,
                setup_bar_time=bar_c.timestamp,
                detect_time=detect_time,
                or_high=opening_range.high,
                or_low=opening_range.low,
                fvg_low=fvg_low,
                fvg_high=fvg_high,
                entry_price=entry_price,
                stop_price=stop_price,
                target_price=target_price,
                risk_per_share=risk_per_share,
            )
            return setup, None

        if not saw_breakout:
            return None, "no_body_breakout"
        if not saw_fvg:
            return None, "no_fvg_after_breakout"
        if saw_filtered_setup:
            return None, "setup_rejected_by_filters"
        return None, "no_valid_setup"

    def _build_opening_range(
        self,
        session_date: date,
        minute_bars: List[Bar],
    ) -> Optional[OpeningRange]:
        start = self._session_datetime(session_date, self.config.session_start_time)
        end = start + timedelta(minutes=self.config.opening_range_minutes)
        opening_minutes = [
            bar
            for bar in minute_bars
            if start <= bar.timestamp.astimezone(self.session_tz) < end
        ]
        if len(opening_minutes) < self.config.opening_range_minutes:
            return None

        fifteen_bars = self.bar_builder.resample(opening_minutes, self.config.opening_range_minutes)
        if not fifteen_bars:
            return None

        opening_bar = fifteen_bars[0]
        return OpeningRange(
            session_date=session_date,
            high=opening_bar.high,
            low=opening_bar.low,
            bar_time=opening_bar.timestamp,
        )

    def _is_body_breakout(self, bar: Bar, or_high: float) -> bool:
        return bar.close > or_high and bar.open <= or_high

    def _in_signal_window(self, timestamp: datetime) -> bool:
        local = timestamp.astimezone(self.session_tz)
        start = self.config.session_start_time
        end = self.config.session_end_time
        return start <= local.time() < end

    def _opening_range_end_time(self) -> time:
        dt = datetime.combine(date.today(), self.config.session_start_time)
        dt += timedelta(minutes=self.config.opening_range_minutes)
        return dt.time()

    def _session_datetime(self, session_date: date, session_time: time) -> datetime:
        return datetime.combine(session_date, session_time, tzinfo=self.session_tz)

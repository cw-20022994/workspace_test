from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

from stock_auto.backtest.metrics import BacktestReport, build_report
from stock_auto.config import StrategyConfig
from stock_auto.domain.models import Bar, DailyNote, FVGSetup, Trade
from stock_auto.services.risk_engine import PositionPlan, RiskEngine
from stock_auto.services.signal_engine import SignalEngine


def parse_timestamp(value: str, assume_timezone: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(assume_timezone))
    return parsed


def load_bars_from_csv(
    path: Path,
    default_symbol: str,
    assume_timezone: str,
) -> List[Bar]:
    bars: List[Bar] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            symbol = row.get("symbol") or default_symbol
            timestamp = parse_timestamp(row["timestamp"], assume_timezone)
            bars.append(
                Bar(
                    symbol=symbol,
                    timestamp=timestamp,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume") or 0.0),
                )
            )
    return sorted(bars, key=lambda item: item.timestamp)


class BacktestRunner:
    def __init__(self, config: StrategyConfig) -> None:
        self.config = config
        self.signal_engine = SignalEngine(config)
        self.risk_engine = RiskEngine(config)
        self.session_tz = ZoneInfo(config.session_timezone)

    def run(self, minute_bars: Iterable[Bar]) -> BacktestReport:
        grouped = self._group_by_session_date(minute_bars)
        equity = self.config.account_size
        trades: List[Trade] = []
        notes: List[DailyNote] = []

        for session_date, day_bars in sorted(grouped.items()):
            signal_result = self.signal_engine.evaluate_day(self.config.symbol, day_bars)
            if signal_result.setup is None:
                notes.append(DailyNote(session_date=session_date, reason=signal_result.skip_reason or "no_setup"))
                continue

            position_plan = self.risk_engine.position_plan(signal_result.setup, equity)
            if position_plan is None:
                notes.append(DailyNote(session_date=session_date, reason="position_size_below_minimum"))
                continue

            trade, skip_reason = self._simulate_trade(
                day_bars=day_bars,
                setup=signal_result.setup,
                position_plan=position_plan,
            )
            if trade is None:
                notes.append(DailyNote(session_date=session_date, reason=skip_reason or "trade_not_executed"))
                continue

            trades.append(trade)
            equity += trade.pnl
            notes.append(DailyNote(session_date=session_date, reason="trade_executed"))

        return build_report(trades=trades, daily_notes=notes, starting_equity=self.config.account_size)

    def _simulate_trade(
        self,
        day_bars: List[Bar],
        setup: FVGSetup,
        position_plan: PositionPlan,
    ) -> Tuple[Optional[Trade], Optional[str]]:
        session_end = datetime.combine(
            setup.session_date,
            self.config.session_end_time,
            tzinfo=self.session_tz,
        )

        ordered = sorted(day_bars, key=lambda bar: bar.timestamp)
        entry_index: Optional[int] = None
        entry_time: Optional[datetime] = None

        for index, bar in enumerate(ordered):
            local_time = bar.timestamp.astimezone(self.session_tz)
            if local_time < setup.detect_time:
                continue
            if local_time >= session_end:
                break
            if bar.low <= setup.entry_price:
                entry_index = index
                entry_time = local_time
                break

        if entry_index is None or entry_time is None:
            return None, "entry_not_filled_by_session_end"

        for index in range(entry_index, len(ordered)):
            bar = ordered[index]
            local_time = bar.timestamp.astimezone(self.session_tz)
            if local_time >= session_end:
                break

            if bar.low <= setup.stop_price:
                exit_price = max(0.0, setup.stop_price - self.config.stop_slippage_per_share)
                return self._build_trade(
                    setup=setup,
                    position_plan=position_plan,
                    entry_time=entry_time,
                    exit_time=local_time,
                    exit_price=exit_price,
                    exit_reason="stop_hit",
                ), None

            if bar.high >= setup.target_price:
                return self._build_trade(
                    setup=setup,
                    position_plan=position_plan,
                    entry_time=entry_time,
                    exit_time=local_time,
                    exit_price=setup.target_price,
                    exit_reason="target_hit",
                ), None

        force_bar = self._force_exit_bar(ordered, session_end)
        exit_price = max(0.0, force_bar.open - self.config.force_exit_slippage_per_share)
        return self._build_trade(
            setup=setup,
            position_plan=position_plan,
            entry_time=entry_time,
            exit_time=force_bar.timestamp.astimezone(self.session_tz),
            exit_price=exit_price,
            exit_reason="session_exit",
        ), None

    def _build_trade(
        self,
        setup: FVGSetup,
        position_plan: PositionPlan,
        entry_time: datetime,
        exit_time: datetime,
        exit_price: float,
        exit_reason: str,
    ) -> Trade:
        pnl = (exit_price - setup.entry_price) * position_plan.quantity
        total_risk = setup.risk_per_share * position_plan.quantity
        r_multiple = (pnl / total_risk) if total_risk else 0.0
        return Trade(
            symbol=setup.symbol,
            session_date=setup.session_date,
            detect_time=setup.detect_time,
            entry_time=entry_time,
            exit_time=exit_time,
            entry_price=setup.entry_price,
            exit_price=exit_price,
            stop_price=setup.stop_price,
            target_price=setup.target_price,
            quantity=position_plan.quantity,
            pnl=pnl,
            r_multiple=r_multiple,
            exit_reason=exit_reason,
        )

    def _force_exit_bar(self, ordered: List[Bar], session_end: datetime) -> Bar:
        for bar in ordered:
            local_time = bar.timestamp.astimezone(self.session_tz)
            if local_time >= session_end:
                return bar
        return ordered[-1]

    def _group_by_session_date(self, minute_bars: Iterable[Bar]) -> Dict[datetime.date, List[Bar]]:
        grouped: Dict[datetime.date, List[Bar]] = defaultdict(list)
        for bar in sorted(minute_bars, key=lambda item: item.timestamp):
            local = bar.timestamp.astimezone(self.session_tz)
            grouped[local.date()].append(
                Bar(
                    symbol=bar.symbol,
                    timestamp=local,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                )
            )
        return grouped

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from stock_auto.backtest.runner import BacktestRunner
from stock_auto.config import StrategyConfig
from stock_auto.domain.models import Bar


def make_bar(symbol: str, timestamp: datetime, open_: float, high: float, low: float, close: float) -> Bar:
    return Bar(symbol=symbol, timestamp=timestamp, open=open_, high=high, low=low, close=close, volume=100)


class BacktestRunnerTest(unittest.TestCase):
    def test_runner_executes_target_hit_trade(self) -> None:
        tz = ZoneInfo("America/New_York")
        start = datetime(2026, 3, 20, 9, 30, tzinfo=tz)
        bars = []

        opening_prices = [
            (100.00, 100.30, 99.80, 100.10),
            (100.10, 100.40, 99.95, 100.20),
            (100.20, 100.60, 100.10, 100.40),
            (100.40, 100.70, 100.20, 100.50),
            (100.50, 100.80, 100.30, 100.60),
            (100.60, 100.90, 100.40, 100.70),
            (100.70, 100.95, 100.50, 100.80),
            (100.80, 101.00, 100.60, 100.90),
            (100.90, 100.98, 100.70, 100.92),
            (100.92, 100.99, 100.75, 100.95),
            (100.95, 100.97, 100.80, 100.90),
            (100.90, 100.96, 100.82, 100.88),
            (100.88, 100.94, 100.81, 100.86),
            (100.86, 100.93, 100.80, 100.85),
            (100.85, 100.92, 100.79, 100.84),
        ]
        for index, ohlc in enumerate(opening_prices):
            bars.append(make_bar("SPY", start + timedelta(minutes=index), *ohlc))

        follow_through = [
            (100.60, 100.90, 100.85, 100.90),
            (100.90, 100.95, 100.88, 100.92),
            (100.92, 100.96, 100.90, 100.94),
            (100.94, 100.98, 100.92, 100.95),
            (100.95, 101.00, 100.93, 100.95),
            (100.95, 101.05, 100.90, 101.00),
            (101.00, 101.18, 100.98, 101.10),
            (101.10, 101.22, 101.00, 101.15),
            (101.15, 101.25, 101.02, 101.18),
            (101.18, 101.28, 101.01, 101.20),
        ]
        offset = 15
        for index, ohlc in enumerate(follow_through):
            bars.append(make_bar("SPY", start + timedelta(minutes=offset + index), *ohlc))

        fvg_bars = [
            (101.18, 101.30, 101.10, 101.20),
            (101.20, 101.35, 101.15, 101.25),
            (101.25, 101.40, 101.20, 101.25),
            (101.25, 101.35, 101.15, 101.22),
            (101.22, 101.25, 101.20, 101.20),
            (101.20, 101.30, 101.18, 101.22),
            (101.22, 101.50, 101.18, 101.30),
            (101.30, 101.35, 101.25, 101.32),
            (101.32, 101.38, 101.28, 101.35),
            (101.35, 101.42, 101.31, 101.40),
        ]
        offset = 25
        for index, ohlc in enumerate(fvg_bars):
            bars.append(make_bar("SPY", start + timedelta(minutes=offset + index), *ohlc))

        retrace_and_target = [
            (101.30, 101.35, 101.00, 101.10),
            (101.10, 101.65, 101.00, 101.60),
            (101.48, 101.50, 101.40, 101.45),
            (101.45, 101.48, 101.42, 101.46),
            (101.46, 101.48, 101.44, 101.47),
        ]
        offset = 35
        for index, ohlc in enumerate(retrace_and_target):
            bars.append(make_bar("SPY", start + timedelta(minutes=offset + index), *ohlc))

        config = StrategyConfig()
        report = BacktestRunner(config).run(bars)

        self.assertEqual(report.total_trades, 1)
        trade = report.trades[0]
        self.assertEqual(trade.exit_reason, "target_hit")
        self.assertAlmostEqual(trade.entry_price, 101.10)
        self.assertAlmostEqual(trade.exit_price, 101.60)
        self.assertGreater(trade.pnl, 0)


if __name__ == "__main__":
    unittest.main()

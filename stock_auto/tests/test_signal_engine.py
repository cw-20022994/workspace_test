from __future__ import annotations

import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from stock_auto.config import StrategyConfig
from stock_auto.domain.models import Bar, OpeningRange
from stock_auto.services.signal_engine import SignalEngine


class SignalEngineTest(unittest.TestCase):
    def test_find_first_setup_after_breakout(self) -> None:
        tz = ZoneInfo("America/New_York")
        config = StrategyConfig()
        engine = SignalEngine(config)
        opening_range = OpeningRange(
            session_date=date(2026, 3, 20),
            high=101.0,
            low=99.5,
            bar_time=datetime(2026, 3, 20, 9, 30, tzinfo=tz),
        )
        bars = [
            Bar("SPY", datetime(2026, 3, 20, 9, 45, tzinfo=tz), 100.60, 101.00, 100.85, 100.95),
            Bar("SPY", datetime(2026, 3, 20, 9, 50, tzinfo=tz), 100.95, 101.25, 100.90, 101.20),
            Bar("SPY", datetime(2026, 3, 20, 9, 55, tzinfo=tz), 101.18, 101.50, 101.06, 101.40),
        ]

        setup, reason = engine.find_first_setup("SPY", opening_range.session_date, bars, opening_range)

        self.assertIsNone(reason)
        self.assertIsNotNone(setup)
        assert setup is not None
        self.assertEqual(setup.entry_price, 101.06)
        self.assertEqual(setup.stop_price, 100.85)
        self.assertAlmostEqual(setup.target_price, 101.48)
        self.assertEqual(setup.detect_time, datetime(2026, 3, 20, 10, 0, tzinfo=tz))


if __name__ == "__main__":
    unittest.main()

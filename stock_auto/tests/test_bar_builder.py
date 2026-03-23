from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from stock_auto.domain.models import Bar
from stock_auto.services.bar_builder import BarBuilder


class BarBuilderTest(unittest.TestCase):
    def test_resample_aggregates_ohlcv(self) -> None:
        tz = ZoneInfo("America/New_York")
        bars = [
            Bar("SPY", datetime(2026, 3, 20, 9, 30, tzinfo=tz), 100.0, 100.2, 99.9, 100.1, 10),
            Bar("SPY", datetime(2026, 3, 20, 9, 31, tzinfo=tz), 100.1, 100.3, 100.0, 100.2, 11),
            Bar("SPY", datetime(2026, 3, 20, 9, 32, tzinfo=tz), 100.2, 100.4, 100.1, 100.3, 12),
            Bar("SPY", datetime(2026, 3, 20, 9, 33, tzinfo=tz), 100.3, 100.5, 100.2, 100.4, 13),
            Bar("SPY", datetime(2026, 3, 20, 9, 34, tzinfo=tz), 100.4, 100.6, 100.3, 100.5, 14),
            Bar("SPY", datetime(2026, 3, 20, 9, 35, tzinfo=tz), 100.5, 100.7, 100.4, 100.6, 15),
        ]

        resampled = BarBuilder().resample(bars, 5)

        self.assertEqual(len(resampled), 2)
        self.assertEqual(resampled[0].timestamp, datetime(2026, 3, 20, 9, 30, tzinfo=tz))
        self.assertEqual(resampled[0].open, 100.0)
        self.assertEqual(resampled[0].high, 100.6)
        self.assertEqual(resampled[0].low, 99.9)
        self.assertEqual(resampled[0].close, 100.5)
        self.assertEqual(resampled[0].volume, 60)


if __name__ == "__main__":
    unittest.main()

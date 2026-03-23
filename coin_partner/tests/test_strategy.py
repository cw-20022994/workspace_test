from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from coin_partner.config import StrategyConfig
from coin_partner.models import Candle
from coin_partner.strategy import SpotStrategy


class SpotStrategyTest(unittest.TestCase):
    def test_entry_signal_when_all_conditions_align(self) -> None:
        tz = ZoneInfo("Asia/Seoul")
        strategy = SpotStrategy(
            StrategyConfig(
                markets=["KRW-BTC", "KRW-ETH"],
                entry_amount_krw=30000,
                ema_pullback_tolerance_pct=0.003,
                min_volume_ratio=1.3,
                rsi_period=14,
                rsi_min=52,
                rsi_max=68,
                overheat_10m_limit_pct=0.018,
                relaxed_hourly_trend_markets=[],
                hourly_ema20_rising_bars=3,
            ),
            "Asia/Seoul",
        )

        now = datetime(2026, 3, 20, 15, 42, tzinfo=tz)
        h1_candles = []
        h1_start = datetime(2026, 3, 17, 8, 0, tzinfo=tz)
        for index in range(80):
            base = 99.8 + index * 0.008
            h1_candles.append(
                Candle(
                    market="KRW-BTC",
                    unit_minutes=60,
                    start_time=h1_start + timedelta(hours=index),
                    open_price=base - 0.06,
                    high_price=base + 0.08,
                    low_price=base - 0.08,
                    close_price=base,
                    volume=1000 + index * 5,
                    turnover=100000,
                )
            )

        m5_candles = []
        m5_start = datetime(2026, 3, 20, 12, 0, tzinfo=tz)
        prices = [
            100.05, 100.05, 100.09, 100.10, 100.07, 100.11, 100.09, 100.14, 100.19, 100.17,
            100.22, 100.20, 100.24, 100.25, 100.23, 100.24, 100.24, 100.24, 100.24, 100.28,
            100.32, 100.35, 100.33, 100.37, 100.38, 100.35, 100.35, 100.30, 100.28, 100.36,
        ]
        for index, close in enumerate(prices):
            high = close + 0.06
            low = close - 0.06
            volume = 100 + index
            if index == len(prices) - 1:
                low = close - 0.02
                high = close + 0.07
                volume = 180
            m5_candles.append(
                Candle(
                    market="KRW-BTC",
                    unit_minutes=5,
                    start_time=m5_start + timedelta(minutes=index * 5),
                    open_price=prices[index] - 0.02,
                    high_price=high,
                    low_price=low,
                    close_price=close,
                    volume=volume,
                    turnover=10000,
                )
            )

        evaluation = strategy.evaluate_market(
            market="KRW-BTC",
            candles_5m=m5_candles,
            candles_1h=h1_candles,
            current_price=100.36,
            now=now,
            last_processed_5m_start=None,
        )

        self.assertTrue(evaluation.decision.should_enter)
        self.assertEqual(evaluation.decision.reasons, ["entry_signal_confirmed"])

    def test_relaxed_hourly_trend_applies_only_to_btc(self) -> None:
        tz = ZoneInfo("Asia/Seoul")
        strategy = SpotStrategy(
            StrategyConfig(
                markets=["KRW-BTC", "KRW-ETH"],
                entry_amount_krw=30000,
                ema_pullback_tolerance_pct=0.003,
                min_volume_ratio=1.3,
                rsi_period=14,
                rsi_min=52,
                rsi_max=68,
                overheat_10m_limit_pct=0.018,
                relaxed_hourly_trend_markets=["KRW-BTC"],
                hourly_ema20_rising_bars=3,
            ),
            "Asia/Seoul",
        )

        now = datetime(2026, 3, 20, 15, 42, tzinfo=tz)
        h1_candles = []
        h1_start = datetime(2026, 3, 17, 8, 0, tzinfo=tz)
        closes = [120 - index * 0.3 for index in range(65)] + [101.0, 101.8, 102.6, 103.4, 104.2, 105.0, 105.8, 106.6, 107.4, 108.2, 109.0, 109.8, 110.6, 111.4, 112.2]
        for index, close in enumerate(closes):
            h1_candles.append(
                Candle(
                    market="KRW-BTC",
                    unit_minutes=60,
                    start_time=h1_start + timedelta(hours=index),
                    open_price=close - 0.2,
                    high_price=close + 0.3,
                    low_price=close - 0.4,
                    close_price=close,
                    volume=1000 + index * 5,
                    turnover=100000,
                )
            )

        m5_candles = []
        m5_start = datetime(2026, 3, 20, 12, 0, tzinfo=tz)
        prices = [
            110.05, 110.05, 110.09, 110.10, 110.07, 110.11, 110.09, 110.14, 110.19, 110.17,
            110.22, 110.20, 110.24, 110.25, 110.23, 110.24, 110.24, 110.24, 110.24, 110.28,
            110.32, 110.35, 110.33, 110.37, 110.38, 110.35, 110.35, 110.30, 110.28, 110.36,
        ]
        for index, close in enumerate(prices):
            high = close + 0.06
            low = close - 0.06
            volume = 100 + index
            if index == len(prices) - 1:
                low = close - 0.02
                high = close + 0.07
                volume = 180
            m5_candles.append(
                Candle(
                    market="KRW-BTC",
                    unit_minutes=5,
                    start_time=m5_start + timedelta(minutes=index * 5),
                    open_price=prices[index] - 0.02,
                    high_price=high,
                    low_price=low,
                    close_price=close,
                    volume=volume,
                    turnover=10000,
                )
            )

        btc_evaluation = strategy.evaluate_market(
            market="KRW-BTC",
            candles_5m=m5_candles,
            candles_1h=h1_candles,
            current_price=110.36,
            now=now,
            last_processed_5m_start=None,
        )
        eth_evaluation = strategy.evaluate_market(
            market="KRW-ETH",
            candles_5m=m5_candles,
            candles_1h=h1_candles,
            current_price=110.36,
            now=now,
            last_processed_5m_start=None,
        )

        self.assertTrue(btc_evaluation.decision.should_enter)
        self.assertIn("hourly_trend_down", eth_evaluation.decision.reasons)


if __name__ == "__main__":
    unittest.main()

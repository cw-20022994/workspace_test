"""Telegram notification tests."""

from __future__ import annotations

import unittest

from stock_report.notifications.telegram import build_daily_refresh_message
from stock_report.notifications.telegram import build_test_message


class TelegramMessageTests(unittest.TestCase):
    def test_build_daily_refresh_message_includes_leaders_and_failures(self) -> None:
        message = build_daily_refresh_message(
            refresh_summary={
                "run_date": "2026-03-19",
                "steps": [
                    {"name": "daily_batch", "status": "success"},
                    {"name": "backtest_summary", "status": "error"},
                ],
                "symbols": ["SPY", "SNDK"],
            },
            daily_summary={
                "leaders": [
                    {"symbol": "SNDK", "total_score": 71.0, "verdict": "review"},
                    {"symbol": "SPY", "total_score": 52.2, "verdict": "hold"},
                ]
            },
            calibration_report={
                "auto_applied": False,
                "reasons": ["완료 관측치가 부족해 기존 점수 체계를 유지했습니다."],
            },
        )

        self.assertIn("stock_report daily-refresh", message)
        self.assertIn("상태: 실패", message)
        self.assertIn("심볼: SPY, SNDK", message)
        self.assertIn("- SNDK 71.0 검토", message)
        self.assertIn("보정: 유지", message)
        self.assertIn("실패 단계: backtest_summary", message)

    def test_build_test_message_returns_short_probe_text(self) -> None:
        self.assertIn("Telegram test", build_test_message())


if __name__ == "__main__":
    unittest.main()

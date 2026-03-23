from __future__ import annotations

import unittest
from datetime import datetime

from coin_partner.config import TelegramConfig
from coin_partner.models import BotState, DailyState, Position
from coin_partner.telegram import TelegramNotifier


class TelegramNotifierTest(unittest.TestCase):
    def _telegram_config(self) -> TelegramConfig:
        return TelegramConfig(
            enabled=True,
            bot_token_env="TELEGRAM_BOT_TOKEN",
            chat_id="123456",
            parse_mode="HTML",
            send_silently=False,
            request_timeout_seconds=10,
            notify_entry=True,
            notify_exit=True,
            notify_daily_stop=True,
            notify_daily_summary=True,
            daily_summary_hour=23,
            daily_summary_minute=0,
            notify_heartbeat=True,
            heartbeat_interval_minutes=60,
            notify_errors=True,
            error_cooldown_minutes=15,
        )

    def test_entry_message_contains_trade_context(self) -> None:
        delivered = []
        notifier = TelegramNotifier(
            self._telegram_config(),
            mode="paper",
            sender=delivered.append,
        )
        notifier.settings.enabled = True

        position = Position(
            market="KRW-BTC",
            volume=0.00123456,
            entry_price=150000000.0,
            invested_krw=30000.0,
            opened_at=datetime(2026, 3, 20, 10, 0),
            stop_price=147750000.0,
            take_profit_price=153450000.0,
        )
        state = BotState(
            paper_cash_krw=169985.0,
            daily=DailyState(trading_date=datetime(2026, 3, 20).date(), trade_count=1),
            positions=[position],
        )

        notifier.notify_entry(position, state)

        self.assertEqual(len(delivered), 1)
        self.assertIn("[ENTRY]", delivered[0])
        self.assertIn("KRW-BTC", delivered[0])
        self.assertIn("cash: 169,985 KRW", delivered[0])

    def test_error_notification_is_rate_limited(self) -> None:
        delivered = []
        notifier = TelegramNotifier(
            self._telegram_config(),
            mode="paper",
            sender=delivered.append,
        )
        notifier.settings.enabled = True

        first = datetime(2026, 3, 20, 10, 0)
        second = datetime(2026, 3, 20, 10, 5)
        third = datetime(2026, 3, 20, 10, 16)

        notifier.notify_error("first error", first)
        notifier.notify_error("second error", second)
        notifier.notify_error("third error", third)

        self.assertEqual(len(delivered), 2)
        self.assertIn("first error", delivered[0])
        self.assertIn("third error", delivered[1])

    def test_daily_summary_and_heartbeat_messages_include_status(self) -> None:
        delivered = []
        notifier = TelegramNotifier(
            self._telegram_config(),
            mode="paper",
            sender=delivered.append,
        )
        notifier.settings.enabled = True

        position = Position(
            market="KRW-ETH",
            volume=0.01234567,
            entry_price=4500000.0,
            invested_krw=30000.0,
            opened_at=datetime(2026, 3, 20, 14, 0),
            stop_price=4432500.0,
            take_profit_price=4603500.0,
        )
        state = BotState(
            paper_cash_krw=171000.0,
            daily=DailyState(trading_date=datetime(2026, 3, 20).date(), trade_count=3, realized_pnl_krw=2400.0),
            positions=[position],
        )

        notifier.notify_daily_summary("2026-03-20", state, wins=2, losses=1, best_trade_pnl_krw=1900.0, worst_trade_pnl_krw=-700.0)
        notifier.notify_heartbeat(state, datetime(2026, 3, 20, 22, 0), mark_prices={"KRW-ETH": 4550000.0})

        self.assertEqual(len(delivered), 2)
        self.assertIn("[DAY SUMMARY]", delivered[0])
        self.assertIn("wins / losses: 2 / 1", delivered[0])
        self.assertIn("[HEARTBEAT]", delivered[1])
        self.assertIn("open positions: 1", delivered[1])
        self.assertIn("unrealized:", delivered[1])


if __name__ == "__main__":
    unittest.main()

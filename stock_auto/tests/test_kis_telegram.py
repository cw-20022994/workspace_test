from __future__ import annotations

import unittest
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

from stock_auto.services.kis_monitor import KISMonitorResult
from stock_auto.services.kis_state import KISTradeState
from stock_auto.services.kis_telegram import KISTelegramNotifier


class _FakeTelegramClient:
    def __init__(self) -> None:
        self.messages = []

    def send_message(self, *, text: str, **kwargs) -> None:
        self.messages.append(text)


class KISTelegramNotifierTest(unittest.TestCase):
    def _state(self, **overrides) -> KISTradeState:
        payload = {
            "symbol": "SPY",
            "session_date": date(2026, 3, 20),
            "session_timezone": "America/New_York",
            "session_end": "11:00",
            "price_tick_size": 0.01,
            "quote_exchange_code": "AMS",
            "order_exchange_code": "AMEX",
            "country_code": "840",
            "market_code": "05",
            "entry_price": 101.10,
            "stop_price": 100.85,
            "target_price": 101.60,
            "requested_quantity": 50,
            "filled_quantity": 50,
            "phase": "position_open",
            "last_status": "position_open",
            "updated_at": datetime(2026, 3, 20, 10, 20),
        }
        payload.update(overrides)
        return KISTradeState(**payload)

    def test_notify_run_once_sends_entry_message(self) -> None:
        telegram_client = _FakeTelegramClient()
        notifier = KISTelegramNotifier(telegram_client)
        setup = SimpleNamespace(
            symbol="SPY",
            entry_price=101.10,
            stop_price=100.85,
            target_price=101.60,
        )
        result = SimpleNamespace(
            status="submitted_entry_only",
            setup=setup,
            quantity=50,
            order_response={"ODNO": "entry-1"},
            message="entry order submitted",
        )

        sent = notifier.notify_run_once(
            result=result,
            state_path=Path("state/kis_spy_20260320.json"),
            submitted=True,
        )

        self.assertTrue(sent)
        self.assertEqual(len(telegram_client.messages), 1)
        self.assertIn("[한국투자증권] [미국주식] [SPY]", telegram_client.messages[0])
        self.assertIn("event: ENTRY SUBMITTED", telegram_client.messages[0])
        self.assertIn("order_id: entry-1", telegram_client.messages[0])

    def test_notify_monitor_result_sends_on_exit_submitted(self) -> None:
        telegram_client = _FakeTelegramClient()
        notifier = KISTelegramNotifier(telegram_client)
        previous_state = self._state()
        current_state = self._state(
            phase="exit_submitted",
            exit_order_id="exit-1",
            exit_reason="target_hit",
            last_status="exit_submitted",
        )
        result = KISMonitorResult(
            status="exit_submitted",
            message="target_hit detected and exit order submitted",
            state=current_state,
            quote={"last": "101.70"},
            order_payload={"ORD_QTY": "50"},
            order_response={"ODNO": "exit-1"},
        )

        sent = notifier.notify_monitor_result(
            previous_state=previous_state,
            result=result,
            state_path=Path("state/kis_spy_20260320.json"),
        )

        self.assertTrue(sent)
        self.assertEqual(len(telegram_client.messages), 1)
        self.assertIn("event: EXIT SUBMITTED", telegram_client.messages[0])
        self.assertIn("reason: target_hit", telegram_client.messages[0])
        self.assertIn("order_id: exit-1", telegram_client.messages[0])

    def test_notify_monitor_result_skips_non_notifiable_status(self) -> None:
        telegram_client = _FakeTelegramClient()
        notifier = KISTelegramNotifier(telegram_client)
        previous_state = self._state()
        result = KISMonitorResult(
            status="no_exit_signal",
            message="no exit condition met",
            state=self._state(),
        )

        sent = notifier.notify_monitor_result(
            previous_state=previous_state,
            result=result,
            state_path=Path("state/kis_spy_20260320.json"),
        )

        self.assertFalse(sent)
        self.assertEqual(telegram_client.messages, [])


if __name__ == "__main__":
    unittest.main()

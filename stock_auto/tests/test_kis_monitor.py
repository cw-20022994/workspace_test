from __future__ import annotations

import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from stock_auto.services.kis_monitor import KISExitMonitor
from stock_auto.services.kis_state import KISTradeState


class _FakeMarketDataClient:
    def __init__(self, quote: dict) -> None:
        self.quote = quote
        self.calls = []

    def fetch_quote_snapshot(self, **kwargs):
        self.calls.append(kwargs)
        return dict(self.quote)


class _FakeBrokerClient:
    def __init__(self, *, positions=None, open_orders=None, history=None) -> None:
        self.positions = positions or []
        self.open_orders = open_orders or []
        self.history = history or []
        self.placed_orders = []
        self.cancelled_orders = []

    def list_open_orders(self, **kwargs):
        return list(self.open_orders)

    def get_present_balance(self, **kwargs):
        return {"positions": list(self.positions)}

    def place_limit_order(self, **kwargs):
        self.placed_orders.append(kwargs)
        return {"ODNO": "exit-1", "ORD_TMD": "102000"}

    def cancel_order(self, **kwargs):
        self.cancelled_orders.append(kwargs)
        return {"ODNO": kwargs["original_order_number"]}

    def inquire_order_history(self, **kwargs):
        return list(self.history)


class KISExitMonitorTest(unittest.TestCase):
    def test_check_once_submits_stop_exit(self) -> None:
        state = KISTradeState(
            symbol="SPY",
            session_date=date(2026, 3, 20),
            session_timezone="America/New_York",
            session_end="11:00",
            price_tick_size=0.01,
            quote_exchange_code="NAS",
            order_exchange_code="NASD",
            country_code="840",
            market_code="01",
            entry_price=101.10,
            stop_price=100.85,
            target_price=101.60,
            requested_quantity=197,
            phase="entry_submitted",
        )
        market_data_client = _FakeMarketDataClient({"last": "100.80", "pbid1": "100.79"})
        broker_client = _FakeBrokerClient(positions=[{"pdno": "SPY", "cblc_qty13": "197"}])
        monitor = KISExitMonitor(market_data_client, broker_client)
        now = datetime(2026, 3, 20, 10, 20, tzinfo=ZoneInfo("America/New_York"))

        result = monitor.check_once(state, now=now, dry_run=False)

        self.assertEqual(result.status, "exit_submitted")
        self.assertEqual(result.state.phase, "exit_submitted")
        self.assertEqual(result.state.exit_reason, "stop_hit")
        self.assertEqual(result.order_payload["ORD_QTY"], "197")
        self.assertEqual(result.order_payload["OVRS_ORD_UNPR"], "100.7900")
        self.assertEqual(broker_client.placed_orders[0]["side"], "sell")
        self.assertEqual(market_data_client.calls[0]["quote_exchange_code"], "NAS")

    def test_check_once_marks_closed_when_position_is_gone(self) -> None:
        state = KISTradeState(
            symbol="SPY",
            session_date=date(2026, 3, 20),
            session_timezone="America/New_York",
            session_end="11:00",
            price_tick_size=0.01,
            quote_exchange_code="NAS",
            order_exchange_code="NASD",
            country_code="840",
            market_code="01",
            entry_price=101.10,
            stop_price=100.85,
            target_price=101.60,
            requested_quantity=197,
            filled_quantity=197,
            phase="exit_submitted",
            exit_order_id="exit-1",
        )
        market_data_client = _FakeMarketDataClient({"last": "101.50", "pbid1": "101.49"})
        broker_client = _FakeBrokerClient(positions=[])
        monitor = KISExitMonitor(market_data_client, broker_client)

        result = monitor.check_once(state, dry_run=False)

        self.assertEqual(result.status, "closed")
        self.assertEqual(result.state.phase, "closed")
        self.assertEqual(len(broker_client.placed_orders), 0)

    def test_check_once_uses_execution_history_before_marking_entry_unfilled(self) -> None:
        state = KISTradeState(
            symbol="SPY",
            session_date=date(2026, 3, 20),
            session_timezone="America/New_York",
            session_end="11:00",
            price_tick_size=0.01,
            quote_exchange_code="NAS",
            order_exchange_code="NASD",
            country_code="840",
            market_code="01",
            entry_price=101.10,
            stop_price=100.85,
            target_price=101.60,
            requested_quantity=197,
            phase="entry_submitted",
            entry_order_id="entry-1",
        )
        market_data_client = _FakeMarketDataClient({"last": "101.00", "pbid1": "100.99"})
        broker_client = _FakeBrokerClient(
            positions=[],
            history=[{"odno": "entry-1", "pdno": "SPY", "ft_ccld_qty": "197", "nccs_qty": "0"}],
        )
        monitor = KISExitMonitor(market_data_client, broker_client)

        result = monitor.check_once(state, dry_run=False)

        self.assertEqual(result.status, "closed")
        self.assertEqual(result.state.phase, "closed")
        self.assertEqual(result.state.filled_quantity, 197)

    def test_check_once_does_not_close_when_owned_exit_order_is_still_open(self) -> None:
        state = KISTradeState(
            symbol="SPY",
            session_date=date(2026, 3, 20),
            session_timezone="America/New_York",
            session_end="11:00",
            price_tick_size=0.01,
            quote_exchange_code="NAS",
            order_exchange_code="NASD",
            country_code="840",
            market_code="01",
            entry_price=101.10,
            stop_price=100.85,
            target_price=101.60,
            requested_quantity=197,
            filled_quantity=197,
            phase="exit_submitted",
            exit_order_id="exit-1",
        )
        market_data_client = _FakeMarketDataClient({"last": "101.50", "pbid1": "101.49"})
        broker_client = _FakeBrokerClient(
            positions=[],
            open_orders=[{"odno": "exit-1", "pdno": "SPY", "sll_buy_dvsn_cd": "01", "nccs_qty": "50"}],
        )
        monitor = KISExitMonitor(market_data_client, broker_client)

        result = monitor.check_once(state, dry_run=True)

        self.assertEqual(result.status, "orphan_exit_order_exists")
        self.assertEqual(result.state.phase, "exit_submitted")
        self.assertEqual(len(broker_client.cancelled_orders), 0)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from stock_auto.backtest.runner import load_bars_from_csv
from stock_auto.config import StrategyConfig
from stock_auto.services.kis_bot import KISOverseasBot


class _FakeMarketDataClient:
    def __init__(self, bars) -> None:
        self.bars = bars
        self.calls = []

    def fetch_recent_minute_bars(self, **kwargs):
        self.calls.append(kwargs)
        return list(self.bars)


class _FakeBrokerClient:
    def __init__(self, *, balance=None) -> None:
        self.submitted = []
        self.balance = balance or {"positions": []}

    def list_open_orders(self, **kwargs):
        return []

    def get_present_balance(self, **kwargs):
        return dict(self.balance)

    def inquire_buying_power(self, **kwargs):
        return {"max_ord_psbl_qty": "300"}

    def place_limit_order(self, **kwargs):
        self.submitted.append(kwargs)
        return {"odno": "kis-order-1", "ord_tmd": "100100"}

    def extract_total_assets(self, balance):
        rows = balance.get("summary") or []
        if isinstance(rows, dict):
            rows = [rows]
        for row in rows:
            value = row.get("tot_asst_amt")
            if value not in (None, ""):
                return float(value)
        return None


class KISOverseasBotTest(unittest.TestCase):
    def test_run_once_builds_entry_payload_in_dry_run(self) -> None:
        root = Path(__file__).resolve().parents[1]
        bars = load_bars_from_csv(
            root / "data" / "sample_spy_minutes.csv",
            default_symbol="SPY",
            assume_timezone="America/New_York",
        )
        config = StrategyConfig()
        market_data_client = _FakeMarketDataClient(bars)
        broker_client = _FakeBrokerClient()
        bot = KISOverseasBot(config, market_data_client, broker_client)
        now = datetime(2026, 3, 20, 10, 6, tzinfo=ZoneInfo("America/New_York"))

        result = bot.run_once(symbol="SPY", now=now, dry_run=True)

        self.assertEqual(result.status, "dry_run")
        self.assertEqual(result.quantity, 197)
        self.assertIsNotNone(result.order_payload)
        assert result.order_payload is not None
        self.assertEqual(result.order_payload["OVRS_EXCG_CD"], "AMEX")
        self.assertEqual(result.order_payload["ORD_QTY"], "197")
        self.assertEqual(result.order_payload["OVRS_ORD_UNPR"], "101.1000")
        self.assertEqual(market_data_client.calls[0]["quote_exchange_code"], "AMS")
        self.assertEqual(len(broker_client.submitted), 0)

    def test_run_once_uses_live_balance_for_position_sizing(self) -> None:
        root = Path(__file__).resolve().parents[1]
        bars = load_bars_from_csv(
            root / "data" / "sample_spy_minutes.csv",
            default_symbol="SPY",
            assume_timezone="America/New_York",
        )
        config = StrategyConfig()
        market_data_client = _FakeMarketDataClient(bars)
        broker_client = _FakeBrokerClient(balance={"positions": [], "summary": [{"tot_asst_amt": "50000"}]})
        bot = KISOverseasBot(config, market_data_client, broker_client)
        now = datetime(2026, 3, 20, 10, 6, tzinfo=ZoneInfo("America/New_York"))

        result = bot.run_once(symbol="SPY", now=now, dry_run=True)

        self.assertEqual(result.status, "dry_run")
        self.assertEqual(result.quantity, 98)
        assert result.order_payload is not None
        self.assertEqual(result.order_payload["ORD_QTY"], "98")

    def test_run_once_returns_weekend_status_before_fetching_market_data(self) -> None:
        config = StrategyConfig()
        market_data_client = _FakeMarketDataClient([])
        broker_client = _FakeBrokerClient()
        bot = KISOverseasBot(config, market_data_client, broker_client)
        now = datetime(2026, 3, 21, 8, 45, tzinfo=ZoneInfo("America/New_York"))

        result = bot.run_once(symbol="SPY", now=now, dry_run=True)

        self.assertEqual(result.status, "market_closed_weekend")
        self.assertEqual(result.message, "US market is closed on weekends")
        self.assertEqual(market_data_client.calls, [])


if __name__ == "__main__":
    unittest.main()

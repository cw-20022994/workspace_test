from __future__ import annotations

import json
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from stock_auto.adapters.broker.alpaca_paper import AlpacaPaperTradingClient
from stock_auto.adapters.market_data.alpaca_historical import AlpacaCredentials
from stock_auto.backtest.runner import load_bars_from_csv
from stock_auto.config import StrategyConfig
from stock_auto.services.paper_bot import PaperTradingBot, build_long_bracket_order_payload


class _FakeResponse:
    def __init__(self, payload) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeMarketDataClient:
    def __init__(self, bars) -> None:
        self.bars = bars
        self.calls = []

    def fetch_stock_bars(self, **kwargs):
        self.calls.append(kwargs)
        return list(self.bars)


class _FakeBrokerClient:
    def __init__(self) -> None:
        self.submitted = []

    def get_account(self):
        return {"equity": "100000"}

    def list_orders(self, **kwargs):
        return []

    def list_positions(self):
        return []

    def submit_order(self, payload):
        self.submitted.append(payload)
        return {"id": "paper-order-1", "status": "accepted"}


class AlpacaPaperTradingClientTest(unittest.TestCase):
    def test_get_account_uses_paper_endpoint(self) -> None:
        credentials = AlpacaCredentials(api_key="key", secret_key="secret")
        client = AlpacaPaperTradingClient(credentials, base_url="https://example.test/v2")
        requests = []

        def fake_urlopen(request, timeout):
            requests.append(request.full_url)
            return _FakeResponse({"id": "acct-1", "status": "ACTIVE"})

        with patch("stock_auto.adapters.broker.alpaca_paper.urlopen", side_effect=fake_urlopen):
            account = client.get_account()

        self.assertEqual(account["id"], "acct-1")
        self.assertEqual(requests[0], "https://example.test/v2/account")

    def test_build_long_bracket_order_payload(self) -> None:
        payload = build_long_bracket_order_payload(
            symbol="SPY",
            quantity=197,
            entry_price=101.1,
            stop_price=100.85,
            take_profit_price=101.6,
            client_order_id="orfvg-spy-20260320",
        )

        self.assertEqual(payload["order_class"], "bracket")
        self.assertEqual(payload["limit_price"], "101.10")
        self.assertEqual(payload["stop_loss"]["stop_price"], "100.85")
        self.assertEqual(payload["take_profit"]["limit_price"], "101.60")

    def test_paper_run_once_submits_order_when_setup_exists(self) -> None:
        root = Path(__file__).resolve().parents[1]
        bars = load_bars_from_csv(
            root / "data" / "sample_spy_minutes.csv",
            default_symbol="SPY",
            assume_timezone="America/New_York",
        )
        config = StrategyConfig()
        market_data_client = _FakeMarketDataClient(bars)
        broker_client = _FakeBrokerClient()
        bot = PaperTradingBot(config, market_data_client, broker_client)
        now = datetime(2026, 3, 20, 10, 6, tzinfo=ZoneInfo("America/New_York"))

        result = bot.run_once(symbol="SPY", now=now, dry_run=False)

        self.assertEqual(result.status, "submitted")
        self.assertEqual(result.quantity, 197)
        self.assertEqual(len(broker_client.submitted), 1)
        self.assertEqual(broker_client.submitted[0]["order_class"], "bracket")
        self.assertEqual(broker_client.submitted[0]["limit_price"], "101.10")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from stock_auto.adapters.market_data.alpaca_historical import (
    AlpacaCredentials,
    AlpacaHistoricalBarsClient,
    write_bars_to_csv,
)
from stock_auto.domain.models import Bar


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class AlpacaHistoricalBarsClientTest(unittest.TestCase):
    def test_fetch_stock_bars_handles_pagination(self) -> None:
        credentials = AlpacaCredentials(api_key="key", secret_key="secret")
        client = AlpacaHistoricalBarsClient(credentials, base_url="https://example.test/v2")
        requests = []

        payloads = [
            {
                "bars": {
                    "SPY": [
                        {"t": "2026-03-20T13:30:00Z", "o": 100.0, "h": 101.0, "l": 99.5, "c": 100.5, "v": 10}
                    ]
                },
                "next_page_token": "token-1",
            },
            {
                "bars": {
                    "SPY": [
                        {"t": "2026-03-20T13:31:00Z", "o": 100.5, "h": 101.2, "l": 100.2, "c": 101.0, "v": 11}
                    ]
                },
                "next_page_token": None,
            },
        ]

        def fake_urlopen(request, timeout):
            requests.append(request.full_url)
            return _FakeResponse(payloads[len(requests) - 1])

        with patch("stock_auto.adapters.market_data.alpaca_historical.urlopen", side_effect=fake_urlopen):
            bars = client.fetch_stock_bars(
                symbol="SPY",
                start=datetime(2026, 3, 20, tzinfo=timezone.utc),
                end=datetime(2026, 3, 21, tzinfo=timezone.utc),
            )

        self.assertEqual(len(bars), 2)
        self.assertIn("page_token=token-1", requests[1])
        self.assertEqual(bars[0].timestamp.isoformat(), "2026-03-20T13:30:00+00:00")

    def test_write_bars_to_csv_outputs_expected_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "bars.csv"
            write_bars_to_csv(
                path,
                [
                    Bar(
                        symbol="SPY",
                        timestamp=datetime(2026, 3, 20, 13, 30, tzinfo=timezone.utc),
                        open=100.0,
                        high=101.0,
                        low=99.5,
                        close=100.5,
                        volume=10,
                    )
                ],
            )

            with path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "SPY")
        self.assertEqual(rows[0]["timestamp"], "2026-03-20T09:30:00-04:00")


if __name__ == "__main__":
    unittest.main()

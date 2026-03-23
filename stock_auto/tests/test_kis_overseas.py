from __future__ import annotations

import unittest

from stock_auto.adapters.auth.kis_auth import KISResponse
from stock_auto.adapters.market_data.kis_overseas import KISOverseasStockDataClient


class _FakeAuthSession:
    def __init__(self) -> None:
        self.calls = []

    def request(self, method, endpoint, **kwargs):
        self.calls.append({"method": method, "endpoint": endpoint, **kwargs})
        return KISResponse(
            status_code=200,
            headers={"tr_cont": ""},
            body={
                "rt_cd": "0",
                "output1": {},
                "output2": [
                    {
                        "xymd": "20260320",
                        "xhms": "093000",
                        "kymd": "20260320",
                        "khms": "093000",
                        "open": "100.0",
                        "high": "101.0",
                        "low": "99.5",
                        "last": "100.5",
                        "evol": "10",
                    }
                ],
            },
        )


class KISOverseasStockDataClientTest(unittest.TestCase):
    def test_fetch_recent_minute_bars_parses_chart_rows(self) -> None:
        auth_session = _FakeAuthSession()
        client = KISOverseasStockDataClient(auth_session)

        bars = client.fetch_recent_minute_bars(
            symbol="SPY",
            quote_exchange_code="NAS",
            interval_minutes=1,
            max_records=1,
            market_timezone="America/New_York",
        )

        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].symbol, "SPY")
        self.assertEqual(bars[0].timestamp.isoformat(), "2026-03-20T09:30:00-04:00")
        self.assertEqual(bars[0].close, 100.5)
        self.assertEqual(auth_session.calls[0]["params"]["EXCD"], "NAS")


if __name__ == "__main__":
    unittest.main()

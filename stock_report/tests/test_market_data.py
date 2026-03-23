"""Market data connector tests."""

import unittest

from stock_report.connectors.http import ConnectorError
from stock_report.connectors.market_data import MarketDataClient
from stock_report.connectors.market_data import NaverKoreaChartClient
from stock_report.connectors.market_data import PriceHistory
from stock_report.connectors.market_data import StooqUsChartClient


class StubHttpClient:
    def __init__(self, text):
        self.text = text

    def get_text(self, url, params=None, headers=None):
        return self.text


class StubHistoryClient:
    def __init__(self, history=None, error=None):
        self.history = history
        self.error = error
        self.calls = 0

    def fetch_history(self, symbol, range_value="1y"):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.history


class MarketDataTests(unittest.TestCase):
    def test_stooq_client_parses_csv_rows(self) -> None:
        csv_text = """Date,Open,High,Low,Close,Volume
2026-03-13,100,104,99,103,1000
2026-03-16,103,106,102,105,1200
2026-03-17,105,108,104,107,1300
"""
        client = StooqUsChartClient(http_client=StubHttpClient(csv_text))
        history = client.fetch_history("NVDA", range_value="1y")

        self.assertEqual(history.symbol, "NVDA")
        self.assertEqual(history.currency, "USD")
        self.assertEqual(len(history.bars), 3)
        self.assertEqual(history.bars[-1].close, 107.0)

    def test_naver_client_parses_daily_table(self) -> None:
        html = """
<html>
  <body>
    <table class="type2">
      <tr><td>2026.03.17</td><td>71,300</td><td>1,200</td><td>70,100</td><td>71,800</td><td>69,900</td><td>10,000</td></tr>
      <tr><td>2026.03.16</td><td>70,000</td><td>500</td><td>69,500</td><td>70,500</td><td>69,100</td><td>9,500</td></tr>
    </table>
  </body>
</html>
"""
        client = NaverKoreaChartClient(http_client=StubHttpClient(html))
        history = client.fetch_history("005930.KS", range_value="1y")

        self.assertEqual(history.symbol, "005930.KS")
        self.assertEqual(history.currency, "KRW")
        self.assertEqual(len(history.bars), 2)
        self.assertEqual(history.bars[-1].close, 71300.0)

    def test_market_data_client_falls_back_to_yahoo_when_stooq_fails(self) -> None:
        fallback_history = PriceHistory(
            symbol="NVDA",
            currency="USD",
            exchange_name="NMS",
            instrument_type="EQUITY",
            short_name="NVIDIA",
            regular_market_price=120.0,
            bars=[],
        )
        primary = StubHistoryClient(error=ConnectorError("stooq down"))
        fallback = StubHistoryClient(history=fallback_history)

        client = MarketDataClient(
            us_client=primary,
            us_fallback_client=fallback,
            korea_client=StubHistoryClient(),
        )
        history = client.fetch_history("NVDA", range_value="1y")

        self.assertEqual(history.short_name, "NVIDIA")
        self.assertEqual(primary.calls, 1)
        self.assertEqual(fallback.calls, 1)

    def test_market_data_client_raises_combined_error_when_both_us_sources_fail(self) -> None:
        client = MarketDataClient(
            us_client=StubHistoryClient(error=ConnectorError("stooq down")),
            us_fallback_client=StubHistoryClient(error=ConnectorError("yahoo down")),
            korea_client=StubHistoryClient(),
        )

        with self.assertRaises(ConnectorError) as ctx:
            client.fetch_history("NVDA", range_value="1y")

        self.assertIn("Primary source error", str(ctx.exception))
        self.assertIn("Fallback source error", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

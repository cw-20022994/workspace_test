"""ETF connector tests."""

import unittest

from stock_report.connectors.etf_data import STOCKANALYSIS_ETF_URL
from stock_report.connectors.etf_data import StockAnalysisEtfClient


class StubHttpClient:
    def __init__(self, responses):
        self.responses = responses

    def get_text(self, url, params=None, headers=None):
        return self.responses[url]


class EtfDataTests(unittest.TestCase):
    def test_stockanalysis_etf_client_parses_overview_and_holdings(self) -> None:
        client = StockAnalysisEtfClient(
            http_client=StubHttpClient(
                {
                    STOCKANALYSIS_ETF_URL.format(symbol="spy"): _stockanalysis_etf_html(),
                }
            )
        )

        snapshot = client.fetch_etf("SPY")

        self.assertEqual(snapshot.as_of, "2026-03-17")
        self.assertEqual(snapshot.source, "StockAnalysis ETF")
        self.assertEqual(snapshot.metrics["asset_class"], "Equity")
        self.assertEqual(snapshot.metrics["category"], "Large Blend")
        self.assertEqual(snapshot.metrics["provider"], "State Street")
        self.assertAlmostEqual(snapshot.metrics["expense_ratio"], 0.09, places=2)
        self.assertAlmostEqual(snapshot.metrics["aum"], 612_300_000_000.0, places=1)
        self.assertEqual(snapshot.metrics["holdings_count"], 503)
        self.assertAlmostEqual(snapshot.metrics["top_10_weight"], 34.6, places=1)
        self.assertEqual(snapshot.metrics["top_holdings"][0]["symbol"], "MSFT")


def _stockanalysis_etf_html() -> str:
    return """
    <html>
      <body>
        <div><span>Asset Class</span><span>Equity</span></div>
        <div><span>Category</span><span>Large Blend</span></div>
        <div><span>Region</span><span>North America</span></div>
        <div><span>ETF Provider</span><span>State Street</span></div>
        <div><span>Index Tracked</span><span>S&P 500 Index</span></div>
        <script>
          var payload = {
            expenseRatio:"0.09%",
            aum:"$612.3B",
            peRatio:"24.1",
            dividendYield:"1.25%",
            beta:"1.00",
            holdings:503,
            inception:"Jan 22, 1993"
          };
        </script>
        <div class="card">
          <div>
            <h2>Top 10 Holdings</h2>
            <span>34.6% of assets</span>
          </div>
          <table>
            <tbody>
              <tr><td>Microsoft</td><td>MSFT</td><td>6.8%</td></tr>
              <tr><td>Apple</td><td>AAPL</td><td>6.2%</td></tr>
              <tr><td>NVIDIA</td><td>NVDA</td><td>5.4%</td></tr>
            </tbody>
          </table>
        </div>
        <div>Updated Mar 17, 2026.</div>
      </body>
    </html>
    """


if __name__ == "__main__":
    unittest.main()

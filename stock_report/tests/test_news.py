"""News connector tests."""

import unittest

from stock_report.connectors.news import GoogleNewsClient
from stock_report.connectors.news import _build_query
from stock_report.models import AssetDefinition


class StubHttpClient:
    def __init__(self, text):
        self.text = text

    def get_text(self, url, params=None):
        return self.text


class NewsTests(unittest.TestCase):
    def test_fetch_news_filters_noise_and_prioritizes_material_events(self) -> None:
        rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Why Is Sandisk Up Today? - Fast Market Desk</title>
      <link>https://example.com/price-action</link>
      <pubDate>Mon, 16 Mar 2026 22:00:00 GMT</pubDate>
      <source>Fast Market Desk</source>
    </item>
    <item>
      <title>Sandisk expands HBF standardization partnership - Example Source</title>
      <link>https://example.com/1</link>
      <pubDate>Mon, 16 Mar 2026 23:03:09 GMT</pubDate>
      <source>Example Source</source>
    </item>
    <item>
      <title>Sandisk expands HBF standardization partnership with new ecosystem push - Example Source</title>
      <link>https://example.com/dup</link>
      <pubDate>Mon, 16 Mar 2026 23:05:09 GMT</pubDate>
      <source>Example Source</source>
    </item>
    <item>
      <title>Sandisk Stock Price, Quote &amp; Chart - Chart Site</title>
      <link>https://example.com/quote</link>
      <pubDate>Tue, 17 Mar 2026 08:00:00 GMT</pubDate>
      <source>Chart Site</source>
    </item>
    <item>
      <title>The Stock Market Is Near Its Peak Dot-Com Era Valuation - Macro Source</title>
      <link>https://example.com/macro</link>
      <pubDate>Tue, 17 Mar 2026 09:00:00 GMT</pubDate>
      <source>Macro Source</source>
    </item>
    <item>
      <title>Sandisk delays production timing update - Example Source</title>
      <link>https://example.com/2</link>
      <pubDate>Tue, 17 Mar 2026 10:00:00 GMT</pubDate>
      <source>Example Source</source>
    </item>
  </channel>
</rss>
"""
        asset = AssetDefinition(
            symbol="SNDK",
            name="Sandisk",
            asset_type="stock",
            theme="hbf_memory_storage",
        )
        client = GoogleNewsClient(http_client=StubHttpClient(rss))

        items = client.fetch_news(asset, days=7, limit=2)

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].category, "standardization")
        self.assertIn("표준화", items[0].summary_ko)
        self.assertEqual(items[0].impact, "positive")
        self.assertIn("standardization", items[0].tags)
        self.assertEqual(items[1].category, "supply_chain")
        self.assertEqual(items[1].impact, "negative")
        self.assertIn("영향 판단은 부정", items[1].summary_ko)
        self.assertGreater(items[0].priority_score, items[1].priority_score)

    def test_fetch_news_sorts_earnings_ahead_of_price_action(self) -> None:
        rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Why Is NVIDIA Up Today? - Market Pulse</title>
      <link>https://example.com/price</link>
      <pubDate>Tue, 17 Mar 2026 08:00:00 GMT</pubDate>
      <source>Market Pulse</source>
    </item>
    <item>
      <title>NVIDIA beats revenue guidance as AI demand expands - Example Source</title>
      <link>https://example.com/earnings</link>
      <pubDate>Tue, 17 Mar 2026 09:00:00 GMT</pubDate>
      <source>Example Source</source>
    </item>
  </channel>
</rss>
"""
        asset = AssetDefinition(
            symbol="NVDA",
            name="NVIDIA",
            asset_type="stock",
            theme="ai_compute",
        )
        client = GoogleNewsClient(http_client=StubHttpClient(rss))

        items = client.fetch_news(asset, days=7, limit=2)

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].category, "earnings")
        self.assertEqual(items[1].category, "price_action")
        self.assertGreater(items[0].priority_score, items[1].priority_score)
        self.assertIn("실적", items[0].summary_ko)

    def test_build_query_uses_etf_specific_terms_without_raw_ticker(self) -> None:
        asset = AssetDefinition(
            symbol="SPY",
            name="SPDR S&P 500 ETF Trust",
            asset_type="etf",
            theme="primary_benchmark",
        )

        query = _build_query(asset, days=7)

        self.assertIn('"SPDR S&P 500 ETF Trust"', query)
        self.assertIn('"SPY ETF"', query)
        self.assertNotIn(" OR SPY)", query)


if __name__ == "__main__":
    unittest.main()

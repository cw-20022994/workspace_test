"""Watchlist loading tests."""

from pathlib import Path
import unittest

from stock_report.watchlist import load_watchlist


class WatchlistTests(unittest.TestCase):
    def test_loads_hbf_and_korea_assets(self) -> None:
        root = Path(__file__).resolve().parents[1]
        watchlist = load_watchlist(str(root / "config" / "watchlist.example.yaml"))

        sndk = watchlist.get_asset("SNDK")
        samsung = watchlist.get_asset("005930.KS")

        self.assertEqual(sndk.theme, "hbf_memory_storage")
        self.assertEqual(samsung.name, "Samsung Electronics")
        self.assertEqual(samsung.market, "KR")


if __name__ == "__main__":
    unittest.main()

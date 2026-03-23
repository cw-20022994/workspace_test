from __future__ import annotations

import unittest

from coin_partner.cli import build_live_buy_confirmation


class CliTest(unittest.TestCase):
    def test_live_buy_confirmation_token_format(self) -> None:
        self.assertEqual(build_live_buy_confirmation("KRW-BTC", 10000), "BUY:KRW-BTC:10000")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from trade_studio.core.models import ExchangeName, TradingMode, build_default_profile


class ProfileConfigTests(unittest.TestCase):
    def test_default_profile_roundtrip(self) -> None:
        profile = build_default_profile()

        payload = profile.to_dict()
        restored = profile.from_dict(payload)

        self.assertEqual(restored.exchange, ExchangeName.KRAKEN)
        self.assertEqual(restored.mode, TradingMode.PAPER)
        self.assertEqual(restored.markets, ["BTC/USD", "ETH/USD"])
        self.assertEqual(restored.strategy.template.value, "pullback")

    def test_validation_rejects_entry_below_exchange_minimum(self) -> None:
        profile = build_default_profile()
        profile.capital.entry_quote = 25.0
        profile.capital.minimum_order_quote = 50.0

        self.assertIn("Entry size cannot be below minimum order size.", profile.validate())


if __name__ == "__main__":
    unittest.main()


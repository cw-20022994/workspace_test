from __future__ import annotations

import unittest

from coin_partner.prototype_data import build_prototype_snapshot


class PrototypeDataTest(unittest.TestCase):
    def test_snapshot_contains_expected_sections(self) -> None:
        snapshot = build_prototype_snapshot()

        self.assertEqual(snapshot.profile_name, "Momentum Pullback / Asia Session")
        self.assertEqual(len(snapshot.metrics), 4)
        self.assertGreaterEqual(len(snapshot.positions), 3)
        self.assertGreaterEqual(len(snapshot.strategy_fields), 4)
        self.assertGreaterEqual(len(snapshot.market_pulse), 10)


if __name__ == "__main__":
    unittest.main()

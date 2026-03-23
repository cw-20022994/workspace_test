from __future__ import annotations

import unittest
from datetime import datetime, timezone

from coin_partner.cli import is_fill_finalized_order_state, parse_exchange_datetime


class ImportHelperTest(unittest.TestCase):
    def test_parse_exchange_datetime_with_z_suffix(self) -> None:
        parsed = parse_exchange_datetime("2026-03-21T10:15:30Z")
        self.assertEqual(parsed, datetime(2026, 3, 21, 10, 15, 30, tzinfo=timezone.utc))

    def test_parse_exchange_datetime_with_offset(self) -> None:
        parsed = parse_exchange_datetime("2026-03-21T19:15:30+09:00")
        self.assertEqual(parsed.isoformat(), "2026-03-21T19:15:30+09:00")

    def test_fill_finalized_order_states(self) -> None:
        self.assertTrue(is_fill_finalized_order_state("done"))
        self.assertTrue(is_fill_finalized_order_state("cancel"))
        self.assertFalse(is_fill_finalized_order_state("wait"))


if __name__ == "__main__":
    unittest.main()

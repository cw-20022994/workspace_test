from __future__ import annotations

import unittest

from coin_partner.models import BotState


class BotStateModelTest(unittest.TestCase):
    def test_loads_legacy_single_position_payload_into_positions_list(self) -> None:
        state = BotState.from_dict(
            {
                "paper_cash_krw": 100000.0,
                "daily": {
                    "trading_date": "2026-03-21",
                    "trade_count": 1,
                    "realized_pnl_krw": 0.0,
                    "consecutive_stop_losses": 0,
                    "stopped_for_day": False,
                    "cooldown_until": None,
                    "market_cooldowns": {},
                },
                "position": {
                    "market": "KRW-BTC",
                    "volume": 0.0001,
                    "entry_price": 100000000.0,
                    "invested_krw": 10000.0,
                    "opened_at": "2026-03-21T13:40:00+09:00",
                    "stop_price": 98500000.0,
                    "take_profit_price": 102300000.0,
                    "breakeven_armed": False,
                    "order_id": "abc",
                    "entry_fee_krw": 5.0,
                },
            }
        )

        self.assertEqual(len(state.positions), 1)
        self.assertEqual(state.positions[0].market, "KRW-BTC")


if __name__ == "__main__":
    unittest.main()

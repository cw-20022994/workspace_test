from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from coin_partner.bot import TradingBot
from coin_partner.config import AppConfig, BotConfig, RiskConfig, StorageConfig, StrategyConfig, TelegramConfig, UpbitConfig
from coin_partner.models import BotState, DailyState, Position


class DummyNotifier:
    def __init__(self) -> None:
        self.settings = type(
            "Settings",
            (),
            {
                "enabled": True,
                "notify_heartbeat": True,
                "notify_daily_summary": True,
            },
        )()
        self.daily_summaries = []
        self.heartbeats = []

    def notify_daily_summary(self, summary_date, state, wins, losses, best_trade_pnl_krw, worst_trade_pnl_krw):
        self.daily_summaries.append(
            {
                "summary_date": summary_date,
                "wins": wins,
                "losses": losses,
                "best": best_trade_pnl_krw,
                "worst": worst_trade_pnl_krw,
                "daily_pnl": state.daily.realized_pnl_krw,
            }
        )
        return True

    def notify_heartbeat(self, state, now, mark_prices=None):
        self.heartbeats.append(
            {
                "now": now.isoformat(),
                "mark_prices": mark_prices,
                "trade_count": state.daily.trade_count,
            }
        )
        return True


class BotNotificationSchedulingTest(unittest.TestCase):
    def _app_config(self, state_path: Path) -> AppConfig:
        return AppConfig(
            bot=BotConfig(
                mode="paper",
                timezone="Asia/Seoul",
                poll_interval_seconds=60,
                log_level="INFO",
                allow_new_entries=True,
                paper_starting_cash_krw=200000,
                paper_fee_rate=0.0005,
                paper_slippage_pct=0.0004,
                live_capital_limit_krw=None,
            ),
            storage=StorageConfig(state_file=state_path),
            upbit=UpbitConfig(
                base_url="https://api.upbit.com/v1",
                access_key_env="UPBIT_ACCESS_KEY",
                secret_key_env="UPBIT_SECRET_KEY",
                request_timeout_seconds=10,
            ),
            telegram=TelegramConfig(
                enabled=False,
                bot_token_env="TELEGRAM_BOT_TOKEN",
                chat_id="",
                parse_mode="HTML",
                send_silently=False,
                request_timeout_seconds=10,
                notify_entry=True,
                notify_exit=True,
                notify_daily_stop=True,
                notify_daily_summary=True,
                daily_summary_hour=23,
                daily_summary_minute=0,
                notify_heartbeat=True,
                heartbeat_interval_minutes=60,
                notify_errors=True,
                error_cooldown_minutes=15,
            ),
            strategy=StrategyConfig(
                markets=["KRW-BTC"],
                entry_amount_krw=30000,
                ema_pullback_tolerance_pct=0.0025,
                min_volume_ratio=1.3,
                rsi_period=14,
                rsi_min=52,
                rsi_max=68,
                overheat_10m_limit_pct=0.018,
                relaxed_hourly_trend_markets=[],
                hourly_ema20_rising_bars=3,
            ),
            risk=RiskConfig(
                max_open_positions=1,
                max_trades_per_day=5,
                daily_loss_limit_krw=7000,
                max_consecutive_stop_losses=3,
                stop_loss_pct=0.015,
                take_profit_pct=0.023,
                breakeven_trigger_pct=0.014,
                breakeven_offset_pct=-0.002,
                max_hold_minutes=75,
                cooldown_after_stop_minutes=10,
                cooldown_after_take_profit_minutes=5,
                same_market_cooldown_minutes=10,
                min_krw_balance_buffer=10000,
            ),
        )

    def test_daily_summary_is_sent_for_previous_day_on_rollover(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bot = TradingBot(self._app_config(Path(temp_dir) / "state.json"))
            notifier = DummyNotifier()
            bot.notifier = notifier  # type: ignore[assignment]

            state = BotState(
                paper_cash_krw=205000.0,
                daily=DailyState(
                    trading_date=datetime(2026, 3, 20).date(),
                    trade_count=3,
                    realized_pnl_krw=2500.0,
                ),
                history=[
                    {"type": "exit", "at": "2026-03-20T10:00:00+09:00", "pnl_krw": 1300.0},
                    {"type": "exit", "at": "2026-03-20T12:30:00+09:00", "pnl_krw": -400.0},
                    {"type": "exit", "at": "2026-03-20T14:30:00+09:00", "pnl_krw": 1600.0},
                ],
            )

            bot._maybe_send_daily_summary(state, datetime(2026, 3, 21, 0, 5, tzinfo=bot.tz))

            self.assertEqual(state.last_daily_summary_date, "2026-03-20")
            self.assertEqual(len(notifier.daily_summaries), 1)
            self.assertEqual(notifier.daily_summaries[0]["wins"], 2)
            self.assertEqual(notifier.daily_summaries[0]["losses"], 1)

    def test_heartbeat_respects_interval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bot = TradingBot(self._app_config(Path(temp_dir) / "state.json"))
            notifier = DummyNotifier()
            bot.notifier = notifier  # type: ignore[assignment]

            state = BotState(
                paper_cash_krw=200000.0,
                daily=DailyState(trading_date=datetime(2026, 3, 20).date(), trade_count=1),
            )
            now = datetime(2026, 3, 20, 10, 0, tzinfo=bot.tz)

            bot._maybe_send_heartbeat(state, now, {})
            bot._maybe_send_heartbeat(state, datetime(2026, 3, 20, 10, 30, tzinfo=bot.tz), {})
            bot._maybe_send_heartbeat(state, datetime(2026, 3, 20, 11, 1, tzinfo=bot.tz), {})

            self.assertEqual(len(notifier.heartbeats), 2)
            self.assertEqual(state.last_heartbeat_at, "2026-03-20T11:01:00+09:00")

    def test_live_available_krw_is_capped_by_live_capital_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._app_config(Path(temp_dir) / "state.json")
            config.bot.mode = "live"
            config.bot.live_capital_limit_krw = 200000.0

            bot = TradingBot(config)
            bot.client.get_krw_balance = lambda: 910000.0  # type: ignore[method-assign]

            state = BotState(
                paper_cash_krw=0.0,
                daily=DailyState(trading_date=datetime(2026, 3, 20).date()),
            )
            self.assertEqual(bot._available_krw(state), 200000.0)

    def test_live_available_krw_subtracts_deployed_positions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._app_config(Path(temp_dir) / "state.json")
            config.bot.mode = "live"
            config.bot.live_capital_limit_krw = 200000.0

            bot = TradingBot(config)
            bot.client.get_krw_balance = lambda: 910000.0  # type: ignore[method-assign]

            state = BotState(
                paper_cash_krw=0.0,
                daily=DailyState(trading_date=datetime(2026, 3, 20).date()),
                positions=[
                    Position(
                        market="KRW-BTC",
                        volume=0.0004,
                        entry_price=100000000.0,
                        invested_krw=50000.0,
                        opened_at=datetime(2026, 3, 20, 10, 0),
                        stop_price=98500000.0,
                        take_profit_price=102300000.0,
                        entry_fee_krw=25.0,
                    )
                ],
            )
            self.assertEqual(bot._available_krw(state), 149975.0)


if __name__ == "__main__":
    unittest.main()

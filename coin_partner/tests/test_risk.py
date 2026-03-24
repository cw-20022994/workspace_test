from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from coin_partner.config import AppConfig, BotConfig, RiskConfig, StorageConfig, StrategyConfig, TelegramConfig, UpbitConfig
from coin_partner.models import BotState, DailyState
from coin_partner.risk import RiskManager


class RiskManagerTest(unittest.TestCase):
    def test_blocks_entry_after_daily_loss_limit(self) -> None:
        config = AppConfig(
            bot=BotConfig(
                mode="paper",
                timezone="Asia/Seoul",
                poll_interval_seconds=60,
                log_level="INFO",
                allow_new_entries=True,
                paper_starting_cash_krw=200000,
                paper_fee_rate=0.0005,
                paper_slippage_pct=0.0004,
            ),
            storage=StorageConfig(state_file=None),  # type: ignore[arg-type]
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
        risk = RiskManager(config)
        tz = ZoneInfo("Asia/Seoul")
        state = BotState(
            paper_cash_krw=200000,
            daily=DailyState(
                trading_date=datetime(2026, 3, 20, tzinfo=tz).date(),
                realized_pnl_krw=-8000,
            ),
        )

        allowed, reason = risk.can_enter(state, "KRW-BTC", datetime(2026, 3, 20, 12, 0, tzinfo=tz), 200000)
        self.assertFalse(allowed)
        self.assertEqual(reason, "daily_loss_limit_reached")

    def test_blocks_entry_when_live_capital_limit_is_too_small(self) -> None:
        config = AppConfig(
            bot=BotConfig(
                mode="live",
                timezone="Asia/Seoul",
                poll_interval_seconds=60,
                log_level="INFO",
                allow_new_entries=True,
                paper_starting_cash_krw=200000,
                paper_fee_rate=0.0005,
                paper_slippage_pct=0.0004,
                live_capital_limit_krw=35000,
            ),
            storage=StorageConfig(state_file=None),  # type: ignore[arg-type]
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
        risk = RiskManager(config)
        tz = ZoneInfo("Asia/Seoul")
        state = BotState(
            paper_cash_krw=200000,
            daily=DailyState(trading_date=datetime(2026, 3, 20, tzinfo=tz).date()),
        )

        allowed, reason = risk.can_enter(
            state,
            "KRW-BTC",
            datetime(2026, 3, 20, 12, 0, tzinfo=tz),
            available_krw=35000,
            capital_limit_remaining_krw=35000,
        )
        self.assertFalse(allowed)
        self.assertEqual(reason, "live_capital_limit_reached")

    def test_blocks_entry_when_max_open_positions_reached(self) -> None:
        config = AppConfig(
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
            storage=StorageConfig(state_file=None),  # type: ignore[arg-type]
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
                max_open_positions=2,
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
        risk = RiskManager(config)
        tz = ZoneInfo("Asia/Seoul")
        state = BotState(
            paper_cash_krw=200000,
            daily=DailyState(trading_date=datetime(2026, 3, 20, tzinfo=tz).date()),
            positions=[
                risk.build_position("KRW-BTC", 100000000.0, 0.0003, 30000.0, datetime(2026, 3, 20, 10, 0, tzinfo=tz)),
                risk.build_position("KRW-ETH", 3000000.0, 0.01, 30000.0, datetime(2026, 3, 20, 11, 0, tzinfo=tz)),
            ],
        )

        allowed, reason = risk.can_enter(
            state,
            "KRW-XRP",
            datetime(2026, 3, 20, 12, 0, tzinfo=tz),
            available_krw=200000,
        )
        self.assertFalse(allowed)
        self.assertEqual(reason, "max_open_positions_reached")

    def test_blocks_duplicate_market_entry_while_position_is_open(self) -> None:
        config = AppConfig(
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
            storage=StorageConfig(state_file=None),  # type: ignore[arg-type]
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
                markets=["KRW-BTC", "KRW-ETH"],
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
                max_open_positions=10,
                max_trades_per_day=0,
                daily_loss_limit_krw=10000,
                max_consecutive_stop_losses=0,
                stop_loss_pct=0.015,
                take_profit_pct=0.023,
                breakeven_trigger_pct=0.014,
                breakeven_offset_pct=-0.002,
                max_hold_minutes=60,
                cooldown_after_stop_minutes=10,
                cooldown_after_take_profit_minutes=0,
                same_market_cooldown_minutes=10,
                min_krw_balance_buffer=10000,
            ),
        )
        risk = RiskManager(config)
        tz = ZoneInfo("Asia/Seoul")
        state = BotState(
            paper_cash_krw=400000,
            daily=DailyState(trading_date=datetime(2026, 3, 20, tzinfo=tz).date()),
            positions=[
                risk.build_position("KRW-ETH", 3200000.0, 0.01, 30000.0, datetime(2026, 3, 20, 11, 0, tzinfo=tz)),
            ],
        )

        allowed, reason = risk.can_enter(
            state,
            "KRW-ETH",
            datetime(2026, 3, 20, 12, 0, tzinfo=tz),
            available_krw=400000,
        )
        self.assertFalse(allowed)
        self.assertEqual(reason, "market_position_open")

    def test_exits_trade_early_when_it_fails_to_make_progress(self) -> None:
        config = AppConfig(
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
            storage=StorageConfig(state_file=None),  # type: ignore[arg-type]
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
                max_hold_minutes=60,
                cooldown_after_stop_minutes=10,
                cooldown_after_take_profit_minutes=5,
                same_market_cooldown_minutes=10,
                min_krw_balance_buffer=10000,
                early_exit_check_minutes=20,
                early_exit_min_pnl_pct=0.004,
            ),
        )
        risk = RiskManager(config)
        tz = ZoneInfo("Asia/Seoul")
        position = risk.build_position(
            "KRW-BTC",
            100000000.0,
            0.0003,
            30000.0,
            datetime(2026, 3, 20, 10, 0, tzinfo=tz),
        )

        decision = risk.evaluate_exit(position, 100200000.0, datetime(2026, 3, 20, 10, 20, tzinfo=tz))
        self.assertTrue(decision.should_exit)
        self.assertEqual(decision.reason, "stalled_trade_exit")

    def test_zero_limits_disable_trade_count_and_consecutive_stop_loss_blocks(self) -> None:
        config = AppConfig(
            bot=BotConfig(
                mode="paper",
                timezone="Asia/Seoul",
                poll_interval_seconds=60,
                log_level="INFO",
                allow_new_entries=True,
                paper_starting_cash_krw=200000,
                paper_fee_rate=0.0005,
                paper_slippage_pct=0.0004,
            ),
            storage=StorageConfig(state_file=None),  # type: ignore[arg-type]
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
                max_open_positions=10,
                max_trades_per_day=0,
                daily_loss_limit_krw=10000,
                max_consecutive_stop_losses=0,
                stop_loss_pct=0.015,
                take_profit_pct=0.023,
                breakeven_trigger_pct=0.014,
                breakeven_offset_pct=-0.002,
                max_hold_minutes=60,
                cooldown_after_stop_minutes=10,
                cooldown_after_take_profit_minutes=0,
                same_market_cooldown_minutes=5,
                min_krw_balance_buffer=10000,
            ),
        )
        risk = RiskManager(config)
        tz = ZoneInfo("Asia/Seoul")
        state = BotState(
            paper_cash_krw=200000,
            daily=DailyState(
                trading_date=datetime(2026, 3, 20, tzinfo=tz).date(),
                trade_count=99,
                consecutive_stop_losses=99,
            ),
        )

        allowed, reason = risk.can_enter(
            state,
            "KRW-BTC",
            datetime(2026, 3, 20, 12, 0, tzinfo=tz),
            available_krw=200000,
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, "ok")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Union


@dataclass
class BotConfig:
    mode: str
    timezone: str
    poll_interval_seconds: int
    log_level: str
    allow_new_entries: bool
    paper_starting_cash_krw: float
    paper_fee_rate: float
    paper_slippage_pct: float
    live_capital_limit_krw: Optional[float] = None


@dataclass
class StorageConfig:
    state_file: Path


@dataclass
class UpbitConfig:
    base_url: str
    access_key_env: str
    secret_key_env: str
    request_timeout_seconds: int

    @property
    def access_key(self) -> Optional[str]:
        return os.getenv(self.access_key_env)

    @property
    def secret_key(self) -> Optional[str]:
        return os.getenv(self.secret_key_env)


@dataclass
class TelegramConfig:
    enabled: bool
    bot_token_env: str
    chat_id: str
    parse_mode: str
    send_silently: bool
    request_timeout_seconds: int
    notify_entry: bool
    notify_exit: bool
    notify_daily_stop: bool
    notify_daily_summary: bool
    daily_summary_hour: int
    daily_summary_minute: int
    notify_heartbeat: bool
    heartbeat_interval_minutes: int
    notify_errors: bool
    error_cooldown_minutes: int

    @property
    def bot_token(self) -> Optional[str]:
        return os.getenv(self.bot_token_env)


@dataclass
class StrategyConfig:
    markets: list[str]
    entry_amount_krw: float
    ema_pullback_tolerance_pct: float
    min_volume_ratio: float
    rsi_period: int
    rsi_min: float
    rsi_max: float
    overheat_10m_limit_pct: float
    relaxed_hourly_trend_markets: list[str]
    hourly_ema20_rising_bars: int


@dataclass
class RiskConfig:
    max_open_positions: int
    max_trades_per_day: int
    daily_loss_limit_krw: float
    max_consecutive_stop_losses: int
    stop_loss_pct: float
    take_profit_pct: float
    breakeven_trigger_pct: float
    breakeven_offset_pct: float
    max_hold_minutes: int
    cooldown_after_stop_minutes: int
    cooldown_after_take_profit_minutes: int
    same_market_cooldown_minutes: int
    min_krw_balance_buffer: float
    early_exit_check_minutes: int = 0
    early_exit_min_pnl_pct: float = 0.0


@dataclass
class AppConfig:
    bot: BotConfig
    storage: StorageConfig
    upbit: UpbitConfig
    telegram: TelegramConfig
    strategy: StrategyConfig
    risk: RiskConfig

    @classmethod
    def load(cls, path: Union[str, Path]) -> "AppConfig":
        config_path = Path(path)
        raw = _load_tomlish(config_path)
        base_dir = config_path.parent

        bot = BotConfig(
            mode=str(raw["bot"]["mode"]).lower(),
            timezone=str(raw["bot"].get("timezone", "Asia/Seoul")),
            poll_interval_seconds=int(raw["bot"].get("poll_interval_seconds", 60)),
            log_level=str(raw["bot"].get("log_level", "INFO")).upper(),
            allow_new_entries=bool(raw["bot"].get("allow_new_entries", True)),
            paper_starting_cash_krw=float(raw["bot"].get("paper_starting_cash_krw", 200000)),
            paper_fee_rate=float(raw["bot"].get("paper_fee_rate", 0.0005)),
            paper_slippage_pct=float(raw["bot"].get("paper_slippage_pct", 0.0004)),
            live_capital_limit_krw=(
                float(raw["bot"]["live_capital_limit_krw"])
                if raw["bot"].get("live_capital_limit_krw") is not None
                else None
            ),
        )

        storage = StorageConfig(
            state_file=(base_dir / str(raw["storage"].get("state_file", "data/state.json"))).resolve()
        )

        upbit = UpbitConfig(
            base_url=str(raw["upbit"].get("base_url", "https://api.upbit.com/v1")),
            access_key_env=str(raw["upbit"].get("access_key_env", "UPBIT_ACCESS_KEY")),
            secret_key_env=str(raw["upbit"].get("secret_key_env", "UPBIT_SECRET_KEY")),
            request_timeout_seconds=int(raw["upbit"].get("request_timeout_seconds", 10)),
        )

        telegram_raw = raw.get("telegram", {})
        telegram = TelegramConfig(
            enabled=bool(telegram_raw.get("enabled", False)),
            bot_token_env=str(telegram_raw.get("bot_token_env", "TELEGRAM_BOT_TOKEN")),
            chat_id=str(telegram_raw.get("chat_id", "")).strip(),
            parse_mode=str(telegram_raw.get("parse_mode", "HTML")).strip() or "HTML",
            send_silently=bool(telegram_raw.get("send_silently", False)),
            request_timeout_seconds=int(telegram_raw.get("request_timeout_seconds", 10)),
            notify_entry=bool(telegram_raw.get("notify_entry", True)),
            notify_exit=bool(telegram_raw.get("notify_exit", True)),
            notify_daily_stop=bool(telegram_raw.get("notify_daily_stop", True)),
            notify_daily_summary=bool(telegram_raw.get("notify_daily_summary", True)),
            daily_summary_hour=int(telegram_raw.get("daily_summary_hour", 23)),
            daily_summary_minute=int(telegram_raw.get("daily_summary_minute", 0)),
            notify_heartbeat=bool(telegram_raw.get("notify_heartbeat", True)),
            heartbeat_interval_minutes=int(telegram_raw.get("heartbeat_interval_minutes", 60)),
            notify_errors=bool(telegram_raw.get("notify_errors", True)),
            error_cooldown_minutes=int(telegram_raw.get("error_cooldown_minutes", 15)),
        )

        strategy = StrategyConfig(
            markets=[str(item) for item in raw["strategy"]["markets"]],
            entry_amount_krw=float(raw["strategy"]["entry_amount_krw"]),
            ema_pullback_tolerance_pct=float(raw["strategy"]["ema_pullback_tolerance_pct"]),
            min_volume_ratio=float(raw["strategy"]["min_volume_ratio"]),
            rsi_period=int(raw["strategy"]["rsi_period"]),
            rsi_min=float(raw["strategy"]["rsi_min"]),
            rsi_max=float(raw["strategy"]["rsi_max"]),
            overheat_10m_limit_pct=float(raw["strategy"]["overheat_10m_limit_pct"]),
            relaxed_hourly_trend_markets=[
                str(item) for item in raw["strategy"].get("relaxed_hourly_trend_markets", [])
            ],
            hourly_ema20_rising_bars=int(raw["strategy"].get("hourly_ema20_rising_bars", 3)),
        )

        risk = RiskConfig(
            max_open_positions=int(raw["risk"]["max_open_positions"]),
            max_trades_per_day=int(raw["risk"]["max_trades_per_day"]),
            daily_loss_limit_krw=float(raw["risk"]["daily_loss_limit_krw"]),
            max_consecutive_stop_losses=int(raw["risk"]["max_consecutive_stop_losses"]),
            stop_loss_pct=float(raw["risk"]["stop_loss_pct"]),
            take_profit_pct=float(raw["risk"]["take_profit_pct"]),
            breakeven_trigger_pct=float(raw["risk"]["breakeven_trigger_pct"]),
            breakeven_offset_pct=float(raw["risk"]["breakeven_offset_pct"]),
            max_hold_minutes=int(raw["risk"]["max_hold_minutes"]),
            early_exit_check_minutes=int(raw["risk"].get("early_exit_check_minutes", 0)),
            early_exit_min_pnl_pct=float(raw["risk"].get("early_exit_min_pnl_pct", 0.0)),
            cooldown_after_stop_minutes=int(raw["risk"]["cooldown_after_stop_minutes"]),
            cooldown_after_take_profit_minutes=int(raw["risk"]["cooldown_after_take_profit_minutes"]),
            same_market_cooldown_minutes=int(raw["risk"]["same_market_cooldown_minutes"]),
            min_krw_balance_buffer=float(raw["risk"]["min_krw_balance_buffer"]),
        )

        config = cls(bot=bot, storage=storage, upbit=upbit, telegram=telegram, strategy=strategy, risk=risk)
        config.validate()
        return config

    def validate(self) -> None:
        if self.bot.mode not in {"paper", "live"}:
            raise ValueError("bot.mode must be 'paper' or 'live'")
        if self.bot.poll_interval_seconds <= 0:
            raise ValueError("bot.poll_interval_seconds must be positive")
        if self.bot.live_capital_limit_krw is not None and self.bot.live_capital_limit_krw < 5000:
            raise ValueError("bot.live_capital_limit_krw must be at least 5000 KRW when set")
        if self.strategy.entry_amount_krw < 5000:
            raise ValueError("strategy.entry_amount_krw must be at least 5000 KRW")
        if self.strategy.hourly_ema20_rising_bars <= 0:
            raise ValueError("strategy.hourly_ema20_rising_bars must be positive")
        if self.risk.stop_loss_pct <= 0 or self.risk.take_profit_pct <= 0:
            raise ValueError("risk stop/take profit must be positive")
        if self.risk.early_exit_check_minutes < 0:
            raise ValueError("risk.early_exit_check_minutes cannot be negative")
        if self.risk.early_exit_min_pnl_pct < 0:
            raise ValueError("risk.early_exit_min_pnl_pct cannot be negative")
        if self.risk.max_trades_per_day < 0:
            raise ValueError("risk.max_trades_per_day cannot be negative")
        if self.risk.max_consecutive_stop_losses < 0:
            raise ValueError("risk.max_consecutive_stop_losses cannot be negative")
        if self.risk.max_open_positions <= 0:
            raise ValueError("risk.max_open_positions must be positive")
        if not self.strategy.markets:
            raise ValueError("strategy.markets cannot be empty")
        if self.bot.mode == "live" and (not self.upbit.access_key or not self.upbit.secret_key):
            raise ValueError("live mode requires access and secret keys in environment variables")
        if not 0 <= self.telegram.daily_summary_hour <= 23:
            raise ValueError("telegram.daily_summary_hour must be between 0 and 23")
        if not 0 <= self.telegram.daily_summary_minute <= 59:
            raise ValueError("telegram.daily_summary_minute must be between 0 and 59")
        if self.telegram.heartbeat_interval_minutes <= 0:
            raise ValueError("telegram.heartbeat_interval_minutes must be positive")
        if self.telegram.error_cooldown_minutes < 0:
            raise ValueError("telegram.error_cooldown_minutes cannot be negative")
        if self.telegram.enabled and (not self.telegram.bot_token or not self.telegram.chat_id):
            raise ValueError("telegram.enabled requires bot token env and chat_id")


def _load_tomlish(path: Path) -> Dict[str, Dict[str, Any]]:
    parsed: Dict[str, Dict[str, Any]] = {}
    current_section: Optional[str] = None
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1].strip()
            parsed[current_section] = {}
            continue
        if current_section is None or "=" not in line:
            raise ValueError("Invalid config line {0}: {1}".format(line_number, raw_line))
        key, value = line.split("=", 1)
        parsed[current_section][key.strip()] = _parse_value(value.strip())
    return parsed


def _parse_value(raw_value: str) -> Any:
    lowered = raw_value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        return ast.literal_eval(raw_value)
    except (ValueError, SyntaxError):
        if "." in raw_value:
            return float(raw_value)
        return int(raw_value)

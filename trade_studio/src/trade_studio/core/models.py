from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ExchangeName(str, Enum):
    KRAKEN = "kraken"
    OKX = "okx"
    BYBIT = "bybit"


class TradingMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class StrategyTemplate(str, Enum):
    PULLBACK = "pullback"
    BREAKOUT = "breakout"
    RSI_REVERSION = "rsi_reversion"


@dataclass
class CapitalSettings:
    total_quote: float = 5_000.0
    entry_quote: float = 250.0
    minimum_order_quote: float = 50.0
    reserve_quote: float = 250.0
    max_open_positions: int = 3

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_quote": self.total_quote,
            "entry_quote": self.entry_quote,
            "minimum_order_quote": self.minimum_order_quote,
            "reserve_quote": self.reserve_quote,
            "max_open_positions": self.max_open_positions,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CapitalSettings":
        return cls(
            total_quote=float(payload.get("total_quote", 5_000.0)),
            entry_quote=float(payload.get("entry_quote", 250.0)),
            minimum_order_quote=float(payload.get("minimum_order_quote", 50.0)),
            reserve_quote=float(payload.get("reserve_quote", 250.0)),
            max_open_positions=int(payload.get("max_open_positions", 3)),
        )


@dataclass
class RiskSettings:
    stop_loss_pct: float = 0.015
    take_profit_pct: float = 0.03
    trailing_stop_pct: float = 0.0
    daily_loss_limit_quote: float = 250.0
    max_trades_per_day: int = 8
    max_consecutive_losses: int = 3
    cooldown_after_exit_minutes: int = 5
    cooldown_after_stop_minutes: int = 15

    def to_dict(self) -> dict[str, Any]:
        return {
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "trailing_stop_pct": self.trailing_stop_pct,
            "daily_loss_limit_quote": self.daily_loss_limit_quote,
            "max_trades_per_day": self.max_trades_per_day,
            "max_consecutive_losses": self.max_consecutive_losses,
            "cooldown_after_exit_minutes": self.cooldown_after_exit_minutes,
            "cooldown_after_stop_minutes": self.cooldown_after_stop_minutes,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RiskSettings":
        return cls(
            stop_loss_pct=float(payload.get("stop_loss_pct", 0.015)),
            take_profit_pct=float(payload.get("take_profit_pct", 0.03)),
            trailing_stop_pct=float(payload.get("trailing_stop_pct", 0.0)),
            daily_loss_limit_quote=float(payload.get("daily_loss_limit_quote", 250.0)),
            max_trades_per_day=int(payload.get("max_trades_per_day", 8)),
            max_consecutive_losses=int(payload.get("max_consecutive_losses", 3)),
            cooldown_after_exit_minutes=int(payload.get("cooldown_after_exit_minutes", 5)),
            cooldown_after_stop_minutes=int(payload.get("cooldown_after_stop_minutes", 15)),
        )


@dataclass
class ScheduleSettings:
    timezone: str = "UTC"
    active_weekdays: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])
    session_start: str = "00:00"
    session_end: str = "23:59"
    poll_interval_seconds: int = 30

    def to_dict(self) -> dict[str, Any]:
        return {
            "timezone": self.timezone,
            "active_weekdays": list(self.active_weekdays),
            "session_start": self.session_start,
            "session_end": self.session_end,
            "poll_interval_seconds": self.poll_interval_seconds,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ScheduleSettings":
        return cls(
            timezone=str(payload.get("timezone", "UTC")),
            active_weekdays=[int(value) for value in payload.get("active_weekdays", [0, 1, 2, 3, 4, 5, 6])],
            session_start=str(payload.get("session_start", "00:00")),
            session_end=str(payload.get("session_end", "23:59")),
            poll_interval_seconds=int(payload.get("poll_interval_seconds", 30)),
        )


@dataclass
class StrategySettings:
    template: StrategyTemplate = StrategyTemplate.PULLBACK
    timeframe: str = "5m"
    indicators: dict[str, bool] = field(
        default_factory=lambda: {
            "ema_filter": True,
            "volume_filter": True,
            "rsi_filter": True,
            "higher_timeframe_filter": True,
        }
    )
    parameters: dict[str, float] = field(
        default_factory=lambda: {
            "ema_fast": 20.0,
            "ema_slow": 50.0,
            "volume_ratio": 1.5,
            "rsi_min": 50.0,
            "rsi_max": 68.0,
            "overheat_limit_pct": 0.02,
        }
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "template": self.template.value,
            "timeframe": self.timeframe,
            "indicators": dict(self.indicators),
            "parameters": dict(self.parameters),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StrategySettings":
        return cls(
            template=StrategyTemplate(str(payload.get("template", StrategyTemplate.PULLBACK.value))),
            timeframe=str(payload.get("timeframe", "5m")),
            indicators={str(key): bool(value) for key, value in payload.get("indicators", {}).items()},
            parameters={str(key): float(value) for key, value in payload.get("parameters", {}).items()},
        )


@dataclass
class ProfileConfig:
    name: str
    exchange: ExchangeName
    mode: TradingMode
    base_currency: str
    markets: list[str]
    capital: CapitalSettings = field(default_factory=CapitalSettings)
    risk: RiskSettings = field(default_factory=RiskSettings)
    schedule: ScheduleSettings = field(default_factory=ScheduleSettings)
    strategy: StrategySettings = field(default_factory=StrategySettings)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.name.strip():
            errors.append("Profile name is required.")
        if not self.markets:
            errors.append("At least one market must be selected.")
        if len(set(self.markets)) != len(self.markets):
            errors.append("Markets must be unique.")
        if self.capital.entry_quote < self.capital.minimum_order_quote:
            errors.append("Entry size cannot be below minimum order size.")
        if self.capital.total_quote <= self.capital.reserve_quote:
            errors.append("Total capital must be larger than reserve capital.")
        if self.capital.max_open_positions <= 0:
            errors.append("Max open positions must be positive.")
        if self.risk.stop_loss_pct <= 0 or self.risk.take_profit_pct <= 0:
            errors.append("Stop loss and take profit must be positive.")
        if self.schedule.poll_interval_seconds <= 0:
            errors.append("Poll interval must be positive.")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "exchange": self.exchange.value,
            "mode": self.mode.value,
            "base_currency": self.base_currency,
            "markets": list(self.markets),
            "capital": self.capital.to_dict(),
            "risk": self.risk.to_dict(),
            "schedule": self.schedule.to_dict(),
            "strategy": self.strategy.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ProfileConfig":
        return cls(
            name=str(payload["name"]),
            exchange=ExchangeName(str(payload["exchange"])),
            mode=TradingMode(str(payload["mode"])),
            base_currency=str(payload.get("base_currency", "USD")),
            markets=[str(item) for item in payload.get("markets", [])],
            capital=CapitalSettings.from_dict(payload.get("capital", {})),
            risk=RiskSettings.from_dict(payload.get("risk", {})),
            schedule=ScheduleSettings.from_dict(payload.get("schedule", {})),
            strategy=StrategySettings.from_dict(payload.get("strategy", {})),
        )


def build_default_profile(name: str = "Kraken Pullback") -> ProfileConfig:
    return ProfileConfig(
        name=name,
        exchange=ExchangeName.KRAKEN,
        mode=TradingMode.PAPER,
        base_currency="USD",
        markets=["BTC/USD", "ETH/USD"],
        capital=CapitalSettings(),
        risk=RiskSettings(),
        schedule=ScheduleSettings(),
        strategy=StrategySettings(),
    )

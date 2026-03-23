from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional


@dataclass
class Candle:
    market: str
    unit_minutes: int
    start_time: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    turnover: float


@dataclass
class SignalDecision:
    market: str
    should_enter: bool
    evaluated_candle_start: Optional[datetime]
    reasons: List[str] = field(default_factory=list)


@dataclass
class ExitDecision:
    should_exit: bool
    reason: Optional[str] = None
    pnl_pct: Optional[float] = None
    stop_price: Optional[float] = None


@dataclass
class Position:
    market: str
    volume: float
    entry_price: float
    invested_krw: float
    opened_at: datetime
    stop_price: float
    take_profit_price: float
    breakeven_armed: bool = False
    order_id: Optional[str] = None
    entry_fee_krw: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "market": self.market,
            "volume": self.volume,
            "entry_price": self.entry_price,
            "invested_krw": self.invested_krw,
            "opened_at": self.opened_at.isoformat(),
            "stop_price": self.stop_price,
            "take_profit_price": self.take_profit_price,
            "breakeven_armed": self.breakeven_armed,
            "order_id": self.order_id,
            "entry_fee_krw": self.entry_fee_krw,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Position":
        return cls(
            market=str(payload["market"]),
            volume=float(payload["volume"]),
            entry_price=float(payload["entry_price"]),
            invested_krw=float(payload["invested_krw"]),
            opened_at=datetime.fromisoformat(str(payload["opened_at"])),
            stop_price=float(payload["stop_price"]),
            take_profit_price=float(payload["take_profit_price"]),
            breakeven_armed=bool(payload.get("breakeven_armed", False)),
            order_id=payload.get("order_id"),
            entry_fee_krw=float(payload.get("entry_fee_krw", 0.0)),
        )


@dataclass
class DailyState:
    trading_date: date
    trade_count: int = 0
    realized_pnl_krw: float = 0.0
    consecutive_stop_losses: int = 0
    stopped_for_day: bool = False
    cooldown_until: Optional[datetime] = None
    market_cooldowns: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trading_date": self.trading_date.isoformat(),
            "trade_count": self.trade_count,
            "realized_pnl_krw": self.realized_pnl_krw,
            "consecutive_stop_losses": self.consecutive_stop_losses,
            "stopped_for_day": self.stopped_for_day,
            "cooldown_until": self.cooldown_until.isoformat() if self.cooldown_until else None,
            "market_cooldowns": self.market_cooldowns,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "DailyState":
        cooldown_raw = payload.get("cooldown_until")
        return cls(
            trading_date=date.fromisoformat(str(payload["trading_date"])),
            trade_count=int(payload.get("trade_count", 0)),
            realized_pnl_krw=float(payload.get("realized_pnl_krw", 0.0)),
            consecutive_stop_losses=int(payload.get("consecutive_stop_losses", 0)),
            stopped_for_day=bool(payload.get("stopped_for_day", False)),
            cooldown_until=datetime.fromisoformat(cooldown_raw) if cooldown_raw else None,
            market_cooldowns={str(k): str(v) for k, v in payload.get("market_cooldowns", {}).items()},
        )


@dataclass
class BotState:
    paper_cash_krw: float
    daily: DailyState
    positions: List[Position] = field(default_factory=list)
    last_processed_5m: Dict[str, str] = field(default_factory=dict)
    last_daily_summary_date: Optional[str] = None
    last_heartbeat_at: Optional[str] = None
    history: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def position(self) -> Optional[Position]:
        return self.positions[0] if self.positions else None

    @position.setter
    def position(self, value: Optional[Position]) -> None:
        self.positions = [value] if value else []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "paper_cash_krw": self.paper_cash_krw,
            "daily": self.daily.to_dict(),
            "positions": [position.to_dict() for position in self.positions],
            "last_processed_5m": self.last_processed_5m,
            "last_daily_summary_date": self.last_daily_summary_date,
            "last_heartbeat_at": self.last_heartbeat_at,
            "history": self.history[-100:],
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "BotState":
        positions_payload = payload.get("positions")
        if positions_payload is None:
            legacy_position_payload = payload.get("position")
            positions_payload = [legacy_position_payload] if legacy_position_payload else []
        return cls(
            paper_cash_krw=float(payload.get("paper_cash_krw", 0.0)),
            daily=DailyState.from_dict(payload["daily"]),
            positions=[Position.from_dict(item) for item in positions_payload],
            last_processed_5m={str(k): str(v) for k, v in payload.get("last_processed_5m", {}).items()},
            last_daily_summary_date=payload.get("last_daily_summary_date"),
            last_heartbeat_at=payload.get("last_heartbeat_at"),
            history=list(payload.get("history", [])),
        )

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


@dataclass(frozen=True)
class Bar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class OpeningRange:
    session_date: date
    high: float
    low: float
    bar_time: datetime


@dataclass(frozen=True)
class FVGSetup:
    symbol: str
    session_date: date
    breakout_bar_time: datetime
    setup_bar_time: datetime
    detect_time: datetime
    or_high: float
    or_low: float
    fvg_low: float
    fvg_high: float
    entry_price: float
    stop_price: float
    target_price: float
    risk_per_share: float


@dataclass(frozen=True)
class DaySignalResult:
    symbol: str
    session_date: date
    opening_range: Optional[OpeningRange]
    setup: Optional[FVGSetup]
    skip_reason: Optional[str]


@dataclass(frozen=True)
class Trade:
    symbol: str
    session_date: date
    detect_time: datetime
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    stop_price: float
    target_price: float
    quantity: int
    pnl: float
    r_multiple: float
    exit_reason: str


@dataclass(frozen=True)
class DailyNote:
    session_date: date
    reason: str

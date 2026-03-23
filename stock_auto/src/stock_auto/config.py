from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import Any, Dict


def _parse_hhmm(value: str) -> time:
    hour_str, minute_str = value.split(":", 1)
    return time(hour=int(hour_str), minute=int(minute_str))


@dataclass(frozen=True)
class StrategyConfig:
    symbol: str = "SPY"
    session_timezone: str = "America/New_York"
    session_start: str = "09:30"
    session_end: str = "11:00"
    quote_exchange_code: str = "AMS"
    order_exchange_code: str = "AMEX"
    country_code: str = "840"
    market_code: str = "05"
    opening_range_minutes: int = 15
    signal_bar_minutes: int = 5
    breakout_lookahead_bars: int = 1
    min_fvg_size_abs: float = 0.05
    min_fvg_size_ratio: float = 0.0005
    risk_reward_ratio: float = 2.0
    account_size: float = 100000.0
    account_risk_pct: float = 0.0025
    max_position_notional_pct: float = 0.20
    min_stop_distance_pct: float = 0.0015
    max_stop_distance_pct: float = 0.012
    price_tick_size: float = 0.01
    stop_slippage_per_share: float = 0.01
    force_exit_slippage_per_share: float = 0.01

    @property
    def session_start_time(self) -> time:
        return _parse_hhmm(self.session_start)

    @property
    def session_end_time(self) -> time:
        return _parse_hhmm(self.session_end)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "StrategyConfig":
        return cls(**payload)

    @classmethod
    def from_file(cls, path: Path) -> "StrategyConfig":
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return cls.from_dict(payload)

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Optional
from zoneinfo import ZoneInfo

from stock_auto.config import StrategyConfig
from stock_auto.domain.models import FVGSetup


@dataclass(frozen=True)
class KISTradeState:
    symbol: str
    session_date: date
    session_timezone: str
    session_end: str
    price_tick_size: float
    quote_exchange_code: str
    order_exchange_code: str
    country_code: str
    market_code: str
    entry_price: float
    stop_price: float
    target_price: float
    requested_quantity: int
    filled_quantity: int = 0
    phase: str = "entry_prepared"
    entry_order_id: Optional[str] = None
    exit_order_id: Optional[str] = None
    entry_submitted_at: Optional[datetime] = None
    exit_submitted_at: Optional[datetime] = None
    exit_reason: Optional[str] = None
    last_status: Optional[str] = None
    last_message: Optional[str] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "symbol": self.symbol,
            "session_date": self.session_date.isoformat(),
            "session_timezone": self.session_timezone,
            "session_end": self.session_end,
            "price_tick_size": self.price_tick_size,
            "quote_exchange_code": self.quote_exchange_code,
            "order_exchange_code": self.order_exchange_code,
            "country_code": self.country_code,
            "market_code": self.market_code,
            "entry_price": self.entry_price,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "requested_quantity": self.requested_quantity,
            "filled_quantity": self.filled_quantity,
            "phase": self.phase,
            "entry_order_id": self.entry_order_id,
            "exit_order_id": self.exit_order_id,
            "entry_submitted_at": _serialize_datetime(self.entry_submitted_at),
            "exit_submitted_at": _serialize_datetime(self.exit_submitted_at),
            "exit_reason": self.exit_reason,
            "last_status": self.last_status,
            "last_message": self.last_message,
            "updated_at": _serialize_datetime(self.updated_at),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "KISTradeState":
        return cls(
            symbol=str(payload["symbol"]),
            session_date=date.fromisoformat(str(payload["session_date"])),
            session_timezone=str(payload["session_timezone"]),
            session_end=str(payload["session_end"]),
            price_tick_size=float(payload["price_tick_size"]),
            quote_exchange_code=str(payload["quote_exchange_code"]),
            order_exchange_code=str(payload["order_exchange_code"]),
            country_code=str(payload["country_code"]),
            market_code=str(payload["market_code"]),
            entry_price=float(payload["entry_price"]),
            stop_price=float(payload["stop_price"]),
            target_price=float(payload["target_price"]),
            requested_quantity=int(payload["requested_quantity"]),
            filled_quantity=int(payload.get("filled_quantity") or 0),
            phase=str(payload.get("phase") or "entry_prepared"),
            entry_order_id=_optional_str(payload.get("entry_order_id")),
            exit_order_id=_optional_str(payload.get("exit_order_id")),
            entry_submitted_at=_parse_datetime(payload.get("entry_submitted_at")),
            exit_submitted_at=_parse_datetime(payload.get("exit_submitted_at")),
            exit_reason=_optional_str(payload.get("exit_reason")),
            last_status=_optional_str(payload.get("last_status")),
            last_message=_optional_str(payload.get("last_message")),
            updated_at=_parse_datetime(payload.get("updated_at")),
        )


def build_kis_trade_state(
    *,
    config: StrategyConfig,
    setup: FVGSetup,
    quantity: int,
    quote_exchange_code: str,
    order_exchange_code: str,
    country_code: str,
    market_code: str,
    entry_order_response: Optional[Dict[str, object]] = None,
    phase: str = "entry_prepared",
    status: Optional[str] = None,
    message: Optional[str] = None,
    now: Optional[datetime] = None,
) -> KISTradeState:
    timestamp = now or datetime.now(ZoneInfo(config.session_timezone))
    return KISTradeState(
        symbol=setup.symbol,
        session_date=setup.session_date,
        session_timezone=config.session_timezone,
        session_end=config.session_end,
        price_tick_size=config.price_tick_size,
        quote_exchange_code=quote_exchange_code,
        order_exchange_code=order_exchange_code,
        country_code=country_code,
        market_code=market_code,
        entry_price=setup.entry_price,
        stop_price=setup.stop_price,
        target_price=setup.target_price,
        requested_quantity=quantity,
        phase=phase,
        entry_order_id=extract_kis_order_id(entry_order_response),
        entry_submitted_at=timestamp if phase == "entry_submitted" else None,
        last_status=status,
        last_message=message,
        updated_at=timestamp,
    )


def default_kis_state_path(base_dir: Path, *, symbol: str, session_date: date) -> Path:
    return base_dir / f"kis_{symbol.lower()}_{session_date.strftime('%Y%m%d')}.json"


def save_kis_trade_state(path: Path, state: KISTradeState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(state.to_dict(), handle, indent=2, sort_keys=True)


def load_kis_trade_state(path: Path) -> KISTradeState:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return KISTradeState.from_dict(payload)


def extract_kis_order_id(payload: Optional[Dict[str, object]]) -> Optional[str]:
    if not payload:
        return None
    for key in ("ODNO", "odno", "order_id", "id"):
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _optional_str(value: object) -> Optional[str]:
    if value in (None, ""):
        return None
    return str(value)


def _serialize_datetime(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat()


def _parse_datetime(value: object) -> Optional[datetime]:
    if value in (None, ""):
        return None
    return datetime.fromisoformat(str(value))

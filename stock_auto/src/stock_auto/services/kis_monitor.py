from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime, time
from typing import Dict, Iterable, Optional
from zoneinfo import ZoneInfo

from stock_auto.adapters.broker.kis_overseas import KISOverseasStockBrokerClient
from stock_auto.adapters.market_data.kis_overseas import KISOverseasStockDataClient
from stock_auto.services.kis_state import KISTradeState, extract_kis_order_id


FINAL_PHASES = {"closed", "cancelled", "entry_closed_without_fill"}


@dataclass(frozen=True)
class KISMonitorResult:
    status: str
    message: str
    state: KISTradeState
    quote: Optional[Dict[str, object]] = None
    order_payload: Optional[Dict[str, object]] = None
    order_response: Optional[Dict[str, object]] = None


def build_kis_exit_order_payload(
    *,
    symbol: str,
    order_exchange_code: str,
    quantity: int,
    limit_price: float,
) -> Dict[str, object]:
    return {
        "OVRS_EXCG_CD": order_exchange_code,
        "PDNO": symbol,
        "ORD_QTY": str(quantity),
        "OVRS_ORD_UNPR": f"{limit_price:.4f}",
        "ORD_DVSN": "00",
        "SIDE": "sell",
    }


class KISExitMonitor:
    def __init__(
        self,
        market_data_client: KISOverseasStockDataClient,
        broker_client: KISOverseasStockBrokerClient,
    ) -> None:
        self.market_data_client = market_data_client
        self.broker_client = broker_client

    def check_once(
        self,
        state: KISTradeState,
        *,
        now: Optional[datetime] = None,
        dry_run: bool = True,
    ) -> KISMonitorResult:
        session_tz = ZoneInfo(state.session_timezone)
        now_local = (now or datetime.now(session_tz)).astimezone(session_tz)
        updated_state = replace(state, updated_at=now_local)

        if updated_state.phase in FINAL_PHASES:
            return KISMonitorResult(
                status="already_final",
                message=f"state is already terminal: {updated_state.phase}",
                state=updated_state,
            )

        open_orders = self.broker_client.list_open_orders(order_exchange_code=state.order_exchange_code)
        symbol_orders = [row for row in open_orders if _matches_symbol(row, state.symbol)]
        owned_entry_order = _find_order_by_id(symbol_orders, state.entry_order_id)
        owned_exit_order = _find_order_by_id(symbol_orders, state.exit_order_id)
        foreign_symbol_orders = _find_foreign_orders(
            symbol_orders,
            owned_order_ids={state.entry_order_id, state.exit_order_id},
        )

        if foreign_symbol_orders:
            conflict_state = replace(
                updated_state,
                last_status="conflicting_symbol_orders",
                last_message="found same-symbol open orders not owned by this state file",
            )
            return KISMonitorResult(
                status="conflicting_symbol_orders",
                message="same-symbol open orders exist that are not owned by this bot state",
                state=conflict_state,
            )

        balance = self.broker_client.get_present_balance(
            country_code=state.country_code,
            market_code=state.market_code,
        )
        position = _find_position(balance.get("positions") or [], state.symbol)
        position_qty = _extract_position_quantity(position) if position else 0

        if position_qty > 0:
            updated_state = replace(
                updated_state,
                phase="position_open",
                filled_quantity=position_qty,
                last_status="position_open",
                last_message="position detected in account balance",
            )

        if updated_state.phase in ("entry_prepared", "entry_submitted") and position_qty < 1:
            return self._handle_entry_wait(
                state=updated_state,
                order_row=owned_entry_order,
                now_local=now_local,
                dry_run=dry_run,
            )

        if position_qty < 1 and owned_exit_order is not None:
            return self._handle_orphan_exit_order(
                state=updated_state,
                order_row=owned_exit_order,
                dry_run=dry_run,
            )

        if position_qty < 1:
            closed_state = replace(
                updated_state,
                phase="closed",
                last_status="closed",
                last_message="no position detected for symbol",
            )
            return KISMonitorResult(
                status="closed",
                message="position is already closed",
                state=closed_state,
            )

        if owned_entry_order is not None:
            return self._handle_open_entry_order(
                state=updated_state,
                order_row=owned_entry_order,
                dry_run=dry_run,
            )

        if owned_exit_order is not None:
            exit_order_id = extract_kis_order_id(owned_exit_order)
            waiting_state = replace(
                updated_state,
                phase="exit_submitted",
                exit_order_id=exit_order_id or updated_state.exit_order_id,
                last_status="exit_order_exists",
                last_message="exit order already exists for symbol",
            )
            return KISMonitorResult(
                status="exit_order_exists",
                message="exit order already exists for symbol",
                state=waiting_state,
            )

        quote = self.market_data_client.fetch_quote_snapshot(
            symbol=state.symbol,
            quote_exchange_code=state.quote_exchange_code,
        )
        last_price = _extract_float(quote, "last")
        best_bid = _extract_float(quote, "pbid1", "bid")
        exit_reason = self._resolve_exit_reason(state, now_local, last_price)
        if exit_reason is None:
            idle_state = replace(
                updated_state,
                last_status="no_exit_signal",
                last_message=f"position open, current price={last_price if last_price is not None else 'n/a'}",
            )
            return KISMonitorResult(
                status="no_exit_signal",
                message="no exit condition met",
                state=idle_state,
                quote=quote,
            )

        sell_quantity = position_qty or updated_state.filled_quantity or updated_state.requested_quantity
        limit_price = self._build_exit_limit_price(
            state=updated_state,
            exit_reason=exit_reason,
            last_price=last_price,
            best_bid=best_bid,
        )
        payload = build_kis_exit_order_payload(
            symbol=state.symbol,
            order_exchange_code=state.order_exchange_code,
            quantity=sell_quantity,
            limit_price=limit_price,
        )
        if dry_run:
            dry_state = replace(
                updated_state,
                last_status="exit_signal_dry_run",
                last_message=f"{exit_reason} detected but exit order not submitted",
                exit_reason=exit_reason,
            )
            return KISMonitorResult(
                status="exit_signal_dry_run",
                message=f"{exit_reason} detected",
                state=dry_state,
                quote=quote,
                order_payload=payload,
            )

        response = self.broker_client.place_limit_order(
            symbol=state.symbol,
            order_exchange_code=state.order_exchange_code,
            quantity=sell_quantity,
            limit_price=limit_price,
            side="sell",
        )
        exit_state = replace(
            updated_state,
            phase="exit_submitted",
            exit_order_id=extract_kis_order_id(response),
            exit_submitted_at=now_local,
            exit_reason=exit_reason,
            last_status="exit_submitted",
            last_message=f"{exit_reason} detected and exit order submitted",
        )
        return KISMonitorResult(
            status="exit_submitted",
            message=f"{exit_reason} detected and exit order submitted",
            state=exit_state,
            quote=quote,
            order_payload=payload,
            order_response=response,
        )

    def _handle_entry_wait(
        self,
        *,
        state: KISTradeState,
        order_row: Optional[Dict[str, object]],
        now_local: datetime,
        dry_run: bool,
    ) -> KISMonitorResult:
        if order_row is None:
            if state.entry_order_id is None and state.phase == "entry_prepared":
                idle_state = replace(
                    state,
                    last_status="entry_not_submitted",
                    last_message="state file has no submitted entry order id",
                )
                return KISMonitorResult(
                    status="entry_not_submitted",
                    message="state file does not represent a submitted entry order",
                    state=idle_state,
                )

            history = self._load_order_history(state)
            entry_history = _find_history_order(history, order_id=state.entry_order_id)
            if entry_history is None:
                pending_state = replace(
                    state,
                    last_status="execution_history_pending",
                    last_message="entry order is not open and execution history has not resolved yet",
                )
                return KISMonitorResult(
                    status="execution_history_pending",
                    message="entry order left the open-book but execution history is not resolved yet",
                    state=pending_state,
                )

            filled_qty = _extract_filled_quantity(entry_history)
            if filled_qty > 0:
                closed_state = replace(
                    state,
                    phase="closed",
                    filled_quantity=filled_qty,
                    last_status="closed_after_execution_history",
                    last_message="entry order was filled previously and no position remains",
                )
                return KISMonitorResult(
                    status="closed",
                    message="entry order filled previously and position is no longer open",
                    state=closed_state,
                )

            closed_state = replace(
                state,
                phase="entry_closed_without_fill",
                last_status="entry_closed_without_fill",
                last_message="entry order left the open-book without a fill",
            )
            return KISMonitorResult(
                status="entry_closed_without_fill",
                message="entry order left the open-book without a fill",
                state=closed_state,
            )

        session_end = _session_end_datetime(state)
        order_id = extract_kis_order_id(order_row) or state.entry_order_id
        remaining_qty = _extract_open_order_quantity(order_row) or state.requested_quantity
        waiting_state = replace(
            state,
            phase="entry_submitted",
            entry_order_id=order_id or state.entry_order_id,
            last_status="waiting_for_entry_fill",
            last_message="entry order is still open",
        )
        if now_local < session_end or order_id is None:
            return KISMonitorResult(
                status="waiting_for_entry_fill",
                message="entry order is still open",
                state=waiting_state,
            )

        if dry_run:
            would_cancel = replace(
                waiting_state,
                last_status="would_cancel_stale_entry",
                last_message="session ended and entry order would be cancelled",
            )
            return KISMonitorResult(
                status="would_cancel_stale_entry",
                message="session ended and entry order would be cancelled",
                state=would_cancel,
            )

        response = self.broker_client.cancel_order(
            symbol=state.symbol,
            order_exchange_code=state.order_exchange_code,
            original_order_number=order_id,
            quantity=remaining_qty,
        )
        cancelled_state = replace(
            waiting_state,
            phase="cancelled",
            last_status="entry_cancelled",
            last_message="session ended before fill, entry order cancelled",
        )
        return KISMonitorResult(
            status="entry_cancelled",
            message="session ended before fill, entry order cancelled",
            state=cancelled_state,
            order_response=response,
        )

    def _handle_orphan_exit_order(
        self,
        *,
        state: KISTradeState,
        order_row: Dict[str, object],
        dry_run: bool,
    ) -> KISMonitorResult:
        order_id = extract_kis_order_id(order_row) or state.exit_order_id
        remaining_qty = _extract_open_order_quantity(order_row) or max(state.filled_quantity, 1)
        holding_state = replace(
            state,
            phase="exit_submitted",
            exit_order_id=order_id or state.exit_order_id,
            last_status="orphan_exit_order_exists",
            last_message="position is flat but an owned exit order remains open",
        )
        if dry_run or order_id is None:
            return KISMonitorResult(
                status="orphan_exit_order_exists",
                message="position is flat but an owned exit order remains open",
                state=holding_state,
            )

        response = self.broker_client.cancel_order(
            symbol=state.symbol,
            order_exchange_code=state.order_exchange_code,
            original_order_number=order_id,
            quantity=remaining_qty,
        )
        cancelled_state = replace(
            holding_state,
            phase="closed",
            last_status="orphan_exit_order_cancelled",
            last_message="position is flat and the remaining exit order was cancelled",
        )
        return KISMonitorResult(
            status="orphan_exit_order_cancelled",
            message="position is flat and the remaining exit order was cancelled",
            state=cancelled_state,
            order_response=response,
        )

    def _handle_open_entry_order(
        self,
        *,
        state: KISTradeState,
        order_row: Dict[str, object],
        dry_run: bool,
    ) -> KISMonitorResult:
        order_id = extract_kis_order_id(order_row) or state.entry_order_id
        remaining_qty = _extract_open_order_quantity(order_row) or max(
            state.requested_quantity - state.filled_quantity,
            1,
        )
        if order_id is None:
            holding_state = replace(
                state,
                last_status="position_open_with_live_entry_order",
                last_message="position exists while entry order is still open, but order id is unavailable",
            )
            return KISMonitorResult(
                status="position_open_with_live_entry_order",
                message="position exists while entry order is still open",
                state=holding_state,
            )

        if dry_run:
            would_cancel = replace(
                state,
                last_status="would_cancel_remaining_entry",
                last_message="position detected and remaining entry order would be cancelled",
            )
            return KISMonitorResult(
                status="would_cancel_remaining_entry",
                message="position detected and remaining entry order would be cancelled",
                state=would_cancel,
            )

        response = self.broker_client.cancel_order(
            symbol=state.symbol,
            order_exchange_code=state.order_exchange_code,
            original_order_number=order_id,
            quantity=remaining_qty,
        )
        cancelled_state = replace(
            state,
            entry_order_id=order_id,
            last_status="remaining_entry_cancelled",
            last_message="position detected and remaining entry order cancelled",
        )
        return KISMonitorResult(
            status="remaining_entry_cancelled",
            message="position detected and remaining entry order cancelled",
            state=cancelled_state,
            order_response=response,
        )

    def _resolve_exit_reason(
        self,
        state: KISTradeState,
        now_local: datetime,
        last_price: Optional[float],
    ) -> Optional[str]:
        if now_local >= _session_end_datetime(state):
            return "session_exit"
        if last_price is None:
            return None
        if last_price <= state.stop_price:
            return "stop_hit"
        if last_price >= state.target_price:
            return "target_hit"
        return None

    def _build_exit_limit_price(
        self,
        *,
        state: KISTradeState,
        exit_reason: str,
        last_price: Optional[float],
        best_bid: Optional[float],
    ) -> float:
        raw_price = best_bid or last_price or (
            state.target_price if exit_reason == "target_hit" else state.stop_price
        )
        tick = state.price_tick_size if state.price_tick_size > 0 else 0.01
        return _round_down_to_tick(raw_price, tick)

    def _load_order_history(self, state: KISTradeState) -> list[Dict[str, object]]:
        return self.broker_client.inquire_order_history(
            order_start_date=state.session_date,
            order_end_date=state.session_date,
            symbol=state.symbol,
            order_exchange_code=state.order_exchange_code,
        )


def is_kis_state_terminal(state: KISTradeState) -> bool:
    return state.phase in FINAL_PHASES


def _session_end_datetime(state: KISTradeState) -> datetime:
    hour_str, minute_str = state.session_end.split(":", 1)
    session_end = time(hour=int(hour_str), minute=int(minute_str))
    return datetime.combine(state.session_date, session_end, tzinfo=ZoneInfo(state.session_timezone))


def _find_position(rows: Iterable[Dict[str, object]], symbol: str) -> Optional[Dict[str, object]]:
    symbol_upper = symbol.upper()
    for row in rows:
        if _matches_symbol(row, symbol_upper):
            return row
    return None


def _find_order_by_id(rows: Iterable[Dict[str, object]], order_id: Optional[str]) -> Optional[Dict[str, object]]:
    if not order_id:
        return None
    for row in rows:
        if extract_kis_order_id(row) == order_id:
            return row
    return None


def _find_foreign_orders(
    rows: Iterable[Dict[str, object]],
    *,
    owned_order_ids: set[Optional[str]],
) -> list[Dict[str, object]]:
    known_ids = {order_id for order_id in owned_order_ids if order_id}
    foreign: list[Dict[str, object]] = []
    for row in rows:
        order_id = extract_kis_order_id(row)
        if not order_id or order_id not in known_ids:
            foreign.append(row)
    return foreign


def _find_history_order(rows: Iterable[Dict[str, object]], order_id: Optional[str]) -> Optional[Dict[str, object]]:
    if not order_id:
        return None
    for row in rows:
        if extract_kis_order_id(row) == order_id:
            return row
    return None


def _matches_symbol(row: Dict[str, object], symbol: str) -> bool:
    symbol_upper = symbol.upper()
    for key in ("pdno", "ovrs_pdno", "item_cd", "symbol", "code"):
        value = str(row.get(key, "")).upper()
        if value == symbol_upper:
            return True
    return False


def _extract_position_quantity(row: Optional[Dict[str, object]]) -> int:
    if not row:
        return 0
    for key in ("cblc_qty13", "ovrs_cblc_qty", "qty", "hold_qty"):
        quantity = _extract_int(row.get(key))
        if quantity is not None:
            return quantity
    return 0


def _extract_open_order_quantity(row: Dict[str, object]) -> Optional[int]:
    for key in ("nccs_qty", "ord_qty", "qty", "ft_ord_qty"):
        quantity = _extract_int(row.get(key))
        if quantity is not None:
            return quantity
    return None


def _extract_filled_quantity(row: Dict[str, object]) -> int:
    for key in ("ft_ccld_qty", "ccld_qty", "filled_qty", "exec_qty"):
        quantity = _extract_int(row.get(key))
        if quantity is not None:
            return quantity
    return 0


def _extract_order_side(row: Dict[str, object]) -> Optional[str]:
    mappings = {
        "01": "sell",
        "02": "buy",
        "SELL": "sell",
        "BUY": "buy",
        "S": "sell",
        "B": "buy",
    }
    for key in ("sll_buy_dvsn_cd", "sll_buy_dvsn", "side", "SELN_BYOV_CLS"):
        value = str(row.get(key, "")).upper()
        if value in mappings:
            return mappings[value]
    return None


def _extract_float(payload: Dict[str, object], *keys: str) -> Optional[float]:
    for key in keys:
        value = payload.get(key)
        if value in (None, ""):
            continue
        try:
            return float(str(value))
        except ValueError:
            continue
    return None


def _extract_int(value: object) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value)))
    except ValueError:
        return None


def _round_down_to_tick(value: float, tick_size: float) -> float:
    steps = math.floor(value / tick_size)
    rounded = steps * tick_size
    return round(rounded, 4)

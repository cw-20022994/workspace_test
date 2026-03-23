from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from stock_auto.services.kis_monitor import KISMonitorResult
from stock_auto.services.kis_state import KISTradeState, extract_kis_order_id


RUN_ONCE_NOTIFIABLE_STATUSES = {
    "submitted_entry_only",
    "open_order_exists",
    "position_exists",
    "insufficient_buying_power",
    "position_too_small",
}

MONITOR_NOTIFIABLE_STATUSES = {
    "exit_submitted",
    "entry_cancelled",
    "remaining_entry_cancelled",
    "orphan_exit_order_cancelled",
    "closed",
    "conflicting_symbol_orders",
    "entry_closed_without_fill",
    "orphan_exit_order_exists",
}


@dataclass(frozen=True)
class KISTelegramNotifier:
    telegram_client: object
    broker_label: str = "한국투자증권"
    asset_class_label: str = "미국주식"

    def notify_run_once(self, *, result, state_path: Optional[Path], submitted: bool) -> bool:
        if result.status not in RUN_ONCE_NOTIFIABLE_STATUSES:
            return False

        if result.status == "submitted_entry_only":
            text = self._build_entry_submitted_message(
                symbol=result.setup.symbol if result.setup is not None else "UNKNOWN",
                quantity=result.quantity,
                entry_price=result.setup.entry_price if result.setup is not None else None,
                stop_price=result.setup.stop_price if result.setup is not None else None,
                target_price=result.setup.target_price if result.setup is not None else None,
                order_id=extract_kis_order_id(result.order_response),
                message=result.message,
                state_path=state_path,
            )
        else:
            symbol = result.setup.symbol if result.setup is not None else "SPY"
            text = self._build_generic_message(
                symbol=symbol,
                event="ENTRY BLOCKED",
                status=result.status,
                message=result.message,
                state_path=state_path,
            )
        return self._send(text)

    def notify_monitor_result(
        self,
        *,
        previous_state: KISTradeState,
        result: KISMonitorResult,
        state_path: Path,
    ) -> bool:
        if result.status not in MONITOR_NOTIFIABLE_STATUSES:
            return False
        if not self._has_meaningful_change(previous_state, result.state):
            return False

        if result.status == "exit_submitted":
            text = self._build_exit_submitted_message(result=result, state_path=state_path)
        elif result.status in {"entry_cancelled", "remaining_entry_cancelled", "orphan_exit_order_cancelled"}:
            text = self._build_generic_message(
                symbol=result.state.symbol,
                event="ORDER UPDATED",
                status=result.status,
                message=result.message,
                state_path=state_path,
            )
        elif result.status == "closed":
            text = self._build_closed_message(result=result, state_path=state_path)
        else:
            text = self._build_generic_message(
                symbol=result.state.symbol,
                event="ACTION REQUIRED",
                status=result.status,
                message=result.message,
                state_path=state_path,
            )
        return self._send(text)

    def notify_error(
        self,
        *,
        symbol: str,
        command: str,
        error: Exception,
        state_path: Optional[Path] = None,
    ) -> bool:
        text = self._build_generic_message(
            symbol=symbol,
            event="ERROR",
            status=command,
            message=str(error),
            state_path=state_path,
        )
        return self._send(text)

    def _has_meaningful_change(self, previous_state: KISTradeState, current_state: KISTradeState) -> bool:
        return any(
            [
                previous_state.phase != current_state.phase,
                previous_state.last_status != current_state.last_status,
                previous_state.entry_order_id != current_state.entry_order_id,
                previous_state.exit_order_id != current_state.exit_order_id,
                previous_state.exit_reason != current_state.exit_reason,
                previous_state.filled_quantity != current_state.filled_quantity,
            ]
        )

    def _build_entry_submitted_message(
        self,
        *,
        symbol: str,
        quantity: Optional[int],
        entry_price: Optional[float],
        stop_price: Optional[float],
        target_price: Optional[float],
        order_id: Optional[str],
        message: str,
        state_path: Optional[Path],
    ) -> str:
        lines = [
            self._header(symbol),
            "event: ENTRY SUBMITTED",
            f"qty: {quantity if quantity is not None else 'n/a'}",
            f"entry: {_fmt_price(entry_price)}",
            f"stop: {_fmt_price(stop_price)}",
            f"target: {_fmt_price(target_price)}",
            f"order_id: {order_id or 'n/a'}",
            f"message: {message}",
        ]
        if state_path is not None:
            lines.append(f"state_path: {state_path}")
        lines.append(f"utc: {datetime.now(timezone.utc).isoformat()}")
        return "\n".join(lines)

    def _build_exit_submitted_message(self, *, result: KISMonitorResult, state_path: Path) -> str:
        state = result.state
        last_price = None
        if result.quote is not None:
            for key in ("last", "last_price", "stck_prpr"):
                value = result.quote.get(key)
                if value not in (None, ""):
                    last_price = float(str(value))
                    break
        lines = [
            self._header(state.symbol),
            "event: EXIT SUBMITTED",
            f"reason: {state.exit_reason or 'n/a'}",
            f"qty: {state.filled_quantity or state.requested_quantity}",
            f"entry: {_fmt_price(state.entry_price)}",
            f"stop: {_fmt_price(state.stop_price)}",
            f"target: {_fmt_price(state.target_price)}",
            f"last: {_fmt_price(last_price)}",
            f"order_id: {extract_kis_order_id(result.order_response) or state.exit_order_id or 'n/a'}",
            f"message: {result.message}",
            f"state_path: {state_path}",
            f"utc: {datetime.now(timezone.utc).isoformat()}",
        ]
        return "\n".join(lines)

    def _build_closed_message(self, *, result: KISMonitorResult, state_path: Path) -> str:
        state = result.state
        lines = [
            self._header(state.symbol),
            "event: POSITION CLOSED",
            f"reason: {state.exit_reason or state.last_status or 'n/a'}",
            f"filled_qty: {state.filled_quantity}",
            f"entry: {_fmt_price(state.entry_price)}",
            f"stop: {_fmt_price(state.stop_price)}",
            f"target: {_fmt_price(state.target_price)}",
            f"message: {result.message}",
            f"state_path: {state_path}",
            f"utc: {datetime.now(timezone.utc).isoformat()}",
        ]
        return "\n".join(lines)

    def _build_generic_message(
        self,
        *,
        symbol: str,
        event: str,
        status: str,
        message: str,
        state_path: Optional[Path],
    ) -> str:
        lines = [
            self._header(symbol),
            f"event: {event}",
            f"status: {status}",
            f"message: {message}",
        ]
        if state_path is not None:
            lines.append(f"state_path: {state_path}")
        lines.append(f"utc: {datetime.now(timezone.utc).isoformat()}")
        return "\n".join(lines)

    def _header(self, symbol: str) -> str:
        return f"[{self.broker_label}] [{self.asset_class_label}] [{symbol}]"

    def _send(self, text: str) -> bool:
        self.telegram_client.send_message(text=text)
        return True


def _fmt_price(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"

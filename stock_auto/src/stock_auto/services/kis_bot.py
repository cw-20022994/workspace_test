from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, Optional
from zoneinfo import ZoneInfo

from stock_auto.adapters.broker.kis_overseas import KISOverseasStockBrokerClient
from stock_auto.adapters.market_data.kis_overseas import KISOverseasStockDataClient
from stock_auto.config import StrategyConfig
from stock_auto.domain.models import FVGSetup
from stock_auto.services.risk_engine import RiskEngine
from stock_auto.services.signal_engine import SignalEngine


@dataclass(frozen=True)
class KISRunOnceResult:
    status: str
    message: str
    order_payload: Optional[Dict[str, object]] = None
    order_response: Optional[Dict[str, object]] = None
    setup: Optional[FVGSetup] = None
    quantity: Optional[int] = None


def build_kis_entry_order_payload(
    *,
    symbol: str,
    order_exchange_code: str,
    quantity: int,
    entry_price: float,
) -> Dict[str, object]:
    return {
        "OVRS_EXCG_CD": order_exchange_code,
        "PDNO": symbol,
        "ORD_QTY": str(quantity),
        "OVRS_ORD_UNPR": f"{entry_price:.4f}",
        "ORD_DVSN": "00",
        "SIDE": "buy",
    }


class KISOverseasBot:
    def __init__(
        self,
        config: StrategyConfig,
        market_data_client: KISOverseasStockDataClient,
        broker_client: KISOverseasStockBrokerClient,
        *,
        signal_engine: Optional[SignalEngine] = None,
        risk_engine: Optional[RiskEngine] = None,
    ) -> None:
        self.config = config
        self.market_data_client = market_data_client
        self.broker_client = broker_client
        self.signal_engine = signal_engine or SignalEngine(config)
        self.risk_engine = risk_engine or RiskEngine(config)
        self.session_tz = ZoneInfo(config.session_timezone)

    def run_once(
        self,
        *,
        symbol: Optional[str] = None,
        quote_exchange_code: Optional[str] = None,
        order_exchange_code: Optional[str] = None,
        now: Optional[datetime] = None,
        dry_run: bool = True,
    ) -> KISRunOnceResult:
        target_symbol = symbol or self.config.symbol
        quote_ex = quote_exchange_code or self.config.quote_exchange_code
        order_ex = order_exchange_code or self.config.order_exchange_code
        now_local = (now or datetime.now(self.session_tz)).astimezone(self.session_tz)

        if now_local.weekday() >= 5:
            return KISRunOnceResult(
                status="market_closed_weekend",
                message="US market is closed on weekends",
            )

        if now_local.time() < self.config.session_start_time:
            return KISRunOnceResult(status="before_session", message="session has not started")

        bars = self.market_data_client.fetch_recent_minute_bars(
            symbol=target_symbol,
            quote_exchange_code=quote_ex,
            interval_minutes=1,
            max_records=180,
            include_previous_day=True,
            market_timezone=self.config.session_timezone,
        )
        if not bars:
            return KISRunOnceResult(status="no_data", message="no market data returned for session")

        signal_result = self.signal_engine.evaluate_day(target_symbol, bars)
        if signal_result.setup is None:
            return KISRunOnceResult(
                status="no_setup",
                message=signal_result.skip_reason or "no setup detected",
            )

        setup = signal_result.setup
        if now_local < setup.detect_time:
            return KISRunOnceResult(
                status="setup_not_active_yet",
                message=f"setup detected but becomes active at {setup.detect_time.isoformat()}",
                setup=setup,
            )

        open_orders = self.broker_client.list_open_orders(order_exchange_code=order_ex)
        if self._has_symbol_match(open_orders, target_symbol):
            return KISRunOnceResult(
                status="open_order_exists",
                message=f"open order already exists for {target_symbol}",
                setup=setup,
            )

        balance = self.broker_client.get_present_balance(
            country_code=self.config.country_code,
            market_code=self.config.market_code,
        )
        if self._has_symbol_match(balance["positions"], target_symbol):
            return KISRunOnceResult(
                status="position_exists",
                message=f"position already exists for {target_symbol}",
                setup=setup,
            )

        account_equity = self.broker_client.extract_total_assets(balance) or self.config.account_size
        position_plan = self.risk_engine.position_plan(setup, account_equity)
        if position_plan is None:
            return KISRunOnceResult(
                status="position_too_small",
                message="risk engine produced no valid position size",
                setup=setup,
            )

        buying_power = self.broker_client.inquire_buying_power(
            order_exchange_code=order_ex,
            symbol=target_symbol,
            limit_price=setup.entry_price,
        )
        max_qty = self._extract_max_orderable_qty(buying_power)
        quantity = min(position_plan.quantity, max_qty) if max_qty is not None else position_plan.quantity
        if quantity < 1:
            return KISRunOnceResult(
                status="insufficient_buying_power",
                message="KIS buying power does not allow any quantity",
                setup=setup,
            )

        payload = build_kis_entry_order_payload(
            symbol=target_symbol,
            order_exchange_code=order_ex,
            quantity=quantity,
            entry_price=setup.entry_price,
        )

        if dry_run:
            return KISRunOnceResult(
                status="dry_run",
                message=(
                    "entry order payload prepared. KIS has no native bracket order here, "
                    "so stop/target must be monitored separately."
                ),
                order_payload=payload,
                setup=setup,
                quantity=quantity,
            )

        response = self.broker_client.place_limit_order(
            symbol=target_symbol,
            order_exchange_code=order_ex,
            quantity=quantity,
            limit_price=setup.entry_price,
            side="buy",
        )
        return KISRunOnceResult(
            status="submitted_entry_only",
            message="entry order submitted. stop/target automation must be handled by a separate monitor.",
            order_payload=payload,
            order_response=response,
            setup=setup,
            quantity=quantity,
        )

    def _extract_max_orderable_qty(self, buying_power: Dict[str, object]) -> Optional[int]:
        for key in (
            "max_ord_psbl_qty",
            "ovrs_max_ord_psbl_qty",
            "ord_psbl_qty",
            "echm_af_ord_psbl_qty",
        ):
            value = buying_power.get(key)
            if value in (None, ""):
                continue
            try:
                return int(float(str(value)))
            except ValueError:
                continue
        return None

    def _has_symbol_match(self, rows, symbol: str) -> bool:
        symbol_upper = symbol.upper()
        for row in rows:
            for key in ("pdno", "ovrs_pdno", "item_cd", "symbol"):
                value = str(row.get(key, "")).upper()
                if value == symbol_upper:
                    return True
        return False

    def _build_client_order_id(self, session_date: date, symbol: str) -> str:
        return f"kis-orfvg-{symbol.lower()}-{session_date.strftime('%Y%m%d')}"

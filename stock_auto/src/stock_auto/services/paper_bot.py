from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, Optional
from zoneinfo import ZoneInfo

from stock_auto.adapters.broker.alpaca_paper import AlpacaPaperTradingClient
from stock_auto.adapters.market_data.alpaca_historical import AlpacaHistoricalBarsClient
from stock_auto.config import StrategyConfig
from stock_auto.domain.models import FVGSetup
from stock_auto.services.risk_engine import RiskEngine
from stock_auto.services.signal_engine import SignalEngine


@dataclass(frozen=True)
class PaperRunResult:
    status: str
    message: str
    order_payload: Optional[Dict[str, object]] = None
    order_response: Optional[Dict[str, object]] = None
    setup: Optional[FVGSetup] = None
    quantity: Optional[int] = None


def build_long_bracket_order_payload(
    *,
    symbol: str,
    quantity: int,
    entry_price: float,
    stop_price: float,
    take_profit_price: float,
    client_order_id: Optional[str] = None,
) -> Dict[str, object]:
    payload: Dict[str, object] = {
        "symbol": symbol,
        "qty": str(quantity),
        "side": "buy",
        "type": "limit",
        "time_in_force": "day",
        "limit_price": f"{entry_price:.2f}",
        "order_class": "bracket",
        "take_profit": {
            "limit_price": f"{take_profit_price:.2f}",
        },
        "stop_loss": {
            "stop_price": f"{stop_price:.2f}",
        },
    }
    if client_order_id:
        payload["client_order_id"] = client_order_id
    return payload


class PaperTradingBot:
    def __init__(
        self,
        config: StrategyConfig,
        market_data_client: AlpacaHistoricalBarsClient,
        broker_client: AlpacaPaperTradingClient,
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
        now: Optional[datetime] = None,
        feed: str = "iex",
        adjustment: str = "split",
        dry_run: bool = False,
    ) -> PaperRunResult:
        target_symbol = symbol or self.config.symbol
        now_local = (now or datetime.now(self.session_tz)).astimezone(self.session_tz)

        if now_local.time() < self.config.session_start_time:
            return PaperRunResult(status="before_session", message="session has not started")

        session_date = now_local.date()
        session_start = datetime.combine(session_date, self.config.session_start_time, tzinfo=self.session_tz)
        session_end = datetime.combine(session_date, self.config.session_end_time, tzinfo=self.session_tz)
        fetch_end = min(now_local, session_end)
        bars = self.market_data_client.fetch_stock_bars(
            symbol=target_symbol,
            start=session_start,
            end=fetch_end,
            timeframe="1Min",
            feed=feed,
            adjustment=adjustment,
        )
        if not bars:
            return PaperRunResult(status="no_data", message="no market data returned for session")

        signal_result = self.signal_engine.evaluate_day(target_symbol, bars)
        if signal_result.setup is None:
            return PaperRunResult(
                status="no_setup",
                message=signal_result.skip_reason or "no setup detected",
            )

        setup = signal_result.setup
        if now_local < setup.detect_time:
            return PaperRunResult(
                status="setup_not_active_yet",
                message=f"setup detected but becomes active at {setup.detect_time.isoformat()}",
                setup=setup,
            )

        if now_local >= session_end:
            return PaperRunResult(
                status="session_closed",
                message="session end reached before order placement",
                setup=setup,
            )

        open_orders = self.broker_client.list_orders(status="open", symbols=[target_symbol])
        if open_orders:
            return PaperRunResult(
                status="open_order_exists",
                message=f"open order already exists for {target_symbol}",
                setup=setup,
            )

        positions = self.broker_client.list_positions()
        for position in positions:
            if str(position.get("symbol", "")).upper() == target_symbol.upper():
                return PaperRunResult(
                    status="position_exists",
                    message=f"position already exists for {target_symbol}",
                    setup=setup,
                )

        account = self.broker_client.get_account()
        equity = float(account["equity"])
        position_plan = self.risk_engine.position_plan(setup, equity)
        if position_plan is None:
            return PaperRunResult(
                status="position_too_small",
                message="risk engine produced no valid position size",
                setup=setup,
            )

        client_order_id = self._build_client_order_id(session_date, target_symbol)
        payload = build_long_bracket_order_payload(
            symbol=target_symbol,
            quantity=position_plan.quantity,
            entry_price=setup.entry_price,
            stop_price=setup.stop_price,
            take_profit_price=setup.target_price,
            client_order_id=client_order_id,
        )

        if dry_run:
            return PaperRunResult(
                status="dry_run",
                message="order payload prepared but not submitted",
                order_payload=payload,
                setup=setup,
                quantity=position_plan.quantity,
            )

        response = self.broker_client.submit_order(payload)
        return PaperRunResult(
            status="submitted",
            message="paper bracket order submitted",
            order_payload=payload,
            order_response=response,
            setup=setup,
            quantity=position_plan.quantity,
        )

    def _build_client_order_id(self, session_date: date, symbol: str) -> str:
        return f"orfvg-{symbol.lower()}-{session_date.strftime('%Y%m%d')}"

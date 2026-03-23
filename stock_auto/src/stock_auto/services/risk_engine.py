from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from stock_auto.config import StrategyConfig
from stock_auto.domain.models import FVGSetup


@dataclass(frozen=True)
class PositionPlan:
    quantity: int
    risk_dollars: float
    position_notional: float


class RiskEngine:
    def __init__(self, config: StrategyConfig) -> None:
        self.config = config

    def position_plan(
        self,
        setup: FVGSetup,
        equity: float,
    ) -> Optional[PositionPlan]:
        max_risk_dollars = equity * self.config.account_risk_pct
        risk_per_share = setup.risk_per_share
        if risk_per_share <= 0:
            return None

        quantity_by_risk = math.floor(max_risk_dollars / risk_per_share)
        quantity_by_notional = math.floor(
            (equity * self.config.max_position_notional_pct) / setup.entry_price
        )
        quantity = min(quantity_by_risk, quantity_by_notional)

        if quantity < 1:
            return None

        return PositionPlan(
            quantity=quantity,
            risk_dollars=quantity * risk_per_share,
            position_notional=quantity * setup.entry_price,
        )

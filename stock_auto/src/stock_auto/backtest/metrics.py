from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from stock_auto.domain.models import DailyNote, Trade


@dataclass(frozen=True)
class BacktestReport:
    starting_equity: float
    ending_equity: float
    total_pnl: float
    return_pct: float
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    average_r: float
    expectancy: float
    gross_profit: float
    gross_loss: float
    profit_factor: float
    max_drawdown: float
    trades: List[Trade]
    daily_notes: List[DailyNote]


def build_report(
    trades: Sequence[Trade],
    daily_notes: Sequence[DailyNote],
    starting_equity: float,
) -> BacktestReport:
    equity = starting_equity
    peak_equity = starting_equity
    max_drawdown = 0.0
    gross_profit = 0.0
    gross_loss = 0.0
    wins = 0
    losses = 0
    total_r = 0.0

    for trade in trades:
        equity += trade.pnl
        peak_equity = max(peak_equity, equity)
        if peak_equity > 0:
            drawdown = (peak_equity - equity) / peak_equity
            max_drawdown = max(max_drawdown, drawdown)

        total_r += trade.r_multiple
        if trade.pnl >= 0:
            wins += 1
            gross_profit += trade.pnl
        else:
            losses += 1
            gross_loss += abs(trade.pnl)

    total_pnl = equity - starting_equity
    total_trades = len(trades)
    win_rate = (wins / total_trades) if total_trades else 0.0
    average_r = (total_r / total_trades) if total_trades else 0.0
    expectancy = (total_pnl / total_trades) if total_trades else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss else float("inf") if gross_profit else 0.0

    return BacktestReport(
        starting_equity=starting_equity,
        ending_equity=equity,
        total_pnl=total_pnl,
        return_pct=(total_pnl / starting_equity) if starting_equity else 0.0,
        total_trades=total_trades,
        wins=wins,
        losses=losses,
        win_rate=win_rate,
        average_r=average_r,
        expectancy=expectancy,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=profit_factor,
        max_drawdown=max_drawdown,
        trades=list(trades),
        daily_notes=list(daily_notes),
    )

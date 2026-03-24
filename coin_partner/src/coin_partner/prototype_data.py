from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OverviewMetric:
    label: str
    value: str
    detail: str


@dataclass(frozen=True)
class PositionRow:
    market: str
    strategy: str
    entry_price: str
    mark_price: str
    pnl: str
    hold_time: str


@dataclass(frozen=True)
class SignalRow:
    market: str
    timeframe: str
    status: str
    progress_text: str
    progress_percent: int


@dataclass(frozen=True)
class ActivityRow:
    time_text: str
    title: str
    detail: str


@dataclass(frozen=True)
class ExchangeRow:
    name: str
    note: str
    badge: str


@dataclass(frozen=True)
class StrategyField:
    label: str
    value: float
    minimum: float
    maximum: float
    decimals: int = 2
    suffix: str = ""


@dataclass(frozen=True)
class PrototypeSnapshot:
    title: str
    subtitle: str
    profile_name: str
    mode_badge: str
    metrics: list[OverviewMetric]
    positions: list[PositionRow]
    signals: list[SignalRow]
    activities: list[ActivityRow]
    exchanges: list[ExchangeRow]
    strategy_fields: list[StrategyField]
    risk_fields: list[StrategyField]
    market_pulse: list[float]


def build_prototype_snapshot() -> PrototypeSnapshot:
    return PrototypeSnapshot(
        title="Coin Partner Studio",
        subtitle=(
            "Desktop auto-trading workspace prototype with strategy controls, risk rails, "
            "exchange connection panels, and live-style operational views."
        ),
        profile_name="Momentum Pullback / Asia Session",
        mode_badge="Mock UI Preview",
        metrics=[
            OverviewMetric("Today PnL", "+184,200 KRW", "5 trades · 80% win rate"),
            OverviewMetric("Capital In Play", "150,000 KRW", "3 of 5 slots filled"),
            OverviewMetric("Signal Strength", "4 / 6 ready", "BTC and ETH nearing entry"),
            OverviewMetric("Risk Budget Left", "71%", "Daily stop at -60,000 KRW"),
        ],
        positions=[
            PositionRow("KRW-BTC", "Pullback", "128,420,000", "129,180,000", "+0.59%", "18m"),
            PositionRow("KRW-ETH", "Breakout", "4,180,000", "4,245,000", "+1.55%", "43m"),
            PositionRow("KRW-XRP", "RSI Snapback", "3,098", "3,072", "-0.84%", "09m"),
        ],
        signals=[
            SignalRow("KRW-BTC", "5m", "Recovering Above EMA20", "5 / 6 conditions", 84),
            SignalRow("KRW-ETH", "15m", "Volume Expansion", "4 / 6 conditions", 68),
            SignalRow("KRW-SOL", "5m", "Cooling After Spike", "3 / 6 conditions", 47),
            SignalRow("KRW-DOGE", "1h", "Trend Filter Failed", "1 / 6 conditions", 19),
        ],
        activities=[
            ActivityRow("09:42", "Entry Imported", "KRW-BTC pullback entry added to session profile."),
            ActivityRow("09:37", "Risk Guard Raised", "ETH position moved to breakeven protection."),
            ActivityRow("09:31", "Strategy Sync", "Asia session template loaded with 5m execution cycle."),
            ActivityRow("09:22", "Exchange Check", "Account connectivity panel returned healthy state."),
            ActivityRow("09:10", "Preview Session", "Paper trading preview toggled on for sales demo."),
        ],
        exchanges=[
            ExchangeRow("Bybit", "Recommended for global derivatives-style users", "Priority"),
            ExchangeRow("Kraken", "OAuth-friendly desktop workflow direction", "Candidate"),
            ExchangeRow("Custom Connector", "Per-client adapter for supported exchanges", "Made-to-order"),
        ],
        strategy_fields=[
            StrategyField("Entry Amount", 50000, 5000, 500000, 0, " KRW"),
            StrategyField("EMA Pullback Tolerance", 0.25, 0.05, 2.00, 2, " %"),
            StrategyField("Volume Ratio", 1.30, 1.00, 5.00, 2, " x"),
            StrategyField("RSI Min", 52, 30, 70, 0, ""),
            StrategyField("RSI Max", 68, 40, 90, 0, ""),
            StrategyField("Overheat Limit", 1.80, 0.50, 8.00, 2, " % / 10m"),
        ],
        risk_fields=[
            StrategyField("Stop Loss", 1.50, 0.30, 10.00, 2, " %"),
            StrategyField("Take Profit", 2.30, 0.50, 15.00, 2, " %"),
            StrategyField("Daily Loss Limit", 10000, 5000, 300000, 0, " KRW"),
            StrategyField("Max Open Positions", 5, 1, 20, 0, ""),
            StrategyField("Cooldown After Stop", 10, 0, 180, 0, " min"),
            StrategyField("Same Market Cooldown", 2, 0, 120, 0, " min"),
        ],
        market_pulse=[32, 36, 34, 39, 41, 47, 44, 52, 55, 61, 58, 64, 67, 73],
    )

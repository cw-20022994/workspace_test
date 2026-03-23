from __future__ import annotations

from typing import List, Optional


def ema(values: List[float], period: int) -> List[Optional[float]]:
    if period <= 0:
        raise ValueError("period must be positive")
    result: List[Optional[float]] = []
    multiplier = 2 / (period + 1)
    current: Optional[float] = None
    for value in values:
        if current is None:
            current = value
        else:
            current = ((value - current) * multiplier) + current
        result.append(current)
    return result


def rsi(values: List[float], period: int) -> List[Optional[float]]:
    if period <= 0:
        raise ValueError("period must be positive")
    if len(values) < 2:
        return [None for _ in values]

    gains = [0.0]
    losses = [0.0]
    for index in range(1, len(values)):
        delta = values[index] - values[index - 1]
        gains.append(max(delta, 0.0))
        losses.append(abs(min(delta, 0.0)))

    rsi_values: List[Optional[float]] = [None for _ in values]
    if len(values) <= period:
        return rsi_values

    avg_gain = sum(gains[1 : period + 1]) / period
    avg_loss = sum(losses[1 : period + 1]) / period
    rsi_values[period] = _calc_rsi(avg_gain, avg_loss)

    for index in range(period + 1, len(values)):
        avg_gain = ((avg_gain * (period - 1)) + gains[index]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[index]) / period
        rsi_values[index] = _calc_rsi(avg_gain, avg_loss)
    return rsi_values


def average(values: List[float]) -> float:
    if not values:
        raise ValueError("values cannot be empty")
    return sum(values) / len(values)


def _calc_rsi(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0 and avg_gain == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

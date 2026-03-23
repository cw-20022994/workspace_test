from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional

from stock_auto.domain.models import Bar


def floor_timestamp(timestamp: datetime, interval_minutes: int) -> datetime:
    floored_minute = (timestamp.minute // interval_minutes) * interval_minutes
    return timestamp.replace(minute=floored_minute, second=0, microsecond=0)


class BarBuilder:
    def resample(self, bars: Iterable[Bar], interval_minutes: int) -> List[Bar]:
        resampled: List[Bar] = []
        current_bucket: Optional[datetime] = None
        current_bar: Optional[Bar] = None

        for bar in sorted(bars, key=lambda item: item.timestamp):
            bucket = floor_timestamp(bar.timestamp, interval_minutes)
            if current_bucket != bucket:
                if current_bar is not None:
                    resampled.append(current_bar)
                current_bucket = bucket
                current_bar = Bar(
                    symbol=bar.symbol,
                    timestamp=bucket,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                )
                continue

            assert current_bar is not None
            current_bar = Bar(
                symbol=current_bar.symbol,
                timestamp=current_bar.timestamp,
                open=current_bar.open,
                high=max(current_bar.high, bar.high),
                low=min(current_bar.low, bar.low),
                close=bar.close,
                volume=current_bar.volume + bar.volume,
            )

        if current_bar is not None:
            resampled.append(current_bar)
        return resampled

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from stock_auto.domain.models import Bar


def write_bars_to_csv(
    path: Path,
    bars: Iterable[Bar],
    *,
    output_timezone: str = "America/New_York",
) -> None:
    tz = ZoneInfo(output_timezone)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "open", "high", "low", "close", "volume", "symbol"],
        )
        writer.writeheader()
        for bar in sorted(bars, key=lambda item: item.timestamp):
            writer.writerow(
                {
                    "timestamp": bar.timestamp.astimezone(tz).isoformat(),
                    "open": f"{bar.open:.4f}",
                    "high": f"{bar.high:.4f}",
                    "low": f"{bar.low:.4f}",
                    "close": f"{bar.close:.4f}",
                    "volume": f"{bar.volume:.0f}",
                    "symbol": bar.symbol,
                }
            )

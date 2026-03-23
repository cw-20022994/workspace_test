from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from coin_partner.models import BotState, DailyState


class StateStore:
    def __init__(self, path: Path, timezone: str, paper_starting_cash_krw: float) -> None:
        self.path = path
        self.tz = ZoneInfo(timezone)
        self.paper_starting_cash_krw = paper_starting_cash_krw

    def load(self) -> BotState:
        if not self.path.exists():
            return self._fresh_state()
        with self.path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        state = BotState.from_dict(payload)
        if "paper_cash_krw" not in payload:
            state.paper_cash_krw = self.paper_starting_cash_krw
        return state

    def save(self, state: BotState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(state.to_dict(), handle, ensure_ascii=True, indent=2)

    def ensure_trading_day(self, state: BotState, now: datetime) -> None:
        local_day = now.astimezone(self.tz).date()
        if state.daily.trading_date == local_day:
            return
        state.daily = DailyState(trading_date=local_day)

    def _fresh_state(self) -> BotState:
        current_day = datetime.now(self.tz).date()
        return BotState(
            paper_cash_krw=self.paper_starting_cash_krw,
            daily=DailyState(trading_date=current_day),
        )

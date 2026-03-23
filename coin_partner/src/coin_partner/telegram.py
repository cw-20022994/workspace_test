from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from html import escape
from typing import Callable, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from coin_partner.config import AppConfig, TelegramConfig
from coin_partner.models import BotState, Position


logger = logging.getLogger(__name__)


class TelegramError(RuntimeError):
    pass


@dataclass
class NotificationSettings:
    enabled: bool
    notify_entry: bool
    notify_exit: bool
    notify_daily_stop: bool
    notify_daily_summary: bool
    daily_summary_hour: int
    daily_summary_minute: int
    notify_heartbeat: bool
    heartbeat_interval_minutes: int
    notify_errors: bool
    error_cooldown_minutes: int


class TelegramNotifier:
    def __init__(
        self,
        config: TelegramConfig,
        mode: str,
        sender: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.config = config
        self.mode = mode
        self.settings = NotificationSettings(
            enabled=config.enabled and bool(config.bot_token) and bool(config.chat_id),
            notify_entry=config.notify_entry,
            notify_exit=config.notify_exit,
            notify_daily_stop=config.notify_daily_stop,
            notify_daily_summary=config.notify_daily_summary,
            daily_summary_hour=config.daily_summary_hour,
            daily_summary_minute=config.daily_summary_minute,
            notify_heartbeat=config.notify_heartbeat,
            heartbeat_interval_minutes=config.heartbeat_interval_minutes,
            notify_errors=config.notify_errors,
            error_cooldown_minutes=config.error_cooldown_minutes,
        )
        self._sender = sender or self._send_message
        self._last_error_sent_at: Optional[datetime] = None

    @classmethod
    def from_app_config(cls, config: AppConfig) -> "TelegramNotifier":
        return cls(config.telegram, config.bot.mode)

    def notify_entry(self, position: Position, state: BotState) -> bool:
        if not (self.settings.enabled and self.settings.notify_entry):
            return False
        lines = [
            "<b>[ENTRY]</b>",
            "mode: {0}".format(escape(self.mode)),
            "market: <code>{0}</code>".format(escape(position.market)),
            "entry: {0:,.0f} KRW".format(position.entry_price),
            "amount: {0:,.0f} KRW".format(position.invested_krw),
            "volume: {0:.8f}".format(position.volume),
            "stop: {0:,.0f} KRW".format(position.stop_price),
            "take: {0:,.0f} KRW".format(position.take_profit_price),
            "daily pnl: {0:,.0f} KRW".format(state.daily.realized_pnl_krw),
            "cash: {0:,.0f} KRW".format(state.paper_cash_krw) if self.mode == "paper" else "trade count: {0}".format(state.daily.trade_count),
        ]
        return self._deliver("\n".join(lines))

    def notify_exit(
        self,
        position: Position,
        exit_price: float,
        reason: str,
        pnl_krw: float,
        state: BotState,
    ) -> bool:
        if not (self.settings.enabled and self.settings.notify_exit):
            return False
        pnl_pct = 0.0
        if position.invested_krw > 0:
            pnl_pct = pnl_krw / position.invested_krw
        lines = [
            "<b>[EXIT]</b>",
            "mode: {0}".format(escape(self.mode)),
            "market: <code>{0}</code>".format(escape(position.market)),
            "reason: <code>{0}</code>".format(escape(reason)),
            "entry: {0:,.0f} KRW".format(position.entry_price),
            "exit: {0:,.0f} KRW".format(exit_price),
            "pnl: {0:+,.0f} KRW ({1:+.2f}%)".format(pnl_krw, pnl_pct * 100),
            "daily pnl: {0:+,.0f} KRW".format(state.daily.realized_pnl_krw),
            "trade count: {0}".format(state.daily.trade_count),
            "cash: {0:,.0f} KRW".format(state.paper_cash_krw) if self.mode == "paper" else "consecutive losses: {0}".format(state.daily.consecutive_stop_losses),
        ]
        return self._deliver("\n".join(lines))

    def notify_daily_stop(self, state: BotState) -> bool:
        if not (self.settings.enabled and self.settings.notify_daily_stop):
            return False
        lines = [
            "<b>[DAY STOP]</b>",
            "trading halted for today",
            "daily pnl: {0:+,.0f} KRW".format(state.daily.realized_pnl_krw),
            "trade count: {0}".format(state.daily.trade_count),
            "consecutive losses: {0}".format(state.daily.consecutive_stop_losses),
        ]
        return self._deliver("\n".join(lines))

    def notify_daily_summary(
        self,
        summary_date: str,
        state: BotState,
        wins: int,
        losses: int,
        best_trade_pnl_krw: float,
        worst_trade_pnl_krw: float,
    ) -> bool:
        if not (self.settings.enabled and self.settings.notify_daily_summary):
            return False
        lines = [
            "<b>[DAY SUMMARY]</b>",
            "date: <code>{0}</code>".format(escape(summary_date)),
            "mode: {0}".format(escape(self.mode)),
            "daily pnl: {0:+,.0f} KRW".format(state.daily.realized_pnl_krw),
            "trade count: {0}".format(state.daily.trade_count),
            "wins / losses: {0} / {1}".format(wins, losses),
            "best trade: {0:+,.0f} KRW".format(best_trade_pnl_krw),
            "worst trade: {0:+,.0f} KRW".format(worst_trade_pnl_krw),
            "cash: {0:,.0f} KRW".format(state.paper_cash_krw) if self.mode == "paper" else "stopped for day: {0}".format(state.daily.stopped_for_day),
            "open positions: {0}".format(len(state.positions)),
        ]
        return self._deliver("\n".join(lines))

    def notify_heartbeat(
        self,
        state: BotState,
        now: datetime,
        mark_prices: Optional[Dict[str, Optional[float]]] = None,
    ) -> bool:
        if not (self.settings.enabled and self.settings.notify_heartbeat):
            return False
        lines = [
            "<b>[HEARTBEAT]</b>",
            "mode: {0}".format(escape(self.mode)),
            "time: <code>{0}</code>".format(escape(now.isoformat(timespec="seconds"))),
            "daily pnl: {0:+,.0f} KRW".format(state.daily.realized_pnl_krw),
            "trade count: {0}".format(state.daily.trade_count),
            "cash: {0:,.0f} KRW".format(state.paper_cash_krw) if self.mode == "paper" else "stopped for day: {0}".format(state.daily.stopped_for_day),
        ]
        if not state.positions:
            lines.append("position: flat")
        else:
            lines.append("open positions: {0}".format(len(state.positions)))
            total_unrealized_krw = 0.0
            mark_prices = mark_prices or {}
            for position in state.positions:
                lines.append("position: <code>{0}</code>".format(escape(position.market)))
                lines.append("entry: {0:,.0f} KRW".format(position.entry_price))
                mark_price = mark_prices.get(position.market)
                if mark_price is None:
                    continue
                unrealized_krw = (position.volume * mark_price) - position.invested_krw
                total_unrealized_krw += unrealized_krw
                unrealized_pct = 0.0
                if position.invested_krw > 0:
                    unrealized_pct = unrealized_krw / position.invested_krw
                lines.append("mark: {0:,.0f} KRW".format(mark_price))
                lines.append("unrealized: {0:+,.0f} KRW ({1:+.2f}%)".format(unrealized_krw, unrealized_pct * 100))
            if len(state.positions) > 1:
                lines.append("total unrealized: {0:+,.0f} KRW".format(total_unrealized_krw))
        return self._deliver("\n".join(lines))

    def notify_error(self, message: str, now: Optional[datetime] = None) -> bool:
        if not (self.settings.enabled and self.settings.notify_errors):
            return False
        now = now or datetime.utcnow()
        if self._last_error_sent_at is not None:
            cooldown = timedelta(minutes=self.settings.error_cooldown_minutes)
            if now - self._last_error_sent_at < cooldown:
                return False
        self._last_error_sent_at = now
        lines = [
            "<b>[ERROR]</b>",
            escape(message),
        ]
        return self._deliver("\n".join(lines))

    def _deliver(self, text: str) -> bool:
        try:
            self._sender(text)
            return True
        except TelegramError:
            logger.exception("Telegram notification failed")
            return False

    def _send_message(self, text: str) -> None:
        if not self.config.bot_token or not self.config.chat_id:
            raise TelegramError("Telegram notifier is missing bot token or chat_id")

        url = "https://api.telegram.org/bot{0}/sendMessage".format(self.config.bot_token)
        payload: Dict[str, object] = {
            "chat_id": self.config.chat_id,
            "text": text,
            "parse_mode": self.config.parse_mode,
            "disable_notification": self.config.send_silently,
        }
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            url,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.config.request_timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise TelegramError("HTTP {0}: {1}".format(exc.code, detail)) from exc
        except URLError as exc:
            raise TelegramError("connection error: {0}".format(exc)) from exc

        if not payload.get("ok", False):
            raise TelegramError("telegram api error: {0}".format(payload))

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
            "<b>[진입]</b>",
            self._format_code_line("모드", self.mode, self._mode_description(self.mode)),
            self._format_code_line("마켓", position.market, "진입한 거래 마켓"),
            "진입가: {0:,.0f} KRW".format(position.entry_price),
            "진입금액: {0:,.0f} KRW".format(position.invested_krw),
            "수량: {0:.8f}".format(position.volume),
            "손절가: {0:,.0f} KRW".format(position.stop_price),
            "익절가: {0:,.0f} KRW".format(position.take_profit_price),
            "오늘 누적 손익: {0:+,.0f} KRW".format(state.daily.realized_pnl_krw),
            "남은 현금: {0:,.0f} KRW".format(state.paper_cash_krw)
            if self.mode == "paper"
            else "오늘 거래 횟수: {0}회".format(state.daily.trade_count),
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
            "<b>[청산]</b>",
            self._format_code_line("모드", self.mode, self._mode_description(self.mode)),
            self._format_code_line("마켓", position.market, "청산된 거래 마켓"),
            self._format_code_line("사유 코드", reason, self._reason_description(reason)),
            "진입가: {0:,.0f} KRW".format(position.entry_price),
            "청산가: {0:,.0f} KRW".format(exit_price),
            "실현손익: {0:+,.0f} KRW ({1:+.2f}%)".format(pnl_krw, pnl_pct * 100),
            "오늘 누적 손익: {0:+,.0f} KRW".format(state.daily.realized_pnl_krw),
            "오늘 거래 횟수: {0}회".format(state.daily.trade_count),
            "남은 현금: {0:,.0f} KRW".format(state.paper_cash_krw)
            if self.mode == "paper"
            else "연속 손실: {0}회".format(state.daily.consecutive_stop_losses),
        ]
        return self._deliver("\n".join(lines))

    def notify_daily_stop(self, state: BotState) -> bool:
        if not (self.settings.enabled and self.settings.notify_daily_stop):
            return False
        lines = [
            "<b>[일중 중지]</b>",
            "오늘 자동매매를 중지합니다.",
            "오늘 누적 손익: {0:+,.0f} KRW".format(state.daily.realized_pnl_krw),
            "오늘 거래 횟수: {0}회".format(state.daily.trade_count),
            "연속 손실: {0}회".format(state.daily.consecutive_stop_losses),
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
            "<b>[일일 요약]</b>",
            self._format_code_line("기준일", summary_date, "요약 대상 날짜"),
            self._format_code_line("모드", self.mode, self._mode_description(self.mode)),
            "오늘 누적 손익: {0:+,.0f} KRW".format(state.daily.realized_pnl_krw),
            "오늘 거래 횟수: {0}회".format(state.daily.trade_count),
            "승 / 패: {0} / {1}".format(wins, losses),
            "최대 이익 거래: {0:+,.0f} KRW".format(best_trade_pnl_krw),
            "최대 손실 거래: {0:+,.0f} KRW".format(worst_trade_pnl_krw),
            "남은 현금: {0:,.0f} KRW".format(state.paper_cash_krw)
            if self.mode == "paper"
            else "일중 중지 여부: {0}".format(self._bool_text(state.daily.stopped_for_day)),
            "보유 포지션 수: {0}개".format(len(state.positions)),
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
            "<b>[상태 점검]</b>",
            self._format_code_line("모드", self.mode, self._mode_description(self.mode)),
            self._format_code_line("기준 시각", now.isoformat(timespec="seconds"), "상태 점검 시각"),
            "오늘 누적 손익: {0:+,.0f} KRW".format(state.daily.realized_pnl_krw),
            "오늘 거래 횟수: {0}회".format(state.daily.trade_count),
            "남은 현금: {0:,.0f} KRW".format(state.paper_cash_krw)
            if self.mode == "paper"
            else "일중 중지 여부: {0}".format(self._bool_text(state.daily.stopped_for_day)),
        ]
        if not state.positions:
            lines.append("보유 포지션: 없음")
        else:
            lines.append("보유 포지션 수: {0}개".format(len(state.positions)))
            total_unrealized_krw = 0.0
            mark_prices = mark_prices or {}
            for position in state.positions:
                lines.append(self._format_code_line("보유 마켓", position.market, "현재 보유 중"))
                lines.append("진입가: {0:,.0f} KRW".format(position.entry_price))
                mark_price = mark_prices.get(position.market)
                if mark_price is None:
                    continue
                unrealized_krw = (position.volume * mark_price) - position.invested_krw
                total_unrealized_krw += unrealized_krw
                unrealized_pct = 0.0
                if position.invested_krw > 0:
                    unrealized_pct = unrealized_krw / position.invested_krw
                lines.append("현재가: {0:,.0f} KRW".format(mark_price))
                lines.append("평가손익: {0:+,.0f} KRW ({1:+.2f}%)".format(unrealized_krw, unrealized_pct * 100))
            if len(state.positions) > 1:
                lines.append("평가손익 합계: {0:+,.0f} KRW".format(total_unrealized_krw))
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
            "<b>[오류]</b>",
            "자동매매 실행 중 예외가 발생했습니다.",
            self._format_code_line("오류 내용", message, "원본 예외 메시지"),
        ]
        return self._deliver("\n".join(lines))

    def _format_code_line(self, label: str, value: str, description: str) -> str:
        return "{0}: <code>{1}</code> {2}".format(
            escape(label),
            escape(value),
            escape(description),
        )

    def _mode_description(self, mode: str) -> str:
        if mode == "paper":
            return "모의매매"
        if mode == "live":
            return "실거래"
        return "사용자 지정 모드"

    def _reason_description(self, reason: str) -> str:
        descriptions = {
            "stop_loss": "손절 기준 도달",
            "take_profit": "익절 기준 도달",
            "stalled_trade_exit": "초기 반응이 약해 조기 청산",
            "time_exit": "최대 보유 시간 도달",
            "unknown": "사유를 확인하지 못한 기본 코드",
        }
        return descriptions.get(reason, "청산 사유 코드")

    def _bool_text(self, value: bool) -> str:
        return "예" if value else "아니오"

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

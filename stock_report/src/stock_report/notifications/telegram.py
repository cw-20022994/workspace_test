"""Telegram notification helpers."""

from __future__ import annotations

import os
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

import requests


class TelegramNotifyError(RuntimeError):
    """Raised when Telegram delivery fails."""


class TelegramNotifier:
    """Minimal Telegram Bot API sender."""

    def __init__(
        self,
        *,
        bot_token: str,
        chat_id: str,
        session: Optional[requests.Session] = None,
        timeout_seconds: int = 20,
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> Optional["TelegramNotifier"]:
        bot_token = os.getenv("STOCK_REPORT_TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("STOCK_REPORT_TELEGRAM_CHAT_ID", "").strip()
        if not bot_token or not chat_id:
            return None
        return cls(bot_token=bot_token, chat_id=chat_id)

    def send_message(self, text: str) -> None:
        response = self.session.post(
            "https://api.telegram.org/bot{token}/sendMessage".format(
                token=self.bot_token
            ),
            data={
                "chat_id": self.chat_id,
                "text": text,
                "disable_web_page_preview": "true",
            },
            timeout=self.timeout_seconds,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise TelegramNotifyError("Telegram returned a non-JSON response.") from exc

        if response.status_code >= 400 or not bool(payload.get("ok")):
            raise TelegramNotifyError(
                "Telegram sendMessage failed: {status} {message}".format(
                    status=response.status_code,
                    message=payload.get("description", "unknown error"),
                )
            )


def build_daily_refresh_message(
    *,
    refresh_summary: Dict[str, Any],
    daily_summary: Optional[Dict[str, Any]] = None,
    calibration_report: Optional[Dict[str, Any]] = None,
) -> str:
    """Build a concise Telegram message for the daily refresh result."""

    steps = list(refresh_summary.get("steps") or [])
    failed_steps = [
        str(item.get("name"))
        for item in steps
        if str(item.get("status")) not in {"success", "skipped"}
    ]
    status_text = "성공" if not failed_steps else "실패"

    lines = [
        "stock_report daily-refresh",
        "날짜: {value}".format(value=_text(refresh_summary.get("run_date"))),
        "상태: {value}".format(value=status_text),
    ]

    symbols = list(refresh_summary.get("symbols") or [])
    if symbols:
        lines.append("심볼: {value}".format(value=", ".join(symbols)))

    if daily_summary:
        leaders = list(daily_summary.get("leaders") or [])
        if leaders:
            lines.append("")
            lines.append("상위 후보:")
            for item in leaders[:3]:
                lines.append(
                    "- {symbol} {score:.1f} {verdict}".format(
                        symbol=_text(item.get("symbol")),
                        score=float(item.get("total_score", 0.0)),
                        verdict=_verdict_label_ko(item.get("verdict")),
                    )
                )

    if calibration_report:
        lines.append("")
        lines.append(
            "보정: {value}".format(
                value="적용" if calibration_report.get("auto_applied") else "유지"
            )
        )
        reasons = list(calibration_report.get("reasons") or [])
        if reasons:
            lines.append("사유: {value}".format(value=reasons[0]))

    if failed_steps:
        lines.append("")
        lines.append("실패 단계: {value}".format(value=", ".join(failed_steps)))

    return "\n".join(lines)


def build_test_message() -> str:
    """Build a small test message for manual verification."""

    return "stock_report Telegram test\n상태: 연결 확인"


def _text(value: Any) -> str:
    if value in (None, ""):
        return "해당 없음"
    return str(value)


def _verdict_label_ko(verdict: Any) -> str:
    return {
        "review": "검토",
        "hold": "보류",
        "avoid": "회피",
    }.get(str(verdict), str(verdict))

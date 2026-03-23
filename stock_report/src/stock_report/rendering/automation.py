"""Automation summary rendering helpers."""

from __future__ import annotations

from typing import Any
from typing import Dict


def build_daily_refresh_guide_ko() -> Dict[str, str]:
    """Return Korean guide text for automation summary fields."""

    return {
        "단계상태": "성공은 정상 완료, 실패는 단계 오류, 건너뜀은 설정 미존재 등으로 실행하지 않은 상태입니다.",
        "산출물": "각 경로는 이번 자동 실행에서 갱신된 주요 JSON/리포트 파일 위치입니다.",
    }


def build_daily_refresh_readable_ko(summary: Dict[str, Any]) -> Dict[str, Any]:
    """Build a Korean-friendly view of the automation summary payload."""

    return {
        "실행일": _text(summary.get("run_date")),
        "생성시각_UTC": _text(summary.get("generated_at_utc")),
        "대상심볼": ", ".join(summary.get("symbols") or []) or "전체",
        "단계별결과": [_step_readable_ko(step) for step in summary.get("steps", [])],
        "주요산출물": {
            _output_label_ko(key): _text(value)
            for key, value in dict(summary.get("outputs") or {}).items()
        },
    }


def render_daily_refresh_markdown(summary: Dict[str, Any]) -> str:
    """Render a summary for the automated daily refresh chain."""

    lines = [
        "# 일일 자동 실행 요약 - {date}".format(date=_text(summary.get("run_date"))),
        "",
        "- 생성 시각(UTC): {value}".format(value=_text(summary.get("generated_at_utc"))),
        "- 대상 심볼: {value}".format(value=", ".join(summary.get("symbols") or []) or "전체"),
        "",
        "## 단계별 결과",
        "",
    ]
    for step in summary.get("steps", []):
        lines.append(
            "- {name}: {status} | {detail}".format(
                name=_step_label_ko(step.get("name")),
                status=_step_status_label_ko(step.get("status")),
                detail=_text(step.get("detail")),
            )
        )

    lines.extend(["", "## 주요 산출물", ""])
    for key, value in dict(summary.get("outputs") or {}).items():
        lines.append(
            "- {key}: {value}".format(
                key=_output_label_ko(key),
                value=_text(value),
            )
        )

    return "\n".join(lines)


def _step_readable_ko(step: Dict[str, Any]) -> Dict[str, str]:
    return {
        "단계": _step_label_ko(step.get("name")),
        "상태": _step_status_label_ko(step.get("status")),
        "세부": _text(step.get("detail")),
    }


def _step_label_ko(name: Any) -> str:
    return {
        "daily_batch": "일간 배치",
        "backtest_labels": "백테스트 라벨",
        "backtest_summary": "백테스트 집계",
        "calibration_report": "점수 보정 리포트",
        "calibration_compare": "보정 전후 비교",
        "telegram_notify": "텔레그램 알림",
    }.get(str(name), _text(name))


def _step_status_label_ko(status: Any) -> str:
    return {
        "success": "성공",
        "error": "실패",
        "skipped": "건너뜀",
    }.get(str(status), _text(status))


def _output_label_ko(name: Any) -> str:
    return {
        "daily_batch_dir": "일간배치폴더",
        "backtest_aggregate": "백테스트집계",
        "calibration_report": "보정보고서",
        "calibration_comparison": "보정비교",
        "telegram_notification": "텔레그램알림",
    }.get(str(name), _text(name))


def _text(value: Any) -> str:
    if value in (None, ""):
        return "해당 없음"
    return str(value)

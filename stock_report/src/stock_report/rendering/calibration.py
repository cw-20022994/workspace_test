"""Calibration report rendering helpers."""

from __future__ import annotations

from typing import Any
from typing import Dict

from stock_report.rendering.localization import verdict_label_ko


def render_calibration_markdown(report: Dict[str, Any]) -> str:
    """Render a scoring calibration report."""

    lines = [
        "# 점수 보정 리포트",
        "",
        "- 생성 시각(UTC): {value}".format(value=_text(report.get("generated_at_utc"))),
        "- 목표 평가 구간: {value}거래일".format(value=_text(report.get("target_horizon"))),
        "- 자동 적용 상태: {value}".format(
            value="적용" if report.get("auto_applied") else "유지"
        ),
        "",
        "## 근거 요약",
        "",
        "- 완료 관측치: {value}".format(
            value=_text(report.get("evidence", {}).get("completed_total"))
        ),
        "- 자동 보정 최소 기준: {value}".format(
            value=_text(report.get("evidence", {}).get("min_completed_required"))
        ),
        "- 판정별 완료 건수: {value}".format(
            value=_text(report.get("evidence", {}).get("verdict_groups"))
        ),
        "- 점수대별 완료 건수: {value}".format(
            value=_text(report.get("evidence", {}).get("score_bands"))
        ),
        "",
        "## 현재 프로필",
        "",
    ]
    lines.extend(_profile_lines(report.get("current_profile", {})))
    lines.extend(["", "## 제안 프로필", ""])
    lines.extend(_profile_lines(report.get("proposed_profile", {})))

    lines.extend(["", "## 변경 사항", ""])
    changes = list(report.get("changes") or [])
    if changes:
        for change in changes:
            lines.append(
                "- {field}: {before} -> {after}".format(
                    field=_text(change.get("field")),
                    before=_text(change.get("before")),
                    after=_text(change.get("after")),
                )
            )
    else:
        lines.append("- 변경 없음")

    if report.get("decisions"):
        lines.extend(["", "## 결정 메모", ""])
        for item in report.get("decisions", []):
            lines.append("- {value}".format(value=_text(item)))

    if report.get("reasons"):
        lines.extend(["", "## 유지 사유", ""])
        for item in report.get("reasons", []):
            lines.append("- {value}".format(value=_text(item)))

    return "\n".join(lines)


def render_calibration_comparison_markdown(payload: Dict[str, Any]) -> str:
    """Render before/after scoring comparison."""

    counts = dict(payload.get("counts") or {})
    lines = [
        "# 점수 보정 전후 비교",
        "",
        "- 자산 수: {value}".format(value=_text(counts.get("assets"))),
        "- 판정 변경 수: {value}".format(value=_text(counts.get("changed_verdicts"))),
        "- 점수 변경 수: {value}".format(value=_text(counts.get("changed_scores"))),
        "",
        "## 프로필 차이",
        "",
    ]

    changes = list(payload.get("profile_changes") or [])
    if changes:
        for change in changes:
            lines.append(
                "- {field}: {before} -> {after}".format(
                    field=_text(change.get("field")),
                    before=_text(change.get("before")),
                    after=_text(change.get("after")),
                )
            )
    else:
        lines.append("- 변경 없음")

    lines.extend(
        [
            "",
            "## 자산별 비교",
            "",
            "| 티커 | 기존 점수 | 신규 점수 | 점수 변화 | 기존 판정 | 신규 판정 | 판정 변경 |",
            "| --- | ---: | ---: | ---: | --- | --- | --- |",
        ]
    )
    for item in payload.get("results", []):
        lines.append(
            "| {symbol} | {before} | {after} | {delta} | {before_verdict} | {after_verdict} | {changed} |".format(
                symbol=_text(item.get("symbol")),
                before=_score(item.get("before", {}).get("total_score")),
                after=_score(item.get("after", {}).get("total_score")),
                delta=_signed_score(item.get("delta", {}).get("total_score")),
                before_verdict=verdict_label_ko(item.get("before", {}).get("verdict")),
                after_verdict=verdict_label_ko(item.get("after", {}).get("verdict")),
                changed="예" if item.get("delta", {}).get("verdict_changed") else "아니오",
            )
        )

    return "\n".join(lines)


def _profile_lines(profile: Dict[str, Any]) -> list[str]:
    weights = dict(profile.get("weights") or {})
    verdicts = dict(profile.get("verdict_thresholds") or {})
    confidence = dict(profile.get("confidence_thresholds") or {})
    return [
        "- 가중치: trend {trend:.2f}, fundamentals {fundamentals:.2f}, news {news:.2f}, risk {risk:.2f}".format(
            trend=float(weights.get("trend", 0.0)),
            fundamentals=float(weights.get("fundamentals", 0.0)),
            news=float(weights.get("news", 0.0)),
            risk=float(weights.get("risk", 0.0)),
        ),
        "- 판정 기준: review >= {review}, hold >= {hold}".format(
            review=_text(verdicts.get("review_min")),
            hold=_text(verdicts.get("hold_min")),
        ),
        "- 신뢰도 기준: high >= {high}, medium >= {medium}".format(
            high=_text(confidence.get("high_min")),
            medium=_text(confidence.get("medium_min")),
        ),
    ]


def _text(value: Any) -> str:
    if value in (None, ""):
        return "해당 없음"
    return str(value)


def _score(value: Any) -> str:
    try:
        if value in (None, ""):
            return "해당 없음"
        return "{value:.1f}".format(value=float(value))
    except (TypeError, ValueError):
        return "해당 없음"


def _signed_score(value: Any) -> str:
    try:
        if value in (None, ""):
            return "해당 없음"
        numeric = float(value)
        return "{value:+.1f}".format(value=numeric)
    except (TypeError, ValueError):
        return "해당 없음"

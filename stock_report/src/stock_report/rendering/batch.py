"""Daily batch summary rendering helpers."""

from __future__ import annotations

from typing import Any
from typing import Dict
from typing import List

from stock_report.rendering.localization import build_score_guide_ko
from stock_report.rendering.localization import confidence_label_ko
from stock_report.rendering.localization import display_name
from stock_report.rendering.localization import theme_label_ko
from stock_report.rendering.localization import translate_text_ko
from stock_report.rendering.localization import verdict_label_ko


def build_daily_summary_payload(
    *,
    batch_date: str,
    generated_at_utc: str,
    benchmark_symbol: str,
    history_range: str,
    news_days: int,
    results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build a machine-readable daily batch summary."""

    successes = [item for item in results if item.get("status") == "success"]
    failures = [item for item in results if item.get("status") == "error"]

    ordered_successes = sorted(
        successes,
        key=lambda item: float(item.get("total_score", 0.0)),
        reverse=True,
    )

    payload = {
        "batch_date": batch_date,
        "generated_at_utc": generated_at_utc,
        "benchmark_symbol": benchmark_symbol,
        "history_range": history_range,
        "news_days": news_days,
        "counts": {
            "requested": len(results),
            "success": len(successes),
            "failed": len(failures),
        },
        "leaders": ordered_successes[:5],
        "results": ordered_successes + failures,
    }
    payload["guide_ko"] = {
        "종합점수": build_score_guide_ko()["종합점수"],
        "판정": build_score_guide_ko()["판정"],
        "신뢰도": build_score_guide_ko()["신뢰도"],
        "summary.md 보는 순서": "먼저 리더보드를 보고, 관심 종목은 markdown 폴더의 개별 리포트를 열면 됩니다.",
    }
    payload["readable_ko"] = {
        "배치일자": batch_date,
        "생성시각_UTC": generated_at_utc,
        "비교기준": benchmark_symbol,
        "수집기간": "{value}일 뉴스, {range_value} 가격 이력".format(
            value=news_days,
            range_value=history_range,
        ),
        "건수": {
            "요청": len(results),
            "성공": len(successes),
            "실패": len(failures),
        },
        "상위후보": [
            {
                "표시명": display_name(item.get("name"), item.get("symbol")),
                "종합점수": "{value:.1f}/100".format(
                    value=float(item.get("total_score", 0.0))
                ),
                "판정": verdict_label_ko(item.get("verdict")),
                "신뢰도": _confidence_from_item(item),
                "테마": theme_label_ko(item.get("theme")),
            }
            for item in ordered_successes[:5]
        ],
        "실패항목": [
            {
                "표시명": display_name(item.get("name"), item.get("symbol")),
                "오류": translate_text_ko(item.get("error")),
            }
            for item in failures
        ],
    }
    return payload


def render_daily_summary_markdown(summary: Dict[str, Any]) -> str:
    """Render a daily watchlist summary in Markdown."""

    counts = summary.get("counts", {})
    leaders = summary.get("leaders", [])
    failures = [
        item for item in summary.get("results", []) if item.get("status") == "error"
    ]

    lines = [
        "# 일간 배치 요약 - {date}".format(date=summary.get("batch_date", "해당 없음")),
        "",
        "- 생성 시각(UTC): {value}".format(value=_text(summary.get("generated_at_utc"))),
        "- 비교 기준: {value}".format(value=_text(summary.get("benchmark_symbol"))),
        "- 가격 이력 범위: {value}".format(value=_text(summary.get("history_range"))),
        "- 뉴스 수집 기간: 최근 {value}일".format(value=_text(summary.get("news_days"))),
        "- 요청 자산 수: {value}".format(value=_text(counts.get("requested"))),
        "- 완료 수: {value}".format(value=_text(counts.get("success"))),
        "- 실패 수: {value}".format(value=_text(counts.get("failed"))),
        "",
        "## 보는 법",
        "",
        "- 종합 점수: 0~100점이며 높을수록 추가 검토 매력이 높다는 뜻입니다.",
        "- 판정: 검토 / 보류 / 회피로 요약합니다.",
        "- 신뢰도: 투자 성공 확률이 아니라 데이터 충분성과 신호 일관성을 뜻합니다.",
        "",
        "## 상위 후보",
        "",
    ]

    if leaders:
        lines.extend(
            [
                "| 회사/종목명 | 티커 | 종합 점수 | 판정 | 신뢰도 | 테마 |",
                "| --- | --- | ---: | --- | --- | --- |",
            ]
        )
        for item in leaders:
            lines.append(
                "| {name} | {symbol} | {score:.1f} | {verdict} | {confidence} | {theme} |".format(
                    name=item.get("name", "해당 없음"),
                    symbol=item.get("symbol", "해당 없음"),
                    score=float(item.get("total_score", 0.0)),
                    verdict=verdict_label_ko(item.get("verdict")),
                    confidence=_confidence_from_item(item),
                    theme=theme_label_ko(item.get("theme")),
                )
            )
    else:
        lines.append("성공적으로 생성된 자산이 없습니다.")

    lines.extend(["", "## 결과 상세", ""])
    for item in summary.get("results", []):
        name = display_name(item.get("name"), item.get("symbol"))
        if item.get("status") == "success":
            lines.append(
                "- {name}: {score:.1f}/100 | {verdict} | {confidence} | 대표 뉴스: {headline}".format(
                    name=name,
                    score=float(item.get("total_score", 0.0)),
                    verdict=verdict_label_ko(item.get("verdict")),
                    confidence=_confidence_from_item(item),
                    headline=_text(item.get("top_news_headline")),
                )
            )
        else:
            lines.append(
                "- {name}: 실패 | {message}".format(
                    name=name,
                    message=translate_text_ko(item.get("error")),
                )
            )

    if failures:
        lines.extend(["", "## 실패 항목", ""])
        for item in failures:
            lines.append(
                "- {name}: {message}".format(
                    name=display_name(item.get("name"), item.get("symbol")),
                    message=translate_text_ko(item.get("error")),
                )
            )

    return "\n".join(lines)


def _text(value: Any) -> str:
    if value in (None, ""):
        return "해당 없음"
    return str(value)


def _confidence_from_item(item: Dict[str, Any]) -> str:
    score = item.get("confidence_score")
    if score is not None:
        return confidence_label_ko(score)
    label = item.get("confidence_label")
    if label:
        return translate_text_ko(label)
    return "해당 없음"

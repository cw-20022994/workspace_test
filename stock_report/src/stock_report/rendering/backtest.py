"""Backtest snapshot rendering helpers."""

from __future__ import annotations

from typing import Any
from typing import Dict

from stock_report.rendering.localization import confidence_label_ko
from stock_report.rendering.localization import display_name
from stock_report.rendering.localization import verdict_label_ko


def render_backtest_markdown(snapshot: Dict[str, Any]) -> str:
    """Render a human-readable backtest snapshot."""

    lines = [
        "# 백테스트 스냅샷 - {date}".format(
            date=_text(snapshot.get("batch_date"))
        ),
        "",
        "- 생성 시각(UTC): {value}".format(
            value=_text(snapshot.get("generated_at_utc"))
        ),
        "- 기본 벤치마크: {value}".format(
            value=_text(snapshot.get("benchmark_symbol"))
        ),
        "- 사용 가격 이력 범위: {value}".format(
            value=_text(snapshot.get("history_range"))
        ),
        "- 평가 구간: {value}".format(
            value=", ".join(
                "{item}거래일".format(item=item)
                for item in snapshot.get("horizons", [])
            )
            or "해당 없음"
        ),
        "",
        "## 보는 법",
        "",
        "- asset_return: 기준일 종가 대비 해당 거래일 후 종가 수익률입니다.",
        "- benchmark_return: 같은 구간의 벤치마크 수익률입니다.",
        "- excess_return: 자산 수익률에서 벤치마크 수익률을 뺀 값입니다.",
        "- 판정 정합: 검토는 초과수익률 0% 이상, 회피는 0% 이하, 보류는 -5% 초과 5% 미만이면 정합으로 봅니다.",
    ]

    for horizon_key, verdicts in dict(snapshot.get("summary_by_horizon") or {}).items():
        lines.extend(
            [
                "",
                "## 판정별 요약 - {value}".format(value=_horizon_label(horizon_key)),
                "",
                "| 판정 | 완료/전체 | 평균 자산 수익률 | 평균 벤치마크 수익률 | 평균 초과수익률 | 정합률 |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for verdict, values in dict(verdicts or {}).items():
            lines.append(
                "| {verdict} | {completed}/{total} | {asset} | {benchmark} | {excess} | {alignment} |".format(
                    verdict=verdict_label_ko(verdict),
                    completed=_text(values.get("completed")),
                    total=_text(values.get("total")),
                    asset=_percent(values.get("avg_asset_return")),
                    benchmark=_percent(values.get("avg_benchmark_return")),
                    excess=_percent(values.get("avg_excess_return")),
                    alignment=_percent(values.get("alignment_rate")),
                )
            )

    lines.extend(["", "## 자산별 상세", ""])
    for item in snapshot.get("results", []):
        lines.append(
            "- {name}: {score} | {verdict} | 신뢰도 {confidence} | 기준일 {score_date}".format(
                name=display_name(item.get("name"), item.get("symbol")),
                score=_score(item.get("total_score")),
                verdict=verdict_label_ko(item.get("verdict")),
                confidence=confidence_label_ko(item.get("confidence_score")),
                score_date=_text(item.get("score_date")),
            )
        )
        for horizon_key, horizon in dict(item.get("horizons") or {}).items():
            asset_result = dict(horizon.get("asset") or {})
            evaluation = dict(horizon.get("evaluation") or {})
            lines.append(
                "  - {horizon}: {status} | 자산 {asset} | 벤치마크 {benchmark} | 초과 {excess} | 정합 {alignment}".format(
                    horizon=_horizon_label(horizon_key),
                    status=_status_label(asset_result.get("status")),
                    asset=_percent(asset_result.get("return_pct")),
                    benchmark=_percent(
                        dict(horizon.get("benchmark") or {}).get("return_pct")
                    ),
                    excess=_percent(horizon.get("excess_return")),
                    alignment=_alignment_label(evaluation.get("verdict_alignment")),
                )
            )

    if snapshot.get("history_errors"):
        lines.extend(["", "## 수집 실패", ""])
        for symbol, message in dict(snapshot.get("history_errors") or {}).items():
            lines.append("- {symbol}: {message}".format(symbol=symbol, message=_text(message)))

    return "\n".join(lines)


def render_backtest_aggregate_markdown(summary: Dict[str, Any]) -> str:
    """Render an aggregate backtest calibration summary."""

    lines = [
        "# 백테스트 집계 요약",
        "",
        "- 생성 시각(UTC): {value}".format(value=_text(summary.get("generated_at_utc"))),
        "- 집계 시작일: {value}".format(value=_text(summary.get("date_from") or "전체")),
        "- 집계 종료일: {value}".format(value=_text(summary.get("date_to") or "전체")),
        "- 포함 스냅샷 수: {value}".format(
            value=_text(summary.get("counts", {}).get("snapshots_included"))
        ),
        "- 전체 관측치 수: {value}".format(
            value=_text(summary.get("counts", {}).get("observations_total"))
        ),
        "",
        "## 보는 법",
        "",
        "- 판정별 집계는 `검토/보류/회피` 그룹의 평균 성과를 봅니다.",
        "- 점수대별 집계는 `0~49`, `50~59`, `60~69`, `70~79`, `80~100` 점수 구간별 평균 성과를 봅니다.",
        "- 정합률은 현재 규칙상 판정이 사후 수익률과 얼마나 맞았는지의 비율입니다.",
    ]

    for horizon_key, statuses in dict(summary.get("counts", {}).get("status_by_horizon") or {}).items():
        lines.extend(
            [
                "",
                "## 상태 요약 - {value}".format(value=_horizon_label(horizon_key)),
                "",
            ]
        )
        for status, count in dict(statuses or {}).items():
            lines.append(
                "- {status}: {count}".format(
                    status=_status_label(status),
                    count=_text(count),
                )
            )

    for horizon_key, groups in dict(summary.get("verdict_summary_by_horizon") or {}).items():
        lines.extend(
            [
                "",
                "## 판정별 집계 - {value}".format(value=_horizon_label(horizon_key)),
                "",
                "| 판정 | 완료/전체 | 평균 자산 수익률 | 평균 벤치마크 수익률 | 평균 초과수익률 | 정합률 |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for verdict, values in dict(groups or {}).items():
            lines.append(
                "| {verdict} | {completed}/{total} | {asset} | {benchmark} | {excess} | {alignment} |".format(
                    verdict=verdict_label_ko(verdict),
                    completed=_text(values.get("completed")),
                    total=_text(values.get("total")),
                    asset=_percent(values.get("avg_asset_return")),
                    benchmark=_percent(values.get("avg_benchmark_return")),
                    excess=_percent(values.get("avg_excess_return")),
                    alignment=_percent(values.get("alignment_rate")),
                )
            )

    for horizon_key, groups in dict(summary.get("score_band_summary_by_horizon") or {}).items():
        lines.extend(
            [
                "",
                "## 점수대별 집계 - {value}".format(value=_horizon_label(horizon_key)),
                "",
                "| 점수대 | 완료/전체 | 평균 자산 수익률 | 평균 벤치마크 수익률 | 평균 초과수익률 | 정합률 |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for band, values in dict(groups or {}).items():
            lines.append(
                "| {band} | {completed}/{total} | {asset} | {benchmark} | {excess} | {alignment} |".format(
                    band=_score_band_label(band),
                    completed=_text(values.get("completed")),
                    total=_text(values.get("total")),
                    asset=_percent(values.get("avg_asset_return")),
                    benchmark=_percent(values.get("avg_benchmark_return")),
                    excess=_percent(values.get("avg_excess_return")),
                    alignment=_percent(values.get("alignment_rate")),
                )
            )

    return "\n".join(lines)


def _text(value: Any) -> str:
    if value in (None, ""):
        return "해당 없음"
    return str(value)


def _percent(value: Any) -> str:
    try:
        if value in (None, ""):
            return "해당 없음"
        return "{value:.1f}%".format(value=float(value))
    except (TypeError, ValueError):
        return "해당 없음"


def _score(value: Any) -> str:
    try:
        if value in (None, ""):
            return "해당 없음"
        return "{value:.1f}/100".format(value=float(value))
    except (TypeError, ValueError):
        return "해당 없음"


def _horizon_label(value: str) -> str:
    return value.replace("d", "거래일")


def _status_label(status: Any) -> str:
    return {
        "complete": "완료",
        "pending": "미완료",
        "missing_anchor": "기준일 누락",
        "invalid_anchor_date": "기준일 오류",
        "fetch_error": "수집 실패",
        "no_history": "이력 없음",
        "invalid_entry_price": "기준 가격 오류",
    }.get(str(status), str(status))


def _alignment_label(status: Any) -> str:
    return {
        "aligned": "정합",
        "misaligned": "비정합",
        "pending": "보류",
    }.get(str(status), str(status))


def _score_band_label(band: Any) -> str:
    return {
        "0-49": "0~49점",
        "50-59": "50~59점",
        "60-69": "60~69점",
        "70-79": "70~79점",
        "80-100": "80~100점",
        "unknown": "미분류",
    }.get(str(band), str(band))

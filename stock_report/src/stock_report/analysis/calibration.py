"""Scoring calibration and comparison helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

from stock_report.analysis.scoring import score_asset
from stock_report.analysis.scoring_profile import normalize_scoring_profile
from stock_report.models import AnalysisInput
from stock_report.models import Watchlist


def build_scoring_calibration_report(
    *,
    aggregate_summary: Dict[str, Any],
    current_profile: Dict[str, Any],
    generated_at_utc: str,
) -> Dict[str, Any]:
    """Build a calibration report and a proposed scoring profile."""

    current = normalize_scoring_profile(current_profile)
    policy = dict(current.get("calibration_policy") or {})
    target_horizon = _pick_target_horizon(
        aggregate_summary=aggregate_summary,
        target_horizon=int(policy.get("target_horizon", 20)),
    )
    target_key = "{value}d".format(value=target_horizon)

    status_counts = dict(
        aggregate_summary.get("counts", {}).get("status_by_horizon", {}).get(target_key)
        or {}
    )
    verdict_summary = dict(
        aggregate_summary.get("verdict_summary_by_horizon", {}).get(target_key) or {}
    )
    score_band_summary = dict(
        aggregate_summary.get("score_band_summary_by_horizon", {}).get(target_key) or {}
    )

    completed_total = int(status_counts.get("complete", 0))
    min_completed = int(policy.get("min_completed_observations", 12))
    min_group = int(policy.get("min_group_observations", 4))
    threshold_step = float(policy.get("threshold_step", 5.0))
    max_weight_shift = float(policy.get("max_weight_shift", 0.05))

    evidence = {
        "target_horizon": target_horizon,
        "completed_total": completed_total,
        "min_completed_required": min_completed,
        "verdict_groups": {
            key: int(dict(value or {}).get("completed", 0))
            for key, value in verdict_summary.items()
        },
        "score_bands": {
            key: int(dict(value or {}).get("completed", 0))
            for key, value in score_band_summary.items()
        },
    }

    proposed = deepcopy(current)
    decisions = []
    reasons = []

    if completed_total < min_completed:
        reasons.append(
            "완료 관측치가 {current}건으로, 자동 보정 최소 기준 {required}건에 못 미칩니다.".format(
                current=completed_total,
                required=min_completed,
            )
        )
    else:
        review_completed = int(dict(verdict_summary.get("review") or {}).get("completed", 0))
        hold_completed = int(dict(verdict_summary.get("hold") or {}).get("completed", 0))
        if review_completed < min_group or hold_completed < min_group:
            reasons.append(
                "검토/보류 그룹의 완료 관측치가 각각 최소 {required}건 이상이어야 합니다.".format(
                    required=min_group
                )
            )
        else:
            decisions.extend(
                _maybe_adjust_thresholds(
                    proposed=proposed,
                    verdict_summary=verdict_summary,
                    score_band_summary=score_band_summary,
                    threshold_step=threshold_step,
                )
            )
            decisions.extend(
                _maybe_adjust_weights(
                    proposed=proposed,
                    score_band_summary=score_band_summary,
                    max_weight_shift=max_weight_shift,
                    min_group=min_group,
                )
            )
            if not decisions:
                reasons.append(
                    "현재 완료 관측치 기준으로는 임계값과 가중치를 바꿔야 할 충분한 왜곡이 확인되지 않았습니다."
                )

    proposed = normalize_scoring_profile(proposed)
    changes = _profile_diff(current, proposed)
    auto_applied = bool(changes) and not reasons

    payload = {
        "generated_at_utc": generated_at_utc,
        "aggregate_batch_count": aggregate_summary.get("counts", {}).get("snapshots_included"),
        "target_horizon": target_horizon,
        "current_profile": current,
        "proposed_profile": proposed,
        "changes": changes,
        "auto_applied": auto_applied,
        "evidence": evidence,
        "reasons": reasons,
        "decisions": decisions,
    }
    payload["readable_ko"] = _build_calibration_readable_ko(payload)
    return payload


def build_score_profile_comparison(
    *,
    watchlist: Watchlist,
    batch_profiles: List[Dict[str, Any]],
    current_profile: Dict[str, Any],
    proposed_profile: Dict[str, Any],
) -> Dict[str, Any]:
    """Compare current and proposed profiles against a batch of saved analyses."""

    current = normalize_scoring_profile(current_profile)
    proposed = normalize_scoring_profile(proposed_profile)
    rows = []

    for item in batch_profiles:
        symbol = str(item.get("symbol") or "").upper()
        asset = watchlist.get_asset(symbol)
        analysis = AnalysisInput.from_dict(dict(item.get("analysis") or {}))
        before = score_asset(
            asset,
            analysis,
            theme_notes=watchlist.theme_notes,
            scoring_profile=current,
        )
        after = score_asset(
            asset,
            analysis,
            theme_notes=watchlist.theme_notes,
            scoring_profile=proposed,
        )
        rows.append(
            {
                "symbol": symbol,
                "name": asset.name,
                "before": {
                    "total_score": before.total_score,
                    "verdict": before.verdict,
                    "confidence_score": before.confidence_score,
                },
                "after": {
                    "total_score": after.total_score,
                    "verdict": after.verdict,
                    "confidence_score": after.confidence_score,
                },
                "delta": {
                    "total_score": round(after.total_score - before.total_score, 2),
                    "verdict_changed": before.verdict != after.verdict,
                    "confidence_score": round(
                        after.confidence_score - before.confidence_score, 2
                    ),
                },
            }
        )

    changed_verdicts = sum(1 for item in rows if item["delta"]["verdict_changed"])
    payload = {
        "counts": {
            "assets": len(rows),
            "changed_verdicts": changed_verdicts,
            "changed_scores": sum(
                1 for item in rows if float(item["delta"]["total_score"]) != 0.0
            ),
        },
        "current_profile": current,
        "proposed_profile": proposed,
        "profile_changes": _profile_diff(current, proposed),
        "results": sorted(rows, key=lambda item: item["symbol"]),
    }
    payload["readable_ko"] = _build_comparison_readable_ko(payload)
    return payload


def _pick_target_horizon(
    *,
    aggregate_summary: Dict[str, Any],
    target_horizon: int,
) -> int:
    requested = "{value}d".format(value=target_horizon)
    status_by_horizon = dict(
        aggregate_summary.get("counts", {}).get("status_by_horizon") or {}
    )
    if requested in status_by_horizon:
        return target_horizon

    available = sorted(
        int(key[:-1])
        for key in status_by_horizon.keys()
        if str(key).endswith("d") and str(key)[:-1].isdigit()
    )
    if not available:
        return target_horizon
    return available[0]


def _maybe_adjust_thresholds(
    *,
    proposed: Dict[str, Any],
    verdict_summary: Dict[str, Any],
    score_band_summary: Dict[str, Any],
    threshold_step: float,
) -> List[str]:
    decisions = []
    thresholds = dict(proposed.get("verdict_thresholds") or {})

    review_avg = _safe_float(
        dict(verdict_summary.get("review") or {}).get("avg_excess_return")
    )
    hold_avg = _safe_float(
        dict(verdict_summary.get("hold") or {}).get("avg_excess_return")
    )
    hold_50s = _safe_float(
        dict(score_band_summary.get("50-59") or {}).get("avg_excess_return")
    )
    review_70s = _safe_float(
        dict(score_band_summary.get("70-79") or {}).get("avg_excess_return")
    )

    if review_avg is not None and hold_avg is not None and review_avg <= hold_avg:
        thresholds["review_min"] = min(thresholds["review_min"] + threshold_step, 90.0)
        decisions.append("검토 그룹 평균 초과수익률이 보류보다 낮아 review 기준을 상향했습니다.")

    if hold_50s is not None and hold_50s <= -3.0:
        thresholds["hold_min"] = min(thresholds["hold_min"] + threshold_step, thresholds["review_min"])
        decisions.append("50점대 평균 초과수익률이 약해 hold 기준을 상향했습니다.")
    elif hold_50s is not None and hold_50s >= 3.0 and review_70s is not None and review_70s >= hold_50s:
        thresholds["hold_min"] = max(thresholds["hold_min"] - threshold_step, 40.0)
        decisions.append("50점대 성과가 양호해 hold 기준을 완만하게 하향했습니다.")

    proposed["verdict_thresholds"] = thresholds
    return decisions


def _maybe_adjust_weights(
    *,
    proposed: Dict[str, Any],
    score_band_summary: Dict[str, Any],
    max_weight_shift: float,
    min_group: int,
) -> List[str]:
    decisions = []
    weights = dict(proposed.get("weights") or {})
    high_band = dict(score_band_summary.get("70-79") or {})
    low_band = dict(score_band_summary.get("50-59") or {})

    if int(high_band.get("completed", 0)) < min_group or int(low_band.get("completed", 0)) < min_group:
        return decisions

    high_excess = _safe_float(high_band.get("avg_excess_return"))
    low_excess = _safe_float(low_band.get("avg_excess_return"))
    if high_excess is None or low_excess is None:
        return decisions

    if high_excess + 1.0 < low_excess:
        shift = min(max_weight_shift, 0.03)
        weights["news"] = max(weights["news"] - shift, 0.05)
        weights["risk"] = min(weights["risk"] + shift, 0.40)
        decisions.append("상위 점수대 성과가 기대보다 약해 news 비중을 줄이고 risk 비중을 늘렸습니다.")

    proposed["weights"] = weights
    return decisions


def _profile_diff(current: Dict[str, Any], proposed: Dict[str, Any]) -> List[Dict[str, Any]]:
    changes = []
    for section in ("weights", "verdict_thresholds", "confidence_thresholds"):
        before = dict(current.get(section) or {})
        after = dict(proposed.get(section) or {})
        for key in sorted(set(before) | set(after)):
            if before.get(key) == after.get(key):
                continue
            changes.append(
                {
                    "field": "{section}.{key}".format(section=section, key=key),
                    "before": before.get(key),
                    "after": after.get(key),
                }
            )
    return changes


def _build_calibration_readable_ko(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "생성시각_UTC": payload.get("generated_at_utc"),
        "목표평가구간": "{value}거래일".format(value=payload.get("target_horizon")),
        "자동적용여부": "적용" if payload.get("auto_applied") else "유지",
        "근거요약": {
            "완료관측치": payload.get("evidence", {}).get("completed_total"),
            "최소필요관측치": payload.get("evidence", {}).get("min_completed_required"),
            "판정별완료건수": payload.get("evidence", {}).get("verdict_groups"),
            "점수대별완료건수": payload.get("evidence", {}).get("score_bands"),
        },
        "변경사항": payload.get("changes"),
        "사유": payload.get("reasons"),
        "결정메모": payload.get("decisions"),
    }


def _build_comparison_readable_ko(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "건수": payload.get("counts"),
        "프로필변경": payload.get("profile_changes"),
        "자산별차이": [
            {
                "티커": item.get("symbol"),
                "회사/종목명": item.get("name"),
                "기존점수": item.get("before", {}).get("total_score"),
                "신규점수": item.get("after", {}).get("total_score"),
                "점수변화": item.get("delta", {}).get("total_score"),
                "기존판정": item.get("before", {}).get("verdict"),
                "신규판정": item.get("after", {}).get("verdict"),
                "판정변경": item.get("delta", {}).get("verdict_changed"),
            }
            for item in payload.get("results", [])
        ],
    }


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None

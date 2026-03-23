"""Theme-aware deterministic scoring logic."""

from __future__ import annotations

from typing import Any
from typing import Dict
from typing import Iterable
from typing import List
from typing import Optional
from typing import Tuple

from stock_report.models import AnalysisInput
from stock_report.models import AssetDefinition
from stock_report.models import ScoreBreakdown
from stock_report.analysis.scoring_profile import load_scoring_profile
from stock_report.analysis.scoring_profile import normalize_scoring_profile

HBF_THEMES = {"hbf_memory_storage", "korea_hbm_hbf"}


def score_asset(
    asset: AssetDefinition,
    analysis: AnalysisInput,
    theme_notes: Optional[Dict[str, Dict[str, str]]] = None,
    scoring_profile: Optional[Dict[str, Any]] = None,
) -> ScoreBreakdown:
    """Score a stock or ETF using deterministic rules."""

    profile = normalize_scoring_profile(
        scoring_profile if scoring_profile is not None else load_scoring_profile()
    )
    weights = dict(profile.get("weights") or {})

    trend_score = _round_score(_score_trend(analysis.prices))
    fundamentals_score = _round_score(
        _score_fundamentals(asset, analysis.fundamentals, analysis.etf)
    )
    news_score = _round_score(_score_news(analysis.news))
    risk_score = _round_score(
        _score_risk(analysis.prices, analysis.fundamentals, analysis.freshness, analysis.risk_flags)
    )

    base_total = _round_score(
        trend_score * weights["trend"]
        + fundamentals_score * weights["fundamentals"]
        + news_score * weights["news"]
        + risk_score * weights["risk"]
    )

    overlay_score, overlay_rationale, confidence_delta = _score_theme_overlay(
        asset, analysis
    )
    if not overlay_rationale and theme_notes:
        overlay_rationale = (
            theme_notes.get(asset.theme, {}).get("overlay")
            or "No theme-specific overlay applied."
        )

    total_score = _round_score(_clamp(base_total + overlay_score))
    verdict = _verdict_from_score(total_score, profile)
    confidence_score, confidence_label, missing_inputs = _score_confidence(
        asset=asset,
        analysis=analysis,
        trend_score=trend_score,
        fundamentals_score=fundamentals_score,
        news_score=news_score,
        risk_score=risk_score,
        theme_confidence_delta=confidence_delta,
        scoring_profile=profile,
    )

    return ScoreBreakdown(
        trend_score=trend_score,
        fundamentals_score=fundamentals_score,
        news_score=news_score,
        risk_score=risk_score,
        base_total_score=base_total,
        theme_overlay=_round_score(overlay_score),
        overlay_rationale=overlay_rationale,
        total_score=total_score,
        verdict=verdict,
        confidence_score=_round_score(confidence_score),
        confidence_label=confidence_label,
        missing_inputs=missing_inputs,
    )


def _score_trend(prices: Dict[str, Any]) -> float:
    score = 50.0

    score += _weighted_metric(prices, "return_20d", weight=0.7, cap=12.0)
    score += _weighted_metric(prices, "return_60d", weight=0.5, cap=12.0)
    score += _weighted_metric(prices, "rs_20d", weight=0.8, cap=10.0)
    score += _weighted_metric(prices, "rs_60d", weight=0.5, cap=8.0)

    score += _ma_bonus(_get_float(prices, "price_vs_ma20"), positive=4.0, negative=-4.0)
    score += _ma_bonus(_get_float(prices, "price_vs_ma50"), positive=6.0, negative=-6.0)
    score += _ma_bonus(_get_float(prices, "price_vs_ma200"), positive=8.0, negative=-8.0)

    drawdown = _get_float(prices, "drawdown")
    if drawdown is not None and drawdown < 0:
        score -= min(abs(drawdown) * 0.40, 14.0)

    volatility = _get_float(prices, "volatility")
    if volatility is not None:
        score -= min(max(volatility - 25.0, 0.0) * 0.50, 12.0)

    return _clamp(score)


def _score_fundamentals(
    asset: AssetDefinition,
    fundamentals: Dict[str, Any],
    etf_metrics: Dict[str, Any],
) -> float:
    score = 50.0

    score += _weighted_metric(fundamentals, "revenue_growth", weight=0.30, cap=10.0)
    score += _weighted_metric(fundamentals, "earnings_growth", weight=0.25, cap=10.0)

    gross_margin = _get_float(fundamentals, "gross_margin")
    if gross_margin is not None:
        score += _bounded((gross_margin - 40.0) * 0.50, 8.0)

    operating_margin = _get_float(fundamentals, "operating_margin")
    if operating_margin is not None:
        score += _bounded((operating_margin - 15.0) * 0.40, 8.0)

    forward_pe = _get_float(fundamentals, "forward_pe")
    if forward_pe is not None and forward_pe > 35.0:
        score -= min((forward_pe - 35.0) * 0.35, 10.0)

    ev_to_sales = _get_float(fundamentals, "ev_to_sales")
    if ev_to_sales is not None and ev_to_sales > 10.0:
        score -= min((ev_to_sales - 10.0) * 0.80, 8.0)

    net_debt = _get_float(fundamentals, "net_debt_to_ebitda")
    if net_debt is not None and net_debt > 2.0:
        score -= min((net_debt - 2.0) * 4.0, 12.0)

    if asset.asset_type == "etf":
        expense_ratio = _first_float(etf_metrics, fundamentals, "expense_ratio")
        if expense_ratio is not None:
            score += _bounded((0.30 - expense_ratio) * 30.0, 6.0)

    return _clamp(score)


def _score_news(news_items: Iterable[Any]) -> float:
    score = 50.0
    impact_weights = {
        "positive": 7.0,
        "neutral": 0.0,
        "mixed": -2.0,
        "negative": -7.0,
    }

    for item in list(news_items)[:5]:
        impact = impact_weights.get(item.impact.lower(), 0.0)
        materiality = max(0.0, min(item.materiality, 1.0))
        delta = impact * materiality

        tags = set(item.tags)
        if tags.intersection({"earnings", "guidance", "product_launch", "standardization"}):
            delta += 1.5 * materiality
        if "regulatory" in tags and item.impact.lower() == "negative":
            delta -= 1.0 * materiality
        if "supply_chain" in tags and item.impact.lower() == "negative":
            delta -= 1.0 * materiality

        score += delta

    return _clamp(score)


def _score_risk(
    prices: Dict[str, Any],
    fundamentals: Dict[str, Any],
    freshness: Dict[str, Any],
    risk_flags: List[str],
) -> float:
    score = 75.0

    volatility = _get_float(prices, "volatility")
    if volatility is not None:
        score -= min(max(volatility - 20.0, 0.0) * 0.60, 20.0)

    drawdown = _get_float(prices, "drawdown")
    if drawdown is not None and drawdown < 0:
        score -= min(abs(drawdown) * 0.50, 20.0)

    forward_pe = _get_float(fundamentals, "forward_pe")
    if forward_pe is not None and forward_pe > 40.0:
        score -= min((forward_pe - 40.0) * 0.40, 12.0)

    event_concentration = _get_float(fundamentals, "event_concentration")
    if event_concentration is not None:
        score -= min(event_concentration * 6.0, 12.0)

    score -= min(len(risk_flags) * 4.0, 16.0)

    score -= _freshness_penalty(_get_float(freshness, "price_data_age_days"), start_days=2, step=2.0, cap=8.0)
    score -= _freshness_penalty(_get_float(freshness, "fundamentals_data_age_days"), start_days=90, step=4.0, cap=10.0)
    score -= _freshness_penalty(_get_float(freshness, "news_data_age_days"), start_days=2, step=2.0, cap=6.0)

    return _clamp(score)


def _score_theme_overlay(
    asset: AssetDefinition, analysis: AnalysisInput
) -> Tuple[float, str, float]:
    if asset.theme not in HBF_THEMES:
        return 0.0, "", 0.0

    signals = analysis.theme_signals
    if not signals:
        return 0.0, "Theme tracked, but no HBF-specific signals were provided.", -8.0

    overlay = 0.0
    confidence_delta = 0.0
    positives = []
    negatives = []

    if _as_bool(signals.get("standardization_progress")):
        overlay += 3.0
        positives.append("standardization progress")

    ecosystem_partners = int(_get_float(signals, "ecosystem_partners") or 0)
    if ecosystem_partners > 0:
        overlay += min(float(ecosystem_partners), 3.0)
        positives.append("{count} ecosystem partner(s)".format(count=ecosystem_partners))

    ai_inference_mentions = int(_get_float(signals, "ai_inference_mentions") or 0)
    if ai_inference_mentions > 0:
        overlay += min(float(ai_inference_mentions), 2.0)
        positives.append("AI inference references")

    if _as_bool(signals.get("commercial_sampling")):
        overlay += 2.0
        positives.append("commercial sampling")

    if _as_bool(signals.get("shipment_evidence")):
        overlay += 3.0
        positives.append("shipment evidence")

    concept_only_news_count = int(_get_float(signals, "concept_only_news_count") or 0)
    if concept_only_news_count > 0:
        penalty = min(float(concept_only_news_count) * 2.0, 4.0)
        overlay -= penalty
        negatives.append("concept-heavy coverage")

    if _as_bool(signals.get("single_source_hype")):
        overlay -= 3.0
        confidence_delta -= 8.0
        negatives.append("single-source narrative risk")

    if not _as_bool(signals.get("commercial_sampling")) and not _as_bool(
        signals.get("shipment_evidence")
    ):
        confidence_delta -= 5.0
        negatives.append("commercial proof still limited")

    overlay = _bounded(overlay, 10.0)

    summary_parts = []
    if positives:
        summary_parts.append("Positive: " + ", ".join(positives))
    if negatives:
        summary_parts.append("Caution: " + ", ".join(negatives))
    if not summary_parts:
        summary_parts.append("HBF theme tracked with neutral evidence.")

    return overlay, ". ".join(summary_parts), confidence_delta


def _score_confidence(
    asset: AssetDefinition,
    analysis: AnalysisInput,
    trend_score: float,
    fundamentals_score: float,
    news_score: float,
    risk_score: float,
    theme_confidence_delta: float,
    scoring_profile: Dict[str, Any],
) -> Tuple[float, str, List[str]]:
    required_inputs = [
        ("prices.return_20d", _get_float(analysis.prices, "return_20d")),
        ("prices.return_60d", _get_float(analysis.prices, "return_60d")),
        ("prices.rs_20d", _get_float(analysis.prices, "rs_20d")),
        ("prices.price_vs_ma50", _get_float(analysis.prices, "price_vs_ma50")),
        ("prices.drawdown", _get_float(analysis.prices, "drawdown")),
        ("prices.volatility", _get_float(analysis.prices, "volatility")),
    ]

    if asset.asset_type == "etf":
        required_inputs.extend(
            [
                (
                    "etf.expense_ratio",
                    _first_float(analysis.etf, analysis.fundamentals, "expense_ratio"),
                ),
                ("etf.holdings_count", _get_float(analysis.etf, "holdings_count")),
                ("etf.top_10_weight", _get_float(analysis.etf, "top_10_weight")),
            ]
        )
    else:
        required_inputs.extend(
            [
                (
                    "fundamentals.revenue_growth",
                    _get_float(analysis.fundamentals, "revenue_growth"),
                ),
                (
                    "fundamentals.earnings_growth",
                    _get_float(analysis.fundamentals, "earnings_growth"),
                ),
            ]
        )

    missing_inputs = [name for name, value in required_inputs if value is None]
    score = 90.0 - (len(missing_inputs) * 5.0)

    if len(analysis.news) == 0:
        score -= 8.0
    elif len(analysis.news) < 3:
        score -= 4.0

    if trend_score >= 65.0 and news_score <= 40.0:
        score -= 6.0
    if fundamentals_score >= 65.0 and risk_score <= 40.0:
        score -= 6.0

    score -= _freshness_penalty(_get_float(analysis.freshness, "price_data_age_days"), start_days=2, step=2.0, cap=8.0)
    score -= _freshness_penalty(_get_float(analysis.freshness, "fundamentals_data_age_days"), start_days=90, step=4.0, cap=10.0)
    score -= _freshness_penalty(_get_float(analysis.freshness, "news_data_age_days"), start_days=2, step=2.0, cap=6.0)
    score += theme_confidence_delta
    score = _clamp(score)

    confidence_thresholds = dict(scoring_profile.get("confidence_thresholds") or {})
    if score >= float(confidence_thresholds.get("high_min", 80.0)):
        band = "high"
    elif score >= float(confidence_thresholds.get("medium_min", 60.0)):
        band = "medium"
    else:
        band = "low"

    label = "{band} ({score}/100)".format(band=band, score=int(round(score)))
    return score, label, missing_inputs


def _freshness_penalty(
    age_days: Optional[float], start_days: float, step: float, cap: float
) -> float:
    if age_days is None or age_days <= start_days:
        return 0.0
    return min((age_days - start_days) * step, cap)


def _ma_bonus(value: Optional[float], positive: float, negative: float) -> float:
    if value is None:
        return 0.0
    return positive if value >= 1.0 else negative


def _weighted_metric(
    payload: Dict[str, Any], key: str, weight: float, cap: float
) -> float:
    value = _get_float(payload, key)
    if value is None:
        return 0.0
    return _bounded(value * weight, cap)


def _first_float(*payloads_and_key: Any) -> Optional[float]:
    *payloads, key = payloads_and_key
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        value = _get_float(payload, key)
        if value is not None:
            return value
    return None


def _get_float(payload: Dict[str, Any], key: str) -> Optional[float]:
    if not isinstance(payload, dict) or key not in payload:
        return None
    value = payload.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _bounded(value: float, cap: float) -> float:
    return max(-cap, min(cap, value))


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def _round_score(value: float) -> float:
    return round(value, 1)


def _verdict_from_score(score: float, scoring_profile: Dict[str, Any]) -> str:
    verdict_thresholds = dict(scoring_profile.get("verdict_thresholds") or {})
    review_min = float(verdict_thresholds.get("review_min", 70.0))
    hold_min = float(verdict_thresholds.get("hold_min", 50.0))
    if score >= review_min:
        return "review"
    if score >= hold_min:
        return "hold"
    return "avoid"

"""Backtest labeling helpers for archived batch outputs."""

from __future__ import annotations

from datetime import date
from datetime import datetime
from typing import Any
from typing import Dict
from typing import Iterable
from typing import List
from typing import Optional

from stock_report.connectors.market_data import MarketDataClient
from stock_report.connectors.market_data import PriceHistory


def build_backtest_snapshot(
    *,
    batch_date: str,
    generated_at_utc: str,
    benchmark_symbol: str,
    scorecards: List[Dict[str, Any]],
    horizons: Iterable[int],
    history_range: str = "2y",
    market_data_client: Optional[MarketDataClient] = None,
) -> Dict[str, Any]:
    """Join saved scorecards with realized forward returns."""

    normalized_horizons = sorted(
        {int(value) for value in horizons if int(value) > 0}
    )
    if not normalized_horizons:
        raise ValueError("At least one positive horizon is required.")

    client = market_data_client or MarketDataClient()
    symbols_to_fetch = _symbols_to_fetch(scorecards, benchmark_symbol)
    histories = {}
    history_errors = {}

    for symbol in symbols_to_fetch:
        try:
            histories[symbol] = client.fetch_history(symbol, range_value=history_range)
        except Exception as exc:
            history_errors[symbol] = str(exc)

    results = []
    for scorecard in scorecards:
        asset = dict(scorecard.get("asset") or {})
        scores = dict(scorecard.get("scores") or {})
        freshness = dict(scorecard.get("freshness") or {})
        symbol = str(asset.get("symbol") or "").upper()
        asset_benchmark = str(
            asset.get("benchmark_symbol") or benchmark_symbol
        ).upper()
        score_date = str(freshness.get("price_data_as_of") or batch_date)
        horizon_results = {}

        for horizon in normalized_horizons:
            asset_result = _forward_return_for_history(
                histories.get(symbol),
                score_date,
                horizon,
                fetch_error=history_errors.get(symbol),
            )
            benchmark_result = _forward_return_for_history(
                histories.get(asset_benchmark),
                score_date,
                horizon,
                fetch_error=history_errors.get(asset_benchmark),
            )
            excess_return = _excess_return(asset_result, benchmark_result)
            horizon_key = _horizon_key(horizon)
            horizon_results[horizon_key] = {
                "trading_days": horizon,
                "asset": asset_result,
                "benchmark": benchmark_result,
                "excess_return": excess_return,
                "evaluation": _evaluate_verdict(
                    verdict=str(scores.get("verdict") or ""),
                    asset_return=asset_result.get("return_pct"),
                    excess_return=excess_return,
                ),
            }

        results.append(
            {
                "symbol": symbol,
                "name": asset.get("name"),
                "display_name": asset.get("display_name"),
                "asset_type": asset.get("asset_type"),
                "market": asset.get("market"),
                "theme": asset.get("theme"),
                "benchmark_symbol": asset_benchmark,
                "score_date": score_date,
                "total_score": _safe_float(scores.get("total_score")),
                "base_total_score": _safe_float(scores.get("base_total_score")),
                "confidence_score": _safe_float(scores.get("confidence_score")),
                "verdict": scores.get("verdict"),
                "horizons": horizon_results,
            }
        )

    summary_by_horizon = _summarize_by_horizon(results, normalized_horizons)
    counts = {
        "scorecards": len(scorecards),
        "symbols_with_history_errors": len(history_errors),
        "horizons": {
            _horizon_key(horizon): _count_horizon_statuses(results, horizon)
            for horizon in normalized_horizons
        },
    }

    payload = {
        "batch_date": batch_date,
        "generated_at_utc": generated_at_utc,
        "benchmark_symbol": benchmark_symbol,
        "history_range": history_range,
        "horizons": normalized_horizons,
        "counts": counts,
        "summary_by_horizon": summary_by_horizon,
        "results": results,
        "history_errors": history_errors,
    }
    payload["guide_ko"] = {
        "거래일기준": "5d, 20d, 60d는 달력이 아니라 거래일 기준입니다.",
        "asset_return": "점수 기준일 종가 대비 해당 거래일 후 종가 수익률입니다.",
        "benchmark_return": "동일 기준일과 동일 거래일 구간에서 벤치마크 수익률입니다.",
        "excess_return": "자산 수익률에서 벤치마크 수익률을 뺀 값입니다.",
        "verdict_alignment": (
            "검토는 초과수익률 0% 이상, 회피는 0% 이하, 보류는 -5% 초과 5% 미만이면 정합으로 봅니다."
        ),
    }
    payload["readable_ko"] = _build_readable_ko(payload)
    return payload


def build_backtest_aggregate(
    *,
    snapshots: List[Dict[str, Any]],
    generated_at_utc: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict[str, Any]:
    """Aggregate multiple backtest snapshots into calibration summaries."""

    included_snapshots = _filter_snapshots_by_date(
        snapshots=snapshots,
        date_from=date_from,
        date_to=date_to,
    )
    horizons = _aggregate_horizons(included_snapshots)
    observations = _flatten_snapshot_results(included_snapshots)

    payload = {
        "generated_at_utc": generated_at_utc,
        "date_from": date_from,
        "date_to": date_to,
        "included_batches": [
            snapshot.get("batch_date")
            for snapshot in included_snapshots
            if snapshot.get("batch_date")
        ],
        "horizons": [int(item[:-1]) for item in horizons],
        "counts": {
            "snapshots_total": len(snapshots),
            "snapshots_included": len(included_snapshots),
            "observations_total": len(observations),
            "status_by_horizon": {
                horizon_key: _aggregate_status_counts(observations, horizon_key)
                for horizon_key in horizons
            },
        },
        "verdict_summary_by_horizon": {
            horizon_key: _aggregate_group_metrics(
                observations,
                horizon_key=horizon_key,
                key_name="verdict",
                key_getter=lambda item: str(item.get("verdict") or "unknown").lower(),
            )
            for horizon_key in horizons
        },
        "score_band_summary_by_horizon": {
            horizon_key: _aggregate_group_metrics(
                observations,
                horizon_key=horizon_key,
                key_name="score_band",
                key_getter=lambda item: _score_band(item.get("total_score")),
            )
            for horizon_key in horizons
        },
    }
    payload["guide_ko"] = {
        "included_batches": "집계에 포함된 배치 날짜 목록입니다.",
        "verdict_summary": "각 판정 그룹의 평균 수익률과 정합률을 보여줍니다.",
        "score_band_summary": "종합 점수대별 평균 수익률과 정합률을 보여줍니다.",
        "status_by_horizon": "완료, 미완료, 수집 실패 등 상태 건수입니다.",
    }
    payload["readable_ko"] = _build_aggregate_readable_ko(payload)
    return payload


def _filter_snapshots_by_date(
    *,
    snapshots: List[Dict[str, Any]],
    date_from: Optional[str],
    date_to: Optional[str],
) -> List[Dict[str, Any]]:
    from_date = _parse_date(date_from) if date_from else None
    to_date = _parse_date(date_to) if date_to else None

    filtered = []
    for snapshot in snapshots:
        batch_date = _parse_date(str(snapshot.get("batch_date") or ""))
        if batch_date is None:
            continue
        if from_date is not None and batch_date < from_date:
            continue
        if to_date is not None and batch_date > to_date:
            continue
        filtered.append(snapshot)
    filtered.sort(key=lambda item: str(item.get("batch_date") or ""))
    return filtered


def _aggregate_horizons(snapshots: List[Dict[str, Any]]) -> List[str]:
    values = set()
    for snapshot in snapshots:
        for horizon in snapshot.get("horizons", []):
            values.add(_horizon_key(int(horizon)))
    return sorted(values, key=lambda item: int(item[:-1]))


def _flatten_snapshot_results(snapshots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    observations = []
    for snapshot in snapshots:
        batch_date = str(snapshot.get("batch_date") or "")
        for item in snapshot.get("results", []):
            observation = dict(item)
            observation["batch_date"] = batch_date
            observations.append(observation)
    return observations


def _aggregate_status_counts(
    observations: List[Dict[str, Any]],
    horizon_key: str,
) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in observations:
        asset_result = dict(item.get("horizons", {}).get(horizon_key, {}).get("asset") or {})
        status = str(asset_result.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _aggregate_group_metrics(
    observations: List[Dict[str, Any]],
    *,
    horizon_key: str,
    key_name: str,
    key_getter,
) -> Dict[str, Any]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for item in observations:
        groups.setdefault(str(key_getter(item)), []).append(item)

    summary = {}
    for group_key, items in sorted(groups.items()):
        metrics = _summarize_group(items, horizon_key)
        metrics[key_name] = group_key
        summary[group_key] = metrics
    return summary


def _symbols_to_fetch(
    scorecards: List[Dict[str, Any]],
    default_benchmark_symbol: str,
) -> List[str]:
    symbols = set()
    for scorecard in scorecards:
        asset = dict(scorecard.get("asset") or {})
        symbol = str(asset.get("symbol") or "").upper()
        benchmark = str(
            asset.get("benchmark_symbol") or default_benchmark_symbol
        ).upper()
        if symbol:
            symbols.add(symbol)
        if benchmark:
            symbols.add(benchmark)
    return sorted(symbols)


def _forward_return_for_history(
    history: Optional[PriceHistory],
    anchor_date: str,
    horizon: int,
    fetch_error: Optional[str] = None,
) -> Dict[str, Any]:
    if history is None:
        return {
            "status": "fetch_error" if fetch_error else "no_history",
            "error": fetch_error,
            "entry_date": None,
            "exit_date": None,
            "entry_price": None,
            "exit_price": None,
            "return_pct": None,
        }

    target_date = _parse_date(anchor_date)
    if target_date is None:
        return {
            "status": "invalid_anchor_date",
            "error": "Invalid anchor date: {value}".format(value=anchor_date),
            "entry_date": None,
            "exit_date": None,
            "entry_price": None,
            "exit_price": None,
            "return_pct": None,
        }

    bars = list(history.bars)
    anchor_index = None
    for index, bar in enumerate(bars):
        if bar.timestamp.date() <= target_date:
            anchor_index = index
        else:
            break

    if anchor_index is None:
        return {
            "status": "missing_anchor",
            "error": "No bar was found on or before {value}".format(value=anchor_date),
            "entry_date": None,
            "exit_date": None,
            "entry_price": None,
            "exit_price": None,
            "return_pct": None,
        }

    exit_index = anchor_index + horizon
    entry_bar = bars[anchor_index]
    if exit_index >= len(bars):
        return {
            "status": "pending",
            "error": None,
            "entry_date": entry_bar.timestamp.date().isoformat(),
            "exit_date": None,
            "entry_price": round(entry_bar.adjclose, 4),
            "exit_price": None,
            "return_pct": None,
        }

    exit_bar = bars[exit_index]
    if entry_bar.adjclose == 0:
        return {
            "status": "invalid_entry_price",
            "error": "Entry price was zero.",
            "entry_date": entry_bar.timestamp.date().isoformat(),
            "exit_date": exit_bar.timestamp.date().isoformat(),
            "entry_price": round(entry_bar.adjclose, 4),
            "exit_price": round(exit_bar.adjclose, 4),
            "return_pct": None,
        }

    return_pct = round(((exit_bar.adjclose / entry_bar.adjclose) - 1.0) * 100.0, 2)
    return {
        "status": "complete",
        "error": None,
        "entry_date": entry_bar.timestamp.date().isoformat(),
        "exit_date": exit_bar.timestamp.date().isoformat(),
        "entry_price": round(entry_bar.adjclose, 4),
        "exit_price": round(exit_bar.adjclose, 4),
        "return_pct": return_pct,
    }


def _excess_return(
    asset_result: Dict[str, Any],
    benchmark_result: Dict[str, Any],
) -> Optional[float]:
    asset_return = _safe_float(asset_result.get("return_pct"))
    benchmark_return = _safe_float(benchmark_result.get("return_pct"))
    if asset_return is None or benchmark_return is None:
        return None
    return round(asset_return - benchmark_return, 2)


def _evaluate_verdict(
    *,
    verdict: str,
    asset_return: Optional[float],
    excess_return: Optional[float],
) -> Dict[str, str]:
    metric = excess_return if excess_return is not None else asset_return
    if metric is None:
        return {
            "realized_bucket": "pending",
            "verdict_alignment": "pending",
        }

    if metric >= 5.0:
        realized_bucket = "strong_outperform"
    elif metric >= 0.0:
        realized_bucket = "outperform"
    elif metric > -5.0:
        realized_bucket = "in_line"
    else:
        realized_bucket = "underperform"

    verdict_normalized = str(verdict).lower()
    if verdict_normalized == "review":
        aligned = metric >= 0.0
    elif verdict_normalized == "avoid":
        aligned = metric <= 0.0
    else:
        aligned = -5.0 < metric < 5.0

    return {
        "realized_bucket": realized_bucket,
        "verdict_alignment": "aligned" if aligned else "misaligned",
    }


def _summarize_by_horizon(
    results: List[Dict[str, Any]],
    horizons: Iterable[int],
) -> Dict[str, Any]:
    summary = {}
    for horizon in horizons:
        horizon_key = _horizon_key(horizon)
        verdict_groups: Dict[str, List[Dict[str, Any]]] = {}
        for item in results:
            verdict = str(item.get("verdict") or "unknown").lower()
            verdict_groups.setdefault(verdict, []).append(item)

        summary[horizon_key] = {
            verdict: _summarize_group(items, horizon_key)
            for verdict, items in sorted(verdict_groups.items())
        }
    return summary


def _summarize_group(items: List[Dict[str, Any]], horizon_key: str) -> Dict[str, Any]:
    asset_returns = []
    benchmark_returns = []
    excess_returns = []
    aligned = 0
    completed = 0

    for item in items:
        horizon = dict(item.get("horizons", {}).get(horizon_key) or {})
        asset_result = dict(horizon.get("asset") or {})
        benchmark_result = dict(horizon.get("benchmark") or {})
        evaluation = dict(horizon.get("evaluation") or {})

        if asset_result.get("status") != "complete":
            continue

        completed += 1
        asset_return = _safe_float(asset_result.get("return_pct"))
        benchmark_return = _safe_float(benchmark_result.get("return_pct"))
        excess_return = _safe_float(horizon.get("excess_return"))
        if asset_return is not None:
            asset_returns.append(asset_return)
        if benchmark_return is not None:
            benchmark_returns.append(benchmark_return)
        if excess_return is not None:
            excess_returns.append(excess_return)
        if evaluation.get("verdict_alignment") == "aligned":
            aligned += 1

    return {
        "total": len(items),
        "completed": completed,
        "avg_asset_return": _average(asset_returns),
        "avg_benchmark_return": _average(benchmark_returns),
        "avg_excess_return": _average(excess_returns),
        "alignment_rate": round((aligned / completed) * 100.0, 1)
        if completed
        else None,
    }


def _count_horizon_statuses(results: List[Dict[str, Any]], horizon: int) -> Dict[str, int]:
    statuses: Dict[str, int] = {}
    horizon_key = _horizon_key(horizon)
    for item in results:
        asset_result = dict(item.get("horizons", {}).get(horizon_key, {}).get("asset") or {})
        status = str(asset_result.get("status") or "unknown")
        statuses[status] = statuses.get(status, 0) + 1
    return statuses


def _build_readable_ko(payload: Dict[str, Any]) -> Dict[str, Any]:
    results = []
    for item in payload.get("results", []):
        horizon_rows = {}
        for horizon_key, horizon in dict(item.get("horizons") or {}).items():
            asset_result = dict(horizon.get("asset") or {})
            benchmark_result = dict(horizon.get("benchmark") or {})
            evaluation = dict(horizon.get("evaluation") or {})
            horizon_rows[horizon_key] = {
                "상태": _status_label_ko(asset_result.get("status")),
                "자산수익률": _percent_text(asset_result.get("return_pct")),
                "벤치마크수익률": _percent_text(benchmark_result.get("return_pct")),
                "초과수익률": _percent_text(horizon.get("excess_return")),
                "판정정합": _alignment_label_ko(evaluation.get("verdict_alignment")),
                "실현구간평가": _bucket_label_ko(evaluation.get("realized_bucket")),
            }
        results.append(
            {
                "표시명": item.get("display_name") or item.get("name") or item.get("symbol"),
                "티커": item.get("symbol"),
                "판정": item.get("verdict"),
                "종합점수": _score_text(item.get("total_score")),
                "기준일": item.get("score_date"),
                "사후성과": horizon_rows,
            }
        )

    summary_by_horizon = {}
    for horizon_key, verdicts in dict(payload.get("summary_by_horizon") or {}).items():
        summary_by_horizon[horizon_key] = {
            verdict: {
                "전체": values.get("total"),
                "완료": values.get("completed"),
                "평균자산수익률": _percent_text(values.get("avg_asset_return")),
                "평균벤치마크수익률": _percent_text(values.get("avg_benchmark_return")),
                "평균초과수익률": _percent_text(values.get("avg_excess_return")),
                "정합률": _percent_text(values.get("alignment_rate")),
            }
            for verdict, values in dict(verdicts or {}).items()
        }

    return {
        "배치일자": payload.get("batch_date"),
        "생성시각_UTC": payload.get("generated_at_utc"),
        "비교기준": payload.get("benchmark_symbol"),
        "평가구간": ["{value}거래일".format(value=h) for h in payload.get("horizons", [])],
        "판정별요약": summary_by_horizon,
        "자산별결과": results,
    }


def _build_aggregate_readable_ko(payload: Dict[str, Any]) -> Dict[str, Any]:
    verdict_summary = {}
    for horizon_key, groups in dict(payload.get("verdict_summary_by_horizon") or {}).items():
        verdict_summary[horizon_key] = {
            _verdict_label_ko(group_key): _group_metrics_readable_ko(values)
            for group_key, values in dict(groups or {}).items()
        }

    score_band_summary = {}
    for horizon_key, groups in dict(payload.get("score_band_summary_by_horizon") or {}).items():
        score_band_summary[horizon_key] = {
            _score_band_label_ko(group_key): _group_metrics_readable_ko(values)
            for group_key, values in dict(groups or {}).items()
        }

    return {
        "생성시각_UTC": payload.get("generated_at_utc"),
        "집계기간": {
            "시작": payload.get("date_from") or "전체",
            "종료": payload.get("date_to") or "전체",
        },
        "포함배치": payload.get("included_batches", []),
        "건수": {
            "전체스냅샷": payload.get("counts", {}).get("snapshots_total"),
            "포함스냅샷": payload.get("counts", {}).get("snapshots_included"),
            "전체관측치": payload.get("counts", {}).get("observations_total"),
        },
        "상태요약": {
            horizon_key: {
                _status_label_ko(status): count
                for status, count in dict(statuses or {}).items()
            }
            for horizon_key, statuses in dict(
                payload.get("counts", {}).get("status_by_horizon") or {}
            ).items()
        },
        "판정별집계": verdict_summary,
        "점수대별집계": score_band_summary,
    }


def _group_metrics_readable_ko(values: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "전체": values.get("total"),
        "완료": values.get("completed"),
        "평균자산수익률": _percent_text(values.get("avg_asset_return")),
        "평균벤치마크수익률": _percent_text(values.get("avg_benchmark_return")),
        "평균초과수익률": _percent_text(values.get("avg_excess_return")),
        "정합률": _percent_text(values.get("alignment_rate")),
    }


def _parse_date(value: str) -> Optional[date]:
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def _average(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return round(sum(values) / float(len(values)), 2)


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _score_text(value: Any) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "해당 없음"
    return "{value:.1f}/100".format(value=numeric)


def _percent_text(value: Any) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "해당 없음"
    return "{value:.1f}%".format(value=numeric)


def _status_label_ko(status: Any) -> str:
    return {
        "complete": "완료",
        "pending": "미완료",
        "missing_anchor": "기준일 누락",
        "invalid_anchor_date": "기준일 오류",
        "fetch_error": "수집 실패",
        "no_history": "이력 없음",
        "invalid_entry_price": "기준 가격 오류",
    }.get(str(status), str(status))


def _alignment_label_ko(status: Any) -> str:
    return {
        "aligned": "정합",
        "misaligned": "비정합",
        "pending": "보류",
    }.get(str(status), str(status))


def _bucket_label_ko(bucket: Any) -> str:
    return {
        "strong_outperform": "강한 초과수익",
        "outperform": "초과수익",
        "in_line": "비슷한 흐름",
        "underperform": "부진",
        "pending": "판정 보류",
    }.get(str(bucket), str(bucket))


def _verdict_label_ko(verdict: Any) -> str:
    return {
        "review": "검토",
        "hold": "보류",
        "avoid": "회피",
        "unknown": "미분류",
    }.get(str(verdict), str(verdict))


def _score_band(score: Any) -> str:
    numeric = _safe_float(score)
    if numeric is None:
        return "unknown"
    if numeric < 50.0:
        return "0-49"
    if numeric < 60.0:
        return "50-59"
    if numeric < 70.0:
        return "60-69"
    if numeric < 80.0:
        return "70-79"
    return "80-100"


def _score_band_label_ko(band: Any) -> str:
    return {
        "0-49": "0~49점",
        "50-59": "50~59점",
        "60-69": "60~69점",
        "70-79": "70~79점",
        "80-100": "80~100점",
        "unknown": "미분류",
    }.get(str(band), str(band))


def _horizon_key(horizon: int) -> str:
    return "{value}d".format(value=horizon)

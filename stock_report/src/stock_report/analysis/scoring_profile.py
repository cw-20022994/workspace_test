"""Scoring profile loading and normalization helpers."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any
from typing import Dict
from typing import Optional

import yaml

DEFAULT_SCORING_PROFILE = {
    "version": 1,
    "weights": {
        "trend": 0.35,
        "fundamentals": 0.25,
        "news": 0.20,
        "risk": 0.20,
    },
    "verdict_thresholds": {
        "review_min": 70.0,
        "hold_min": 50.0,
    },
    "confidence_thresholds": {
        "high_min": 80.0,
        "medium_min": 60.0,
    },
    "calibration_policy": {
        "target_horizon": 20,
        "min_completed_observations": 12,
        "min_group_observations": 4,
        "threshold_step": 5.0,
        "max_weight_shift": 0.05,
    },
}


def default_scoring_profile() -> Dict[str, Any]:
    """Return a deep copy of the default scoring profile."""

    return deepcopy(DEFAULT_SCORING_PROFILE)


def load_scoring_profile(path: Optional[str] = None) -> Dict[str, Any]:
    """Load a scoring profile from YAML or return normalized defaults."""

    profile = default_scoring_profile()
    resolved_path = _resolve_profile_path(path)
    if resolved_path is None or not resolved_path.exists():
        return normalize_scoring_profile(profile)

    payload = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        _deep_update(profile, payload)
    return normalize_scoring_profile(profile)


def normalize_scoring_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize numeric values and ensure required sections exist."""

    normalized = default_scoring_profile()
    if isinstance(profile, dict):
        _deep_update(normalized, profile)

    weights = dict(normalized.get("weights") or {})
    normalized["weights"] = _normalize_weights(weights)

    verdict_thresholds = dict(normalized.get("verdict_thresholds") or {})
    normalized["verdict_thresholds"] = {
        "review_min": float(verdict_thresholds.get("review_min", 70.0)),
        "hold_min": float(verdict_thresholds.get("hold_min", 50.0)),
    }
    if normalized["verdict_thresholds"]["hold_min"] > normalized["verdict_thresholds"]["review_min"]:
        normalized["verdict_thresholds"]["hold_min"] = normalized["verdict_thresholds"]["review_min"]

    confidence_thresholds = dict(normalized.get("confidence_thresholds") or {})
    normalized["confidence_thresholds"] = {
        "high_min": float(confidence_thresholds.get("high_min", 80.0)),
        "medium_min": float(confidence_thresholds.get("medium_min", 60.0)),
    }
    if normalized["confidence_thresholds"]["medium_min"] > normalized["confidence_thresholds"]["high_min"]:
        normalized["confidence_thresholds"]["medium_min"] = normalized["confidence_thresholds"]["high_min"]

    calibration_policy = dict(normalized.get("calibration_policy") or {})
    normalized["calibration_policy"] = {
        "target_horizon": int(calibration_policy.get("target_horizon", 20)),
        "min_completed_observations": int(
            calibration_policy.get("min_completed_observations", 12)
        ),
        "min_group_observations": int(
            calibration_policy.get("min_group_observations", 4)
        ),
        "threshold_step": float(calibration_policy.get("threshold_step", 5.0)),
        "max_weight_shift": float(calibration_policy.get("max_weight_shift", 0.05)),
    }
    return normalized


def dump_scoring_profile(profile: Dict[str, Any]) -> str:
    """Serialize a normalized scoring profile to YAML."""

    normalized = normalize_scoring_profile(profile)
    return yaml.safe_dump(normalized, sort_keys=False, allow_unicode=True)


def _resolve_profile_path(path: Optional[str]) -> Optional[Path]:
    if path:
        return Path(path)

    project_root = Path(__file__).resolve().parents[3]
    default_path = project_root / "config" / "scoring.yaml"
    if default_path.exists():
        return default_path
    return None


def _normalize_weights(weights: Dict[str, Any]) -> Dict[str, float]:
    keys = ("trend", "fundamentals", "news", "risk")
    numeric = {}
    for key in keys:
        try:
            numeric[key] = max(float(weights.get(key, DEFAULT_SCORING_PROFILE["weights"][key])), 0.0)
        except (TypeError, ValueError):
            numeric[key] = float(DEFAULT_SCORING_PROFILE["weights"][key])

    total = sum(numeric.values())
    if total <= 0:
        return dict(DEFAULT_SCORING_PROFILE["weights"])
    return {key: round(value / total, 6) for key, value in numeric.items()}


def _deep_update(target: Dict[str, Any], payload: Dict[str, Any]) -> None:
    for key, value in payload.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value

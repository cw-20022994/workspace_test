"""Helpers for reading the project watchlist configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from typing import Dict
from typing import Iterable
from typing import Optional

import yaml

from stock_report.models import AssetDefinition
from stock_report.models import Watchlist


def load_watchlist(path: str) -> Watchlist:
    """Load and normalize a watchlist YAML file."""

    raw_path = Path(path)
    payload = yaml.safe_load(raw_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Watchlist payload must be a mapping.")

    assets = {}
    assets.update(_build_assets(payload.get("required_etfs", []), asset_type="etf"))
    assets.update(_build_assets(payload.get("core_etfs", []), asset_type="etf"))
    assets.update(_build_assets(payload.get("us_theme_stocks", []), asset_type="stock"))
    assets.update(
        _build_assets(payload.get("korea_hbm_hbf_stocks", []), asset_type="stock")
    )

    theme_notes = {}
    for item in payload.get("theme_notes", []):
        if not isinstance(item, dict) or "theme" not in item:
            continue
        item_copy = dict(item)
        theme = str(item_copy.pop("theme")).strip()
        theme_notes[theme] = {str(key): str(value) for key, value in item_copy.items()}

    return Watchlist(
        version=int(payload.get("version", 1)),
        defaults=dict(payload.get("defaults", {})),
        assets=assets,
        theme_notes=theme_notes,
        reporting=dict(payload.get("reporting", {})),
    )


def _build_assets(items: Iterable[Dict[str, Any]], asset_type: str) -> Dict[str, AssetDefinition]:
    assets = {}
    for item in items:
        if not isinstance(item, dict):
            continue

        symbol = str(item.get("symbol", "")).strip()
        if not symbol:
            continue

        theme = _resolve_theme(item, asset_type)
        asset = AssetDefinition(
            symbol=symbol,
            name=str(item.get("name", symbol)).strip(),
            asset_type=asset_type,
            theme=theme,
            market=str(item.get("market", "US")).strip(),
            role=_maybe_string(item.get("role")),
            thesis=_maybe_string(item.get("thesis")),
            note=_maybe_string(item.get("note")),
        )
        assets[symbol.upper()] = asset
    return assets


def _resolve_theme(item: Dict[str, Any], asset_type: str) -> str:
    explicit_theme = _maybe_string(item.get("theme"))
    if explicit_theme:
        return explicit_theme

    role = _maybe_string(item.get("role"))
    if role:
        return role

    if asset_type == "etf":
        return "broad_market_etf"
    return "unclassified"


def _maybe_string(value: Optional[Any]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

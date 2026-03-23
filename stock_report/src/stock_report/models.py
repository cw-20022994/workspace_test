"""Shared data models used across the project."""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Dict
from typing import List
from typing import Optional


@dataclass(frozen=True)
class AssetDefinition:
    """Static metadata for a tracked stock or ETF."""

    symbol: str
    name: str
    asset_type: str
    theme: str
    market: str = "US"
    role: Optional[str] = None
    thesis: Optional[str] = None
    note: Optional[str] = None


@dataclass
class Watchlist:
    """Resolved watchlist configuration."""

    version: int
    defaults: Dict[str, Any]
    assets: Dict[str, AssetDefinition]
    theme_notes: Dict[str, Dict[str, str]]
    reporting: Dict[str, Any]

    def get_asset(self, symbol: str) -> AssetDefinition:
        asset = self.assets.get(symbol.upper())
        if asset is None:
            raise KeyError("Unknown symbol: {symbol}".format(symbol=symbol))
        return asset


@dataclass(frozen=True)
class NewsItem:
    """Normalized news record used by scoring and rendering."""

    headline: str
    source: str
    published_at: str
    impact: str
    summary_ko: str = ""
    category: str = "general"
    priority_score: float = 0.0
    materiality: float = 0.5
    tags: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "NewsItem":
        return cls(
            headline=str(payload.get("headline", "")).strip(),
            summary_ko=str(
                payload.get("summary_ko", payload.get("summary", ""))
            ).strip(),
            source=str(payload.get("source", "unknown")).strip(),
            published_at=str(payload.get("published_at", "unknown")).strip(),
            impact=str(payload.get("impact", "neutral")).strip().lower(),
            category=str(payload.get("category", "general")).strip().lower(),
            priority_score=float(payload.get("priority_score", 0.0)),
            materiality=float(payload.get("materiality", 0.5)),
            tags=[str(tag).strip().lower() for tag in payload.get("tags", [])],
        )


@dataclass
class AnalysisInput:
    """Structured analysis input consumed by the CLI."""

    asset_type: str = "stock"
    report_time_utc: Optional[str] = None
    benchmark_symbol: Optional[str] = None
    prices: Dict[str, Any] = field(default_factory=dict)
    fundamentals: Dict[str, Any] = field(default_factory=dict)
    etf: Dict[str, Any] = field(default_factory=dict)
    news: List[NewsItem] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)
    freshness: Dict[str, Any] = field(default_factory=dict)
    theme_signals: Dict[str, Any] = field(default_factory=dict)
    notes: Optional[str] = None

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "AnalysisInput":
        return cls(
            asset_type=str(payload.get("asset_type", "stock")).strip().lower(),
            report_time_utc=payload.get("report_time_utc"),
            benchmark_symbol=payload.get("benchmark_symbol"),
            prices=dict(payload.get("prices", {})),
            fundamentals=dict(payload.get("fundamentals", {})),
            etf=dict(payload.get("etf", {})),
            news=[NewsItem.from_dict(item) for item in payload.get("news", [])],
            risk_flags=[
                str(item).strip()
                for item in payload.get("risk_flags", payload.get("risks", []))
            ],
            freshness=dict(payload.get("freshness", {})),
            theme_signals=dict(payload.get("theme_signals", {})),
            notes=payload.get("notes"),
        )


@dataclass
class ScoreBreakdown:
    """Deterministic scoring output."""

    trend_score: float
    fundamentals_score: float
    news_score: float
    risk_score: float
    base_total_score: float
    theme_overlay: float
    overlay_rationale: str
    total_score: float
    verdict: str
    confidence_score: float
    confidence_label: str
    missing_inputs: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

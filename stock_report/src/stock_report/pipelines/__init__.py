"""Pipeline entry points for data ingestion and report generation."""

from stock_report.pipelines.live_profile import LiveAnalysisBuilder

__all__ = ["LiveAnalysisBuilder"]

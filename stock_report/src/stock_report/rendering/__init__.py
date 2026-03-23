"""Report rendering modules."""

from stock_report.rendering.batch import build_daily_summary_payload
from stock_report.rendering.batch import render_daily_summary_markdown
from stock_report.rendering.markdown import build_scorecard
from stock_report.rendering.markdown import render_markdown_report

__all__ = [
    "build_daily_summary_payload",
    "build_scorecard",
    "render_daily_summary_markdown",
    "render_markdown_report",
]

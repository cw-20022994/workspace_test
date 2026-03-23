# Report Template

Use the following structure for the first Markdown report.

```md
# {{ symbol }} - Research Report

- Name: {{ asset_name }}
- Asset type: {{ asset_type }}
- Report time: {{ report_time_utc }}
- Benchmark: {{ benchmark_symbol }}
- Verdict: {{ verdict }}
- Total score: {{ total_score }}/100
- Confidence: {{ confidence }}

## Executive Summary

{{ summary_paragraph }}

## What Changed Recently

- Price move (5d): {{ return_5d }}
- Price move (20d): {{ return_20d }}
- Relative strength vs benchmark (20d): {{ rs_20d }}
- Realized volatility: {{ volatility }}
- Drawdown from recent high: {{ drawdown }}

## Top News

1. {{ headline_1 }} | {{ source_1 }} | {{ published_at_1 }} | {{ impact_1 }}
2. {{ headline_2 }} | {{ source_2 }} | {{ published_at_2 }} | {{ impact_2 }}
3. {{ headline_3 }} | {{ source_3 }} | {{ published_at_3 }} | {{ impact_3 }}

## Trend Analysis

- Short-term trend: {{ short_trend_view }}
- Medium-term trend: {{ medium_trend_view }}
- Technical evidence:
  - price vs 20D MA: {{ price_vs_ma20 }}
  - price vs 50D MA: {{ price_vs_ma50 }}
  - price vs 200D MA: {{ price_vs_ma200 }}

## Fundamentals Snapshot

- Revenue growth: {{ revenue_growth }}
- Earnings growth: {{ earnings_growth }}
- Profitability: {{ profitability_view }}
- Valuation: {{ valuation_view }}
- Balance-sheet risk: {{ balance_sheet_view }}

## ETF Notes

- Category: {{ etf_category }}
- Expense ratio: {{ expense_ratio }}
- Concentration view: {{ concentration_view }}
- Holdings or sector notes: {{ holdings_note }}

## Scorecard

- Trend score: {{ trend_score }}/100
- Fundamental score: {{ fundamental_score }}/100
- News score: {{ news_score }}/100
- Risk score: {{ risk_score }}/100
- Theme overlay: {{ theme_overlay }}
- Overlay rationale: {{ overlay_rationale }}

## Key Risks

- {{ risk_1 }}
- {{ risk_2 }}
- {{ risk_3 }}

## Bottom Line

{{ bottom_line }}

## Data Freshness

- Price data as of: {{ price_data_time }}
- Fundamentals as of: {{ fundamentals_data_time }}
- News window: {{ news_window }}

Not financial advice. Use this report as a research aid.
```

# MVP Specification

## Problem Statement

Investors spend too much time jumping between charting tools, financial data pages, and scattered news links. The product should compress that workflow into one report per asset.

## Target Outcomes

- Generate a high-signal report for one stock or ETF in one run
- Generate a daily batch report for a predefined watchlist
- Make the recommendation explainable with numeric evidence and recent news context

## Primary User Stories

1. As a user, I want to run a report for a single ticker and immediately see whether it deserves more research.
2. As a user, I want a morning batch report for my watchlist so I can focus only on names with meaningful change.
3. As a user, I want ETF reports to include benchmark context and category-specific commentary.

## Functional Requirements

### Universe

- Support US-listed stocks and ETFs
- Keep stock coverage narrow in MVP:
  - AI compute and accelerators
  - semiconductor and memory
  - HBF-related memory and storage
  - AI networking, optical, and custom silicon
  - semiconductor equipment
  - AI data center power and cooling
- Include Korea-listed names only when they are directly tied to HBM or HBF themes
- Include at least one S&P 500 ETF in the default universe
- Allow a configurable watchlist file

### Data Ingestion

- Pull historical daily OHLCV data
- Pull a fundamentals snapshot when available
- Pull recent news for each ticker
- Track source timestamp and fetch timestamp for freshness

### News Processing

- Deduplicate similar headlines
- Keep the top 3-5 material items for the report
- Produce a short summary and a directional impact tag: positive, neutral, negative, mixed

### Quantitative Analysis

- Compute short- and medium-term returns
- Compute moving average relationships
- Compute drawdown and realized volatility
- Compute relative strength versus the chosen benchmark
- Add ETF-specific metrics when available, such as category, expense ratio, and concentration cues

### Scoring

- Produce section scores for trend, fundamentals, news, and risk
- Produce a weighted total score from 0 to 100
- Map the score to a verdict: `review`, `hold`, `avoid`
- Include a confidence band driven by data completeness and signal alignment
- Allow theme-specific overlays for HBM and HBF names when the generic model misses the actual adoption curve

### Reporting

- Render a Markdown report for humans
- Render a JSON scorecard for downstream automation
- Include data freshness, assumptions, and risk flags

## Non-Functional Requirements

- Deterministic numeric scoring
- LLM use only for summarization and final narrative phrasing
- Re-runnable without changing scores for identical inputs
- Clear separation between raw data, processed data, features, and reports

## Acceptance Criteria

- A single command can generate a report for one stock
- A single command can generate a report for one ETF
- A batch command can generate reports for all watchlist symbols
- Reports contain at least one benchmark comparison for each symbol
- Reports contain at least one risk section and one explicit verdict
- Missing data degrades confidence instead of silently failing

## Out of Scope for MVP

- Intraday trading signals
- Autonomous order execution
- Portfolio optimization
- Personalized tax logic
- Fully automated price targets
- Broad coverage of consumer, healthcare, finance, or unrelated non-AI sectors

## Important Product Constraint

The output is decision support, not financial advice. Reports should explain why the model leans positive or negative and should surface uncertainty when evidence is weak.

## Theme Note

Treat `HBF` as a separate emerging theme rather than a synonym for `HBM`. As of February 25, 2026, Sandisk and SK hynix announced the start of HBF standardization for the AI inference era, so the project should allow dedicated HBF tagging and watchlists.

For Korea coverage, keep the exception narrow and limited to names with direct HBM or HBF relevance. The default set should include SK hynix and Samsung Electronics.

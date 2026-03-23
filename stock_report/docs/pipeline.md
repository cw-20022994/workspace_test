# Data Pipeline Design

## Design Principles

- Keep market data and scoring deterministic
- Use an LLM only after structured facts are already assembled
- Preserve raw records so analyses can be reproduced
- Fail loudly on stale or partial data

## End-to-End Flow

1. Load the watchlist and choose the benchmark
2. Fetch raw price history, metadata, fundamentals, and news
3. Normalize records into internal models
4. Build features and section scores
5. Generate the narrative summary
6. Render Markdown and JSON outputs
7. Store artifacts and run quality checks

## Storage Zones

- `data/raw/`
  - unmodified connector payloads
- `data/processed/`
  - normalized tables or files keyed by symbol and date
- `data/features/`
  - engineered features and section scores
- `reports/daily/`
  - scheduled reports
- `reports/ad_hoc/`
  - one-off user-triggered reports

## Logical Modules

The watchlist should tag each asset with a theme so reports can compare similar names.

- `ai_compute`
- `semiconductor_memory`
- `hbf_memory_storage`
- `ai_networking_optical`
- `semiconductor_equipment`
- `ai_power_cooling`
- `korea_hbm_hbf`

### Ingestion

- `prices`: daily bars and benchmark bars
- `fundamentals`: ratios, growth metrics, balance-sheet snapshot
- `news`: headlines, article metadata, publication time, source

### Normalization

- standardize timestamps and currencies
- standardize ticker metadata
- deduplicate news and map tickers to assets

### Feature Engineering

- returns over 5, 20, 60, 252 trading days
- moving averages and slope
- drawdown and volatility
- relative strength versus benchmark
- ETF-specific fields if available

### Scoring

- assign section scores
- weight them into a total score
- derive a verdict and confidence band
- apply theme-specific overlays when a theme has different adoption evidence than a standard stock

### Narrative Generation

- summarize what changed
- connect numeric signals with recent news
- highlight the strongest bullish and bearish evidence

### Rendering

- write Markdown report
- write JSON scorecard
- stamp source freshness and run metadata

## Job Boundaries

Recommended job split for the first implementation:

1. `fetch_market_data`
2. `fetch_fundamentals`
3. `fetch_news`
4. `build_features`
5. `score_assets`
6. `render_reports`

These can run sequentially at first. Parallelization is optional after the data model is stable.

## Freshness and Safety Checks

- reject missing benchmark data for benchmark-relative metrics
- lower confidence when fundamentals are stale
- flag duplicated or low-quality news clusters
- record the exact run time, source time, and lookback windows used
- flag HBF reports when the narrative is based mostly on announcements without adoption, partner, or shipment evidence

## Suggested Initial Cadence

- Daily batch run after market close
- Optional pre-market update for overnight news only
- Ad hoc single-symbol run at any time

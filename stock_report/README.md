# stock_report

Research report generator for stocks and ETFs.

This repository currently contains the project blueprint and the initial folder skeleton. The target product pulls market data and news, builds deterministic signals, and renders decision-support reports for individual stocks and ETFs.

## Product Goal

- Read major news for stocks and ETFs.
- Analyze price history, volume, benchmark-relative strength, and basic fundamentals.
- Produce a report that answers: what changed, what the trend looks like, what the main risks are, and whether the asset is worth deeper investment review.

## MVP Scope

- Asset coverage: US stocks and ETFs, with Korea included only for HBM/HBF-related names
- Required benchmark coverage: at least one S&P 500 ETF
- Default benchmark set: `SPY`, `VOO`, `IVV`
- Output formats: Markdown report plus machine-readable JSON scorecard
- Run modes: single-symbol report and daily watchlist batch

## Coverage Focus

The first version should stay narrow and target sectors where AI demand shows up clearly in market and company data.

- US AI compute and accelerator names
- US semiconductor and memory names
- US HBF-related memory and storage names
- US AI networking, optical, and custom silicon names
- US semiconductor equipment names
- US AI data center power and cooling names
- Korea HBM/HBF-related names only

## Core Features

1. Watchlist management for stocks and ETFs within the allowed coverage themes
2. News ingestion, deduplication, and short narrative summary
3. Historical price and metadata ingestion
4. Feature generation for trend, momentum, volatility, and relative strength
5. Rule-based scoring for investment suitability
6. Report rendering with evidence, risks, and confidence

## Decision Framework

The first version should keep the numeric logic deterministic and use an LLM only for narrative summarization.

- Trend score: moving averages, breakout/breakdown status, relative strength, drawdown
- Fundamental score: growth, profitability, valuation snapshot, balance-sheet risk
- News score: earnings, guidance, product/regulatory events, sentiment, concentration of negative catalysts
- Risk score: volatility, gap risk, sector concentration, stale data, conflicting signals
- Final verdict: `review`, `hold`, or `avoid`, with a 0-100 total score and confidence band

For emerging themes such as `HBF`, use theme-specific evidence instead of forcing them into a generic semiconductor bucket. The scoring model should reward confirmed ecosystem progress and penalize theme hype without adoption signals.

## Repository Layout

```text
stock_report/
├── README.md
├── pyproject.toml
├── config/
│   └── watchlist.example.yaml
├── docs/
│   ├── mvp.md
│   ├── pipeline.md
│   └── report_template.md
├── src/
│   └── stock_report/
│       ├── __init__.py
│       ├── README.md
│       ├── analysis/
│       ├── pipelines/
│       └── rendering/
├── data/
│   └── README.md
├── reports/
│   └── README.md
└── tests/
    └── __init__.py
```

## Key Docs

- `docs/mvp.md`: product scope and acceptance criteria
- `docs/pipeline.md`: data flow and job boundaries
- `docs/report_template.md`: report shape and required sections
- `docs/scoring.md`: base scoring model plus HBF-specific scoring rules
- `docs/automation.md`: macOS launchd-based scheduler setup
- `config/watchlist.example.yaml`: starter universe with S&P 500 ETF coverage

## Current Implementation

The repository now includes a first runnable slice:

- watchlist YAML loading
- theme-aware deterministic scoring
- HBF overlay handling
- single-symbol Markdown and JSON report generation from structured input
- live price fetching from Stooq CSV and Naver Finance daily pages
- live fundamentals fetching from StockAnalysis and Naver Finance
- live ETF overview and top-holdings fetching from StockAnalysis ETF pages
- live headline fetching from Google News RSS

## Quick Start

Create a virtual environment and install the package:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

Generate a sample report:

```bash
stock-report single-symbol \
  --watchlist config/watchlist.example.yaml \
  --symbol SNDK \
  --input examples/profiles/sndk.json \
  --markdown-output reports/ad_hoc/sndk.md \
  --json-output reports/ad_hoc/sndk.json
```

You can also run it without installation:

```bash
PYTHONPATH=src python3 -m stock_report.cli single-symbol \
  --watchlist config/watchlist.example.yaml \
  --symbol NVDA \
  --input examples/profiles/nvda.json
```

Generate a live report from fetched price and news data:

```bash
stock-report live-symbol \
  --watchlist config/watchlist.example.yaml \
  --symbol NVDA \
  --markdown-output reports/ad_hoc/nvda_live.md \
  --json-output reports/ad_hoc/nvda_live.json \
  --profile-output reports/ad_hoc/nvda_live_profile.json
```

Generate a dated daily batch for the watchlist or a symbol subset:

```bash
stock-report daily-batch \
  --watchlist config/watchlist.example.yaml \
  --output-dir reports/daily \
  --date 2026-03-18 \
  --symbols SPY NVDA SNDK SMH
```

Generate a backtest snapshot from an archived daily batch:

```bash
stock-report backtest-labels \
  --batch-dir reports/daily/2026-03-18 \
  --output-dir reports/backtests \
  --horizons 5 20 60
```

Aggregate multiple backtest snapshots into a calibration summary:

```bash
stock-report backtest-summary \
  --input-dir reports/backtests \
  --output-dir reports/backtests/aggregate
```

Generate a scoring calibration report and proposed scoring profile:

```bash
stock-report calibration-report \
  --aggregate-json reports/backtests/aggregate/summary.json \
  --current-profile config/scoring.yaml \
  --output-dir reports/calibration/latest
```

Compare the current and proposed scoring profiles on a saved daily batch:

```bash
stock-report calibration-compare \
  --watchlist config/watchlist.example.yaml \
  --batch-dir reports/daily/2026-03-18 \
  --current-profile config/scoring.yaml \
  --proposed-profile reports/calibration/latest/proposed_scoring.yaml \
  --output-dir reports/calibration/latest
```

Run the full daily chain in one command:

```bash
stock-report daily-refresh \
  --watchlist config/watchlist.example.yaml \
  --date 2026-03-19 \
  --symbols SPY NVDA SNDK SMH \
  --daily-output-dir reports/daily \
  --backtest-output-dir reports/backtests \
  --aggregate-output-dir reports/backtests/aggregate \
  --calibration-output-dir reports/calibration/latest \
  --automation-output-dir reports/automation
```

Install the macOS scheduler:

```bash
./scripts/install_launchd.sh
```

Configure Telegram alerts for scheduled runs:

```bash
cp config/runtime.env.example config/runtime.env
# fill STOCK_REPORT_TELEGRAM_BOT_TOKEN and STOCK_REPORT_TELEGRAM_CHAT_ID
stock-report telegram-test
```

- The CLI also reads `config/runtime.env` automatically, so the manual Telegram test works without exporting env vars in your shell.

## Input Profile Shape

The current CLI expects a JSON analysis profile with:

- `prices`: returns, moving-average relationships, drawdown, volatility
- `fundamentals`: growth, margins, valuation, leverage
- `news`: headline list with impact and materiality
- `freshness`: source timestamps and data ages
- `theme_signals`: theme-specific evidence such as HBF standardization or commercialization progress

## Live Data Notes

- The live path fetches prices, headlines, stock fundamentals, and ETF overview data when a supported source is available.
- US and ETF prices currently use Stooq daily CSV as the primary source and Yahoo Chart as the fallback source.
- US stock fundamentals currently come from StockAnalysis financials and ratios pages.
- US ETF category, provider, expense ratio, AUM, holdings count, and top holdings currently come from StockAnalysis ETF pages.
- Korea `.KS` prices currently come from Naver Finance daily pages.
- Korea `.KS` stock fundamentals currently come from the Naver Finance company summary page.
- HTTP GET responses are cached locally under `data/raw/http_cache/` by default.
- The default HTTP cache TTL is 6 hours and can be overridden with `STOCK_REPORT_HTTP_CACHE_TTL_SECONDS`.
- You can disable the HTTP cache with `STOCK_REPORT_HTTP_CACHE_DISABLED=1` or move it with `STOCK_REPORT_HTTP_CACHE_DIR`.

## Daily Batch Output

- `daily-batch` writes to `reports/daily/<YYYY-MM-DD>/` by default.
- It creates `summary.md`, `summary.json`, and per-symbol `markdown/`, `scorecards/`, and `profiles/` subfolders.
- Batch runs continue past per-symbol fetch failures and record them in the summary, but the CLI exits non-zero when any symbol fails.

## Backtest Snapshot Output

- `backtest-labels` reads an existing `reports/daily/<YYYY-MM-DD>/scorecards/` folder.
- It writes `reports/backtests/<YYYY-MM-DD>/snapshot.md` and `snapshot.json`.
- Forward returns are calculated in trading days from each scorecard's `price_data_as_of` date.
- If the requested horizon extends beyond the latest available bar, that horizon remains `pending`.

## Backtest Aggregate Output

- `backtest-summary` reads one or more `snapshot.json` files from `reports/backtests/`.
- It writes `reports/backtests/aggregate/summary.md` and `summary.json`.
- The summary includes verdict-level and score-band-level average returns, excess returns, and alignment rates.

## Scoring Calibration Output

- The active scoring profile lives in `config/scoring.yaml`.
- `calibration-report` reads the aggregate summary and writes `reports/calibration/latest/report.md`, `report.json`, and `proposed_scoring.yaml`.
- `calibration-compare` rescoring a saved daily batch with the current and proposed profiles, then writes `comparison.md` and `comparison.json`.
- If completed backtest observations are below the minimum threshold, the calibration report keeps the current profile unchanged.

## Daily Refresh Output

- `daily-refresh` chains `daily-batch`, `backtest-labels`, `backtest-summary`, `calibration-report`, `calibration-compare`, and optional `telegram_notify`.
- It writes a run summary under `reports/automation/<YYYY-MM-DD>/summary.md` and `summary.json`.
- The command refreshes backtest snapshots for every dated daily batch folder currently present under `reports/daily/`.
- If Telegram env vars are not configured, the notification step is recorded as `skipped`.

## Scheduler

- macOS `launchd` files live under `config/launchd/`.
- The default LaunchAgent runs `scripts/run_daily_refresh.sh` every day at local time `08:30`.
- Install with `./scripts/install_launchd.sh` and remove with `./scripts/uninstall_launchd.sh`.
- If `~/Library/LaunchAgents` is not writable, the installer falls back to bootstrapping the project plist directly.
- Runtime logs go to `reports/logs/daily_refresh.stdout.log` and `reports/logs/daily_refresh.stderr.log`.
- `scripts/run_daily_refresh.sh` automatically loads `config/runtime.env` when present.
- The CLI also reads `config/runtime.env` when present, including `telegram-test`.
- Telegram alerts use `STOCK_REPORT_TELEGRAM_BOT_TOKEN` and `STOCK_REPORT_TELEGRAM_CHAT_ID`.

## Suggested Build Order

1. Normalize raw data into stable internal models
2. Expand feature calculators and scoring rules
3. Render Markdown and JSON reports
4. Add a scheduler for daily batch runs
5. Backfill tests around scoring, freshness checks, and report completeness

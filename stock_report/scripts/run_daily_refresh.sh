#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNTIME_ENV_PATH="${STOCK_REPORT_RUNTIME_ENV_FILE:-$REPO_ROOT/config/runtime.env}"
PYTHON_BIN="${STOCK_REPORT_PYTHON_BIN:-$REPO_ROOT/.venv/bin/python}"
WATCHLIST_PATH="${STOCK_REPORT_WATCHLIST:-$REPO_ROOT/config/watchlist.example.yaml}"
CURRENT_PROFILE_PATH="${STOCK_REPORT_CURRENT_PROFILE:-$REPO_ROOT/config/scoring.yaml}"
DAILY_OUTPUT_DIR="${STOCK_REPORT_DAILY_OUTPUT_DIR:-$REPO_ROOT/reports/daily}"
BACKTEST_OUTPUT_DIR="${STOCK_REPORT_BACKTEST_OUTPUT_DIR:-$REPO_ROOT/reports/backtests}"
AGGREGATE_OUTPUT_DIR="${STOCK_REPORT_AGGREGATE_OUTPUT_DIR:-$REPO_ROOT/reports/backtests/aggregate}"
CALIBRATION_OUTPUT_DIR="${STOCK_REPORT_CALIBRATION_OUTPUT_DIR:-$REPO_ROOT/reports/calibration/latest}"
AUTOMATION_OUTPUT_DIR="${STOCK_REPORT_AUTOMATION_OUTPUT_DIR:-$REPO_ROOT/reports/automation}"
HISTORY_RANGE="${STOCK_REPORT_HISTORY_RANGE:-1y}"
BACKTEST_HISTORY_RANGE="${STOCK_REPORT_BACKTEST_HISTORY_RANGE:-2y}"
NEWS_DAYS="${STOCK_REPORT_NEWS_DAYS:-7}"
BACKTEST_HORIZONS="${STOCK_REPORT_BACKTEST_HORIZONS:-5 20 60}"

if [[ -f "$RUNTIME_ENV_PATH" ]]; then
  set -a
  source "$RUNTIME_ENV_PATH"
  set +a
fi

mkdir -p \
  "$DAILY_OUTPUT_DIR" \
  "$BACKTEST_OUTPUT_DIR" \
  "$AGGREGATE_OUTPUT_DIR" \
  "$CALIBRATION_OUTPUT_DIR" \
  "$AUTOMATION_OUTPUT_DIR" \
  "$REPO_ROOT/reports/logs"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python executable not found: $PYTHON_BIN" >&2
  exit 1
fi

if [[ ! -f "$WATCHLIST_PATH" ]]; then
  echo "Watchlist file not found: $WATCHLIST_PATH" >&2
  exit 1
fi

if [[ ! -f "$CURRENT_PROFILE_PATH" ]]; then
  echo "Scoring profile file not found: $CURRENT_PROFILE_PATH" >&2
  exit 1
fi

BACKTEST_HORIZON_ARGS=(${=BACKTEST_HORIZONS})
SYMBOL_ARGS=()
if [[ -n "${STOCK_REPORT_SYMBOLS:-}" ]]; then
  SYMBOL_ARGS=(--symbols ${=STOCK_REPORT_SYMBOLS})
fi

BENCHMARK_ARGS=()
if [[ -n "${STOCK_REPORT_BENCHMARK:-}" ]]; then
  BENCHMARK_ARGS=(--benchmark "$STOCK_REPORT_BENCHMARK")
fi

DATE_ARGS=()
if [[ -n "${STOCK_REPORT_BATCH_DATE:-}" ]]; then
  DATE_ARGS=(--date "$STOCK_REPORT_BATCH_DATE")
fi

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] stock_report daily-refresh start"
cd "$REPO_ROOT"

PYTHONPATH="$REPO_ROOT/src" \
  "$PYTHON_BIN" -m stock_report.cli daily-refresh \
  --watchlist "$WATCHLIST_PATH" \
  "${DATE_ARGS[@]}" \
  "${BENCHMARK_ARGS[@]}" \
  --history-range "$HISTORY_RANGE" \
  --news-days "$NEWS_DAYS" \
  --daily-output-dir "$DAILY_OUTPUT_DIR" \
  --backtest-output-dir "$BACKTEST_OUTPUT_DIR" \
  --backtest-history-range "$BACKTEST_HISTORY_RANGE" \
  --horizons "${BACKTEST_HORIZON_ARGS[@]}" \
  --aggregate-output-dir "$AGGREGATE_OUTPUT_DIR" \
  --current-profile "$CURRENT_PROFILE_PATH" \
  --calibration-output-dir "$CALIBRATION_OUTPUT_DIR" \
  --automation-output-dir "$AUTOMATION_OUTPUT_DIR" \
  "${SYMBOL_ARGS[@]}"

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] stock_report daily-refresh finish"

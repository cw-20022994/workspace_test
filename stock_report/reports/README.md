# Report Outputs

- `daily/`: scheduled watchlist reports
- `ad_hoc/`: one-off symbol reports
- `backtests/`: per-date backtest snapshots and aggregate summary
- `calibration/`: scoring calibration report and before/after comparison
- `automation/`: daily refresh run summaries
- `logs/`: scheduler stdout/stderr logs
- `daily/<YYYY-MM-DD>/summary.md`: batch leaderboard and failures
- `daily/<YYYY-MM-DD>/markdown/`: per-symbol Markdown reports
- `daily/<YYYY-MM-DD>/scorecards/`: per-symbol JSON scorecards
- `daily/<YYYY-MM-DD>/profiles/`: raw fetched analysis profiles

Render both Markdown and JSON outputs so the project can support human review and downstream automation.

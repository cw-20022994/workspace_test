# Automation

## Goal

- Run `daily-refresh` automatically every day.
- Save logs in the repository so failures are easy to inspect.
- Keep the installation path simple for the current macOS workspace.

## Files

- `scripts/run_daily_refresh.sh`: wrapper that runs the full refresh chain
- `scripts/install_launchd.sh`: installs the LaunchAgent into `~/Library/LaunchAgents`
- `scripts/uninstall_launchd.sh`: unloads and removes the LaunchAgent
- `config/launchd/com.stockreport.daily-refresh.plist`: launchd job definition
- `config/runtime.env.example`: example runtime env file for scheduled runs and alerts

## Default Schedule

- Local time: `08:30`
- Assumption: this is late enough in Korea time to pick up the prior U.S. session cleanly.

## Environment Overrides

The wrapper script supports optional environment variables:

- `STOCK_REPORT_RUNTIME_ENV_FILE`
- `STOCK_REPORT_SYMBOLS`
- `STOCK_REPORT_BENCHMARK`
- `STOCK_REPORT_BATCH_DATE`
- `STOCK_REPORT_WATCHLIST`
- `STOCK_REPORT_CURRENT_PROFILE`
- `STOCK_REPORT_DAILY_OUTPUT_DIR`
- `STOCK_REPORT_BACKTEST_OUTPUT_DIR`
- `STOCK_REPORT_AGGREGATE_OUTPUT_DIR`
- `STOCK_REPORT_CALIBRATION_OUTPUT_DIR`
- `STOCK_REPORT_AUTOMATION_OUTPUT_DIR`
- `STOCK_REPORT_HISTORY_RANGE`
- `STOCK_REPORT_BACKTEST_HISTORY_RANGE`
- `STOCK_REPORT_NEWS_DAYS`
- `STOCK_REPORT_BACKTEST_HORIZONS`
- `STOCK_REPORT_TELEGRAM_BOT_TOKEN`
- `STOCK_REPORT_TELEGRAM_CHAT_ID`

The wrapper automatically loads `config/runtime.env` when present. The CLI also reads the same file, so `stock-report telegram-test` works without exporting the values manually.

Example:

```bash
cp config/runtime.env.example config/runtime.env
```

Telegram quick setup:

1. Create a bot with `@BotFather` and copy the bot token.
2. Send one message to the bot or to the target group where the bot is invited.
3. Run `curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates"` and find `message.chat.id`.
4. Put the values into `config/runtime.env`.
5. Run `stock-report telegram-test`.

## Install

```bash
chmod +x scripts/run_daily_refresh.sh scripts/install_launchd.sh scripts/uninstall_launchd.sh
./scripts/install_launchd.sh
```

- If `~/Library/LaunchAgents` is writable, the installer copies the plist there.
- If it is not writable, the installer bootstraps the plist directly from the repository path.

## Check

```bash
launchctl print gui/$(id -u)/com.stockreport.daily-refresh
tail -n 100 reports/logs/daily_refresh.stdout.log
tail -n 100 reports/logs/daily_refresh.stderr.log
stock-report telegram-test
```

## Remove

```bash
./scripts/uninstall_launchd.sh
```

## Notes

- If the repository path changes, update the absolute paths inside the plist file.
- If you want a different schedule, edit `StartCalendarInterval` in the plist and reinstall it.
- `daily-refresh` writes the Telegram step into `reports/automation/<YYYY-MM-DD>/summary.md` and `summary.json`.

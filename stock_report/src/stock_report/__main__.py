"""Allow `python -m stock_report` to work."""

from stock_report.cli import main


if __name__ == "__main__":
    raise SystemExit(main())

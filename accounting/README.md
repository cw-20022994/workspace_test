# Expense CSV Summarizer

This repository contains a small Python CLI that reads an expense CSV file and prints:

- total expenses and total income or refunds
- monthly expense totals
- top spending categories

## Quick start

```bash
python3 expense_summary.py sample_transactions.csv
```

## Supported columns

The script auto-detects common column names for:

- date
- amount
- category
- description

It recognizes both English and common Korean headers. When auto-detection is wrong or your CSV uses custom names, pass them explicitly:

```bash
python3 expense_summary.py my.csv \
  --date-column PostedAt \
  --amount-column ChargeAmount \
  --category-column Type \
  --description-column Merchant
```

## Common options

Filter to one month:

```bash
python3 expense_summary.py my.csv --month 2026-03
```

Use a custom date format:

```bash
python3 expense_summary.py my.csv --date-format %Y/%m/%d
```

Treat negative numbers as expenses:

```bash
python3 expense_summary.py my.csv --expenses-negative
```

Use a different delimiter or encoding:

```bash
python3 expense_summary.py my.csv --delimiter ';' --encoding cp949
```

## Notes

- The default assumption is that positive amounts are expenses.
- Rows with invalid dates or amounts are skipped and reported at the end.
- If no category column is found, the script groups those rows as `Uncategorized`.

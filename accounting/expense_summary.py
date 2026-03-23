#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path


HEADER_ALIASES = {
    "date": ["date", "transaction_date", "posted_at", "사용일", "거래일", "일자", "승인일"],
    "amount": ["amount", "price", "total", "sum", "사용금액", "금액", "결제금액", "출금액", "입금액"],
    "category": ["category", "type", "group", "카테고리", "분류", "업종", "항목"],
    "description": ["description", "memo", "merchant", "name", "가맹점", "내용", "메모", "상호"],
}

DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y.%m.%d",
    "%Y%m%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%Y.%m.%d %H:%M:%S",
    "%Y년 %m월 %d일",
    "%m/%d/%Y",
    "%d/%m/%Y",
)


@dataclass(frozen=True)
class Entry:
    date: datetime
    amount: Decimal
    category: str
    description: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarize expense CSV files by month and category."
    )
    parser.add_argument("csv_path", help="Path to the CSV file to summarize.")
    parser.add_argument(
        "--date-column",
        help="Column name for transaction dates. Auto-detected when omitted.",
    )
    parser.add_argument(
        "--amount-column",
        help="Column name for amounts. Auto-detected when omitted.",
    )
    parser.add_argument(
        "--category-column",
        help="Column name for categories. Defaults to Uncategorized when missing.",
    )
    parser.add_argument(
        "--description-column",
        help="Column name for merchant or memo text.",
    )
    parser.add_argument(
        "--date-format",
        help="Optional strptime format, for example %%Y-%%m-%%d.",
    )
    parser.add_argument(
        "--delimiter",
        default=",",
        help="CSV delimiter. Defaults to ','.",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8-sig",
        help="File encoding. Defaults to utf-8-sig.",
    )
    parser.add_argument(
        "--month",
        help="Filter to a specific month in YYYY-MM format.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of categories to show. Defaults to 10.",
    )
    parser.add_argument(
        "--expenses-negative",
        action="store_true",
        help="Treat negative amounts as expenses instead of refunds.",
    )
    return parser


def normalize_header(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", value.strip().lower())


def resolve_header(headers: list[str], requested: str | None, field: str) -> str | None:
    if requested:
        requested_header = find_matching_header(headers, requested)
        if requested_header is None:
            raise SystemExit(
                f"Column '{requested}' was not found. Available columns: {', '.join(headers)}"
            )
        return requested_header

    for alias in HEADER_ALIASES[field]:
        alias_match = find_matching_header(headers, alias)
        if alias_match is not None:
            return alias_match

    if field in {"category", "description"}:
        return None

    raise SystemExit(
        f"Could not auto-detect the {field} column. "
        f"Use --{field}-column. Available columns: {', '.join(headers)}"
    )


def find_matching_header(headers: list[str], target: str) -> str | None:
    normalized_target = normalize_header(target)
    for header in headers:
        if normalize_header(header) == normalized_target:
            return header
    return None


def parse_date(raw_value: str, date_format: str | None) -> datetime:
    value = raw_value.strip()
    if not value:
        raise ValueError("missing date")

    if date_format:
        try:
            return datetime.strptime(value, date_format)
        except ValueError as exc:
            raise ValueError(f"date '{value}' does not match format '{date_format}'") from exc

    for candidate in DATE_FORMATS:
        try:
            return datetime.strptime(value, candidate)
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"unsupported date '{value}'") from exc


def parse_amount(raw_value: str) -> Decimal:
    value = raw_value.strip()
    if not value:
        raise ValueError("missing amount")

    wrapped_negative = value.startswith("(") and value.endswith(")")
    if wrapped_negative:
        value = value[1:-1]

    value = value.replace(",", "")
    value = re.sub(r"[^\d.\-]", "", value)

    if not value or value in {"-", ".", "-."}:
        raise ValueError(f"unsupported amount '{raw_value}'")

    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"unsupported amount '{raw_value}'") from exc

    if wrapped_negative:
        return -abs(amount)
    return amount


def load_entries(args: argparse.Namespace) -> tuple[list[Entry], list[str]]:
    csv_path = Path(args.csv_path)
    if not csv_path.exists():
        raise SystemExit(f"CSV file was not found: {csv_path}")

    with csv_path.open("r", encoding=args.encoding, newline="") as handle:
        reader = csv.DictReader(handle, delimiter=args.delimiter)
        if not reader.fieldnames:
            raise SystemExit("CSV file has no header row.")

        headers = [header.strip() for header in reader.fieldnames if header]
        date_column = resolve_header(headers, args.date_column, "date")
        amount_column = resolve_header(headers, args.amount_column, "amount")
        category_column = resolve_header(headers, args.category_column, "category")
        description_column = resolve_header(headers, args.description_column, "description")

        entries: list[Entry] = []
        errors: list[str] = []

        for line_number, row in enumerate(reader, start=2):
            if is_blank_row(row):
                continue

            try:
                entry_date = parse_date(row.get(date_column, ""), args.date_format)
                amount = parse_amount(row.get(amount_column, ""))
            except ValueError as exc:
                errors.append(f"line {line_number}: {exc}")
                continue

            category = ""
            if category_column is not None:
                category = row.get(category_column, "").strip()

            description = ""
            if description_column is not None:
                description = row.get(description_column, "").strip()

            entries.append(
                Entry(
                    date=entry_date,
                    amount=amount,
                    category=category or "Uncategorized",
                    description=description,
                )
            )

    if not entries:
        error_text = "\n".join(errors[:5]) if errors else "No data rows were parsed."
        raise SystemExit(f"No valid rows were loaded.\n{error_text}")

    return entries, errors


def is_blank_row(row: dict[str, str | None]) -> bool:
    return all(not (value or "").strip() for value in row.values())


def summarize_entries(
    entries: list[Entry], month_filter: str | None, expenses_negative: bool
) -> dict[str, object]:
    selected_entries = entries
    if month_filter:
        validate_month_filter(month_filter)
        selected_entries = [
            entry for entry in entries if entry.date.strftime("%Y-%m") == month_filter
        ]

    monthly_expenses: dict[str, Decimal] = defaultdict(Decimal)
    category_expenses: dict[str, Decimal] = defaultdict(Decimal)

    total_expense = Decimal("0")
    total_income = Decimal("0")
    expense_rows = 0
    income_rows = 0

    for entry in selected_entries:
        amount = entry.amount
        is_expense = amount < 0 if expenses_negative else amount > 0
        amount_value = abs(amount)

        if is_expense and amount_value > 0:
            expense_rows += 1
            total_expense += amount_value
            monthly_expenses[entry.date.strftime("%Y-%m")] += amount_value
            category_expenses[entry.category] += amount_value
            continue

        if amount_value > 0:
            income_rows += 1
            total_income += amount_value

    return {
        "selected_entries": selected_entries,
        "monthly_expenses": monthly_expenses,
        "category_expenses": category_expenses,
        "total_expense": total_expense,
        "total_income": total_income,
        "expense_rows": expense_rows,
        "income_rows": income_rows,
    }


def validate_month_filter(month_filter: str) -> None:
    try:
        datetime.strptime(month_filter, "%Y-%m")
    except ValueError as exc:
        raise SystemExit("--month must use YYYY-MM format.") from exc


def format_amount(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):,.2f}"


def print_summary(
    csv_path: str, summary: dict[str, object], parse_errors: list[str], top_categories: int
) -> None:
    selected_entries = summary["selected_entries"]
    monthly_expenses = summary["monthly_expenses"]
    category_expenses = summary["category_expenses"]
    total_expense = summary["total_expense"]
    total_income = summary["total_income"]
    expense_rows = summary["expense_rows"]
    income_rows = summary["income_rows"]

    print(f"Source file: {csv_path}")
    print(f"Rows included: {len(selected_entries)}")
    print(f"Expense rows: {expense_rows}")
    print(f"Income/refund rows: {income_rows}")
    print(f"Total expenses: {format_amount(total_expense)}")
    print(f"Total income/refunds: {format_amount(total_income)}")

    print("\nMonthly expenses")
    if monthly_expenses:
        for month, value in sorted(monthly_expenses.items()):
            print(f"  {month:<7} {format_amount(value)}")
    else:
        print("  No expense rows matched the current filter.")

    print("\nTop categories")
    ranked_categories = sorted(
        category_expenses.items(),
        key=lambda item: (-item[1], item[0]),
    )[:top_categories]
    if ranked_categories:
        for category, value in ranked_categories:
            print(f"  {category:<20} {format_amount(value)}")
    else:
        print("  No categories to display.")

    if parse_errors:
        print(f"\nSkipped rows: {len(parse_errors)}")
        for error in parse_errors[:5]:
            print(f"  {error}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    entries, parse_errors = load_entries(args)
    summary = summarize_entries(entries, args.month, args.expenses_negative)
    print_summary(args.csv_path, summary, parse_errors, args.top)


if __name__ == "__main__":
    main()

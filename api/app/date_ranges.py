from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func


DateRangeKey = str


@dataclass(frozen=True)
class ResolvedDateRange:
    key: DateRangeKey
    start_date: date | None
    end_date: date | None


def resolve_date_range(
    range_key: str = 'month',
    from_value: str | None = None,
    to_value: str | None = None,
    *,
    today: date | None = None,
) -> ResolvedDateRange:
    current_day = today or datetime.now(timezone.utc).date()
    normalized = (range_key or 'month').strip().lower()

    if normalized == 'all':
        return ResolvedDateRange(key='all', start_date=None, end_date=None)
    if normalized == 'month':
        return ResolvedDateRange(key='month', start_date=current_day.replace(day=1), end_date=current_day)
    if normalized == 'last_month':
        current_month_start = current_day.replace(day=1)
        last_month_end = current_month_start - timedelta(days=1)
        return ResolvedDateRange(key='last_month', start_date=last_month_end.replace(day=1), end_date=last_month_end)
    if normalized == 'year':
        return ResolvedDateRange(key='year', start_date=current_day.replace(month=1, day=1), end_date=current_day)
    if normalized == 'custom':
        if not from_value or not to_value:
            raise ValueError("Für range=custom sind 'from' und 'to' erforderlich.")
        try:
            start_date = date.fromisoformat(from_value)
            end_date = date.fromisoformat(to_value)
        except ValueError as exc:
            raise ValueError("Ungültiges Datum. Erwartet wird YYYY-MM-DD.") from exc
        if end_date < start_date:
            raise ValueError("'to' darf nicht vor 'from' liegen.")
        return ResolvedDateRange(key='custom', start_date=start_date, end_date=end_date)

    raise ValueError("Ungültiger range-Wert. Erlaubt: month, last_month, year, all, custom.")


def apply_date_filter_to_datetime(stmt, column, date_range: ResolvedDateRange):
    if date_range.start_date is None or date_range.end_date is None:
        return stmt
    return stmt.where(
        func.date(column) >= date_range.start_date.isoformat(),
        func.date(column) <= date_range.end_date.isoformat(),
    )


def apply_date_filter_to_date(stmt, column, date_range: ResolvedDateRange):
    if date_range.start_date is None or date_range.end_date is None:
        return stmt
    return stmt.where(column >= date_range.start_date, column <= date_range.end_date)

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterator


def month_chunks(
    start: date, end: date
) -> Iterator[tuple[date, date]]:
    """Yield (chunk_start, chunk_end) pairs, one calendar month at a time."""
    cursor = start.replace(day=1)
    while cursor <= end:
        # Last day of this month
        if cursor.month == 12:
            next_month = cursor.replace(year=cursor.year + 1, month=1, day=1)
        else:
            next_month = cursor.replace(month=cursor.month + 1, day=1)

        chunk_end = min(next_month - timedelta(days=1), end)
        yield cursor, chunk_end
        cursor = next_month


def to_datetime(d: date | datetime) -> datetime:
    if isinstance(d, datetime):
        return d
    return datetime(d.year, d.month, d.day)


def history_start_date(months_back: int) -> date:
    today = date.today()
    year = today.year
    month = today.month - months_back

    while month <= 0:
        month += 12
        year -= 1

    return date(year, month, 1)

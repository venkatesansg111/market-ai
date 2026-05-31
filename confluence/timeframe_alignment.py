"""Timeframe alignment service for multi-timeframe analysis.

The central concern is **look-ahead bias prevention**: when processing an
entry-timeframe bar, we must only use indicator data from higher timeframes
that was *available* (i.e., fully closed) at the time that entry bar closed.

Alignment formula
-----------------
Given an entry bar that *opens* at ``entry_time`` and closes at::

    close_time = entry_time + timedelta(minutes=entry_duration)

the last completed target-timeframe bar has ``candle_time``::

    aligned_time = floor(close_time - target_duration, target_duration)

where ``floor(t, d)`` rounds ``t`` *down* to the nearest multiple of ``d``
minutes within the same calendar day.

This formula holds for all intraday-to-intraday and intraday-to-daily pairs.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Sequence

from indicators.indicator_models import IndicatorRecord


# ---------------------------------------------------------------------------
# Supported timeframes
# ---------------------------------------------------------------------------

_DURATION_MINUTES: dict[str, int] = {
    "1min":  1,
    "5min":  5,
    "15min": 15,
    "30min": 30,
    "1hour": 60,
    "4hour": 240,
    "1day":  1440,
}


class TimeframeAlignmentService:
    """Aligns candle/indicator data across multiple timeframes without look-ahead bias.

    Design goals:
    - Stateless: no internal mutable state; safe to share across threads.
    - Pure: no database access; all data is passed in by the caller.
    - Deterministic: same inputs always produce the same aligned times.

    Example::

        svc = TimeframeAlignmentService()
        aligned = svc.align(
            entry_time=datetime(2024, 1, 15, 10, 25),
            entry_timeframe="5min",
            all_indicators={
                "1day":  daily_records,   # list sorted asc by candle_time
                "15min": min15_records,
                "5min":  min5_records,
            },
        )
        # aligned["1day"]  → last completed 1-day indicator before 10:30
        # aligned["15min"] → last completed 15-min indicator before 10:30
        # aligned["5min"]  → the 10:25 5-min record itself
    """

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def get_duration_minutes(self, timeframe: str) -> int:
        """Return the candle duration in minutes for *timeframe*.

        Raises:
            KeyError: If *timeframe* is not in the supported set.
        """
        if timeframe not in _DURATION_MINUTES:
            raise KeyError(
                f"Unknown timeframe '{timeframe}'. "
                f"Supported: {list(_DURATION_MINUTES)}"
            )
        return _DURATION_MINUTES[timeframe]

    def get_aligned_candle_time(
        self,
        entry_time: datetime,
        entry_timeframe: str,
        target_timeframe: str,
    ) -> datetime:
        """Return the ``candle_time`` of the last completed target-timeframe bar
        that is available at the close of the entry bar — without look-ahead.

        The entry bar ``[entry_time, entry_time + entry_duration)`` *closes* at
        ``close_time = entry_time + entry_duration``.

        The last target bar whose close ≤ close_time has::

            candle_time = floor(close_time - target_duration, target_duration)

        This prevents look-ahead because the aligned bar's close is guaranteed
        to be ≤ ``close_time``.

        Args:
            entry_time:       Open time of the entry bar being processed.
            entry_timeframe:  Timeframe string for the entry bar.
            target_timeframe: Timeframe string for the bar we want to align to.

        Returns:
            ``datetime`` representing the ``candle_time`` of the aligned bar.

        Raises:
            KeyError: If either timeframe is not supported.

        Examples:
            >>> svc = TimeframeAlignmentService()
            >>> svc.get_aligned_candle_time(
            ...     datetime(2024, 1, 15, 10, 25), "5min", "15min"
            ... )
            datetime.datetime(2024, 1, 15, 10, 15, 0)

            >>> svc.get_aligned_candle_time(
            ...     datetime(2024, 1, 15, 10, 25), "5min", "1day"
            ... )
            datetime.datetime(2024, 1, 14, 0, 0, 0)
        """
        entry_duration = self.get_duration_minutes(entry_timeframe)
        target_duration = self.get_duration_minutes(target_timeframe)

        close_time = entry_time + timedelta(minutes=entry_duration)

        # Shift back by one full target period to find the most recent *closed* bar.
        # floor() then snaps to the exact period boundary.
        anchor = close_time - timedelta(minutes=target_duration)
        return self._floor_to_period(anchor, target_duration)

    def align(
        self,
        entry_time: datetime,
        entry_timeframe: str,
        all_indicators: dict[str, Sequence[IndicatorRecord]],
    ) -> dict[str, Optional[IndicatorRecord]]:
        """Return the most-recent valid ``IndicatorRecord`` per timeframe,
        aligned to ``entry_time`` without look-ahead bias.

        For the **entry timeframe** itself, the record at exactly
        ``entry_time`` is returned (or the nearest earlier record if an
        exact match is absent — this handles sparse data gracefully).

        For **other timeframes**, the record whose ``candle_time`` is at or
        before the computed aligned time is returned.  ``None`` is returned
        when no such record exists.

        Args:
            entry_time:       Open time of the entry bar being processed.
            entry_timeframe:  Timeframe of the entry bar.
            all_indicators:   Mapping of timeframe → records, where each
                              record list is sorted ascending by ``candle_time``.

        Returns:
            Dict mapping timeframe → ``IndicatorRecord | None``.
        """
        result: dict[str, Optional[IndicatorRecord]] = {}

        for tf, records in all_indicators.items():
            if not records:
                result[tf] = None
                continue

            if tf == entry_timeframe:
                # Exact entry bar, or nearest earlier record.
                matched = self._find_at_or_before(records, entry_time)
            else:
                aligned_time = self.get_aligned_candle_time(entry_time, entry_timeframe, tf)
                matched = self._find_at_or_before(records, aligned_time)

            result[tf] = matched

        return result

    def is_same_session(self, time1: datetime, time2: datetime) -> bool:
        """Return ``True`` when both datetimes fall on the same calendar date.

        Useful for intraday session-boundary checks (e.g. VWAP resets).
        """
        return time1.date() == time2.date()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _floor_to_period(dt: datetime, period_minutes: int) -> datetime:
        """Round ``dt`` down to the nearest ``period_minutes`` boundary
        within the same calendar day (preserves the date component).

        For ``period_minutes >= 1440`` (daily), the result is always midnight
        of the same date as *dt*.
        """
        total_minutes = dt.hour * 60 + dt.minute
        floored_minutes = (total_minutes // period_minutes) * period_minutes
        return dt.replace(
            hour=floored_minutes // 60,
            minute=floored_minutes % 60,
            second=0,
            microsecond=0,
        )

    @staticmethod
    def _find_at_or_before(
        records: Sequence[IndicatorRecord],
        cutoff: datetime,
    ) -> Optional[IndicatorRecord]:
        """Return the most recent record with ``candle_time <= cutoff``.

        Assumes *records* is sorted ascending by ``candle_time``.  Iterates
        in reverse for O(1) typical-case access (most recent bar is last).
        """
        for rec in reversed(records):
            if rec.candle_time <= cutoff:
                return rec
        return None

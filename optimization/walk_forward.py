"""WalkForwardOptimizer — generate rolling and expanding train/test window splits."""
from __future__ import annotations

import calendar
from datetime import datetime, timedelta
from typing import Literal

from optimization.optimization_models import OptimizationWindow


def _add_months(dt: datetime, months: int) -> datetime:
    """Add *months* months to *dt*, clamping day to valid month-end."""
    total_month = dt.month - 1 + months
    year = dt.year + total_month // 12
    month = total_month % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return datetime(year, month, day, dt.hour, dt.minute, dt.second, dt.microsecond)


class WalkForwardOptimizer:
    """Generates train/test window splits for walk-forward analysis.

    Rolling example (train_months=6, test_months=3)::

        Window 0: train 2024-01 → 2024-06, test 2024-07 → 2024-09
        Window 1: train 2024-04 → 2024-09, test 2024-10 → 2024-12

    Expanding example (train_months=6, test_months=3)::

        Window 0: train 2024-01 → 2024-06, test 2024-07 → 2024-09
        Window 1: train 2024-01 → 2024-09, test 2024-10 → 2024-12
    """

    def generate_windows(
        self,
        start_date: datetime,
        end_date: datetime,
        train_months: int = 12,
        test_months: int = 3,
        window_type: Literal["rolling", "expanding"] = "rolling",
    ) -> list[OptimizationWindow]:
        """Generate train/test windows for walk-forward analysis.

        Args:
            start_date:   First date of the overall analysis period.
            end_date:     Last date of the overall analysis period.
            train_months: Number of months in each training window.
            test_months:  Number of months in each testing window.
            window_type:  "rolling" (fixed-length train) or "expanding" (growing train).

        Returns:
            List of :class:`OptimizationWindow` instances in chronological order.

        Raises:
            ValueError: if *train_months* < 1, *test_months* < 1, or *window_type* is unknown.
        """
        if train_months < 1:
            raise ValueError("train_months must be >= 1")
        if test_months < 1:
            raise ValueError("test_months must be >= 1")
        if start_date >= end_date:
            raise ValueError("start_date must be before end_date")

        if window_type == "rolling":
            return self._rolling(start_date, end_date, train_months, test_months)
        elif window_type == "expanding":
            return self._expanding(start_date, end_date, train_months, test_months)
        else:
            raise ValueError(
                f"Unknown window_type '{window_type}'. Use 'rolling' or 'expanding'."
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _rolling(
        start_date: datetime,
        end_date: datetime,
        train_months: int,
        test_months: int,
    ) -> list[OptimizationWindow]:
        windows: list[OptimizationWindow] = []
        idx = 0
        train_start = start_date

        while True:
            train_end = _add_months(train_start, train_months) - timedelta(days=1)
            test_start = train_end + timedelta(days=1)
            test_end = _add_months(test_start, test_months) - timedelta(days=1)

            if test_end > end_date:
                break

            windows.append(
                OptimizationWindow(
                    train_start=train_start,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                    window_type="rolling",
                    window_index=idx,
                )
            )
            train_start = _add_months(train_start, test_months)
            idx += 1

        return windows

    @staticmethod
    def _expanding(
        start_date: datetime,
        end_date: datetime,
        train_months: int,
        test_months: int,
    ) -> list[OptimizationWindow]:
        windows: list[OptimizationWindow] = []
        idx = 0
        anchor = start_date
        train_end = _add_months(anchor, train_months) - timedelta(days=1)

        while True:
            test_start = train_end + timedelta(days=1)
            test_end = _add_months(test_start, test_months) - timedelta(days=1)

            if test_end > end_date:
                break

            windows.append(
                OptimizationWindow(
                    train_start=anchor,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                    window_type="expanding",
                    window_index=idx,
                )
            )
            train_end = test_end
            idx += 1

        return windows

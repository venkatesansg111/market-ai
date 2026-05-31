from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from confluence.timeframe_alignment import TimeframeAlignmentService
from indicators.indicator_models import IndicatorRecord


def _make_record(tf: str, candle_time: datetime) -> IndicatorRecord:
    return IndicatorRecord(
        instrument="TEST",
        candle_time=candle_time,
        timeframe=tf,
    )


class TestGetDurationMinutes:
    def test_1min(self):
        svc = TimeframeAlignmentService()
        assert svc.get_duration_minutes("1min") == 1

    def test_5min(self):
        assert TimeframeAlignmentService().get_duration_minutes("5min") == 5

    def test_15min(self):
        assert TimeframeAlignmentService().get_duration_minutes("15min") == 15

    def test_30min(self):
        assert TimeframeAlignmentService().get_duration_minutes("30min") == 30

    def test_1hour(self):
        assert TimeframeAlignmentService().get_duration_minutes("1hour") == 60

    def test_4hour(self):
        assert TimeframeAlignmentService().get_duration_minutes("4hour") == 240

    def test_1day(self):
        assert TimeframeAlignmentService().get_duration_minutes("1day") == 1440

    def test_unknown_raises_key_error(self):
        with pytest.raises(KeyError, match="Unknown timeframe"):
            TimeframeAlignmentService().get_duration_minutes("3min")


class TestGetAlignedCandleTime:
    """Verify the no-look-ahead alignment formula for representative cases."""

    def setup_method(self):
        self.svc = TimeframeAlignmentService()

    def test_5min_to_15min_within_period(self):
        # Entry bar at 10:25 5min closes at 10:30
        # anchor = 10:30 - 15min = 10:15; floor(10:15, 15) = 10:15
        result = self.svc.get_aligned_candle_time(
            datetime(2024, 1, 15, 10, 25), "5min", "15min"
        )
        assert result == datetime(2024, 1, 15, 10, 15)

    def test_5min_to_1day(self):
        # Entry bar at 10:25 5min closes at 10:30
        # anchor = 10:30 - 1440min = 2024-01-14 10:30; floor(prev_day 10:30, 1440) = 2024-01-14 00:00
        result = self.svc.get_aligned_candle_time(
            datetime(2024, 1, 15, 10, 25), "5min", "1day"
        )
        assert result == datetime(2024, 1, 14, 0, 0, 0)

    def test_1min_to_5min(self):
        # Entry at 10:04 1min closes at 10:05
        # anchor = 10:05 - 5 = 10:00; floor(10:00, 5) = 10:00
        result = self.svc.get_aligned_candle_time(
            datetime(2024, 1, 15, 10, 4), "1min", "5min"
        )
        assert result == datetime(2024, 1, 15, 10, 0)

    def test_1min_to_15min(self):
        # Entry at 10:14 1min closes at 10:15
        # anchor = 10:15 - 15 = 10:00; floor(10:00, 15) = 10:00
        result = self.svc.get_aligned_candle_time(
            datetime(2024, 1, 15, 10, 14), "1min", "15min"
        )
        assert result == datetime(2024, 1, 15, 10, 0)

    def test_15min_to_1hour(self):
        # Entry at 10:15 15min closes at 10:30
        # anchor = 10:30 - 60 = 09:30; floor(09:30, 60) = 09:00
        result = self.svc.get_aligned_candle_time(
            datetime(2024, 1, 15, 10, 15), "15min", "1hour"
        )
        assert result == datetime(2024, 1, 15, 9, 0)

    def test_no_look_ahead_entry_time_same_as_target(self):
        # A 5min bar at 10:25 must NOT use the 10:25 15min bar (not yet closed).
        # The last fully closed 15min bar is at 10:15, not 10:30.
        result = self.svc.get_aligned_candle_time(
            datetime(2024, 1, 15, 10, 25), "5min", "15min"
        )
        assert result < datetime(2024, 1, 15, 10, 30)

    def test_unknown_entry_tf_raises(self):
        with pytest.raises(KeyError):
            self.svc.get_aligned_candle_time(
                datetime(2024, 1, 15, 10, 0), "3min", "15min"
            )

    def test_unknown_target_tf_raises(self):
        with pytest.raises(KeyError):
            self.svc.get_aligned_candle_time(
                datetime(2024, 1, 15, 10, 0), "5min", "2hour"
            )


class TestAlign:
    """Verify align() returns the right records for each timeframe."""

    def setup_method(self):
        self.svc = TimeframeAlignmentService()

    def _records(self, tf: str, times: list[datetime]) -> list[IndicatorRecord]:
        return [_make_record(tf, t) for t in times]

    def test_entry_tf_returns_exact_match(self):
        entry_time = datetime(2024, 1, 15, 10, 25)
        records_5min = self._records(
            "5min",
            [
                datetime(2024, 1, 15, 10, 15),
                datetime(2024, 1, 15, 10, 20),
                datetime(2024, 1, 15, 10, 25),
            ],
        )
        result = self.svc.align(entry_time, "5min", {"5min": records_5min})
        assert result["5min"].candle_time == entry_time

    def test_entry_tf_returns_nearest_earlier_when_no_exact(self):
        entry_time = datetime(2024, 1, 15, 10, 25)
        records = self._records("5min", [datetime(2024, 1, 15, 10, 20)])
        result = self.svc.align(entry_time, "5min", {"5min": records})
        assert result["5min"].candle_time == datetime(2024, 1, 15, 10, 20)

    def test_higher_tf_picks_last_closed_bar(self):
        entry_time = datetime(2024, 1, 15, 10, 25)
        # 15min bars at 10:00 and 10:15; aligned time for 5min→15min at 10:25 is 10:15
        records_15min = self._records(
            "15min",
            [
                datetime(2024, 1, 15, 10, 0),
                datetime(2024, 1, 15, 10, 15),
                datetime(2024, 1, 15, 10, 30),  # not yet closed — must NOT be used
            ],
        )
        result = self.svc.align(entry_time, "5min", {"15min": records_15min})
        assert result["15min"].candle_time == datetime(2024, 1, 15, 10, 15)

    def test_empty_list_returns_none(self):
        result = self.svc.align(
            datetime(2024, 1, 15, 10, 25), "5min", {"15min": []}
        )
        assert result["15min"] is None

    def test_all_records_after_entry_returns_none(self):
        records = self._records("15min", [datetime(2024, 1, 15, 11, 0)])
        result = self.svc.align(
            datetime(2024, 1, 15, 10, 0), "5min", {"15min": records}
        )
        assert result["15min"] is None

    def test_multi_tf_align_returns_all_keys(self):
        entry_time = datetime(2024, 1, 15, 10, 25)
        all_indicators = {
            "1day": self._records("1day", [datetime(2024, 1, 14, 0, 0)]),
            "15min": self._records("15min", [datetime(2024, 1, 15, 10, 15)]),
            "5min": self._records("5min", [datetime(2024, 1, 15, 10, 25)]),
        }
        result = self.svc.align(entry_time, "5min", all_indicators)
        assert set(result.keys()) == {"1day", "15min", "5min"}
        assert result["5min"].candle_time == entry_time
        assert result["15min"].candle_time == datetime(2024, 1, 15, 10, 15)
        assert result["1day"].candle_time == datetime(2024, 1, 14, 0, 0)

    def test_align_uses_most_recent_at_or_before_cutoff(self):
        entry_time = datetime(2024, 1, 15, 10, 25)
        records_15min = self._records(
            "15min",
            [
                datetime(2024, 1, 15, 9, 45),
                datetime(2024, 1, 15, 10, 0),
                datetime(2024, 1, 15, 10, 15),
            ],
        )
        result = self.svc.align(entry_time, "5min", {"15min": records_15min})
        assert result["15min"].candle_time == datetime(2024, 1, 15, 10, 15)


class TestIsSameSession:
    def test_same_day_returns_true(self):
        svc = TimeframeAlignmentService()
        t1 = datetime(2024, 1, 15, 9, 15)
        t2 = datetime(2024, 1, 15, 15, 30)
        assert svc.is_same_session(t1, t2) is True

    def test_different_day_returns_false(self):
        svc = TimeframeAlignmentService()
        t1 = datetime(2024, 1, 15, 9, 15)
        t2 = datetime(2024, 1, 16, 9, 15)
        assert svc.is_same_session(t1, t2) is False

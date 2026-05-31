"""Unit tests for WalkForwardOptimizer."""
from datetime import datetime, timedelta

import pytest

from optimization.walk_forward import WalkForwardOptimizer, _add_months


class TestAddMonths:
    def test_basic(self):
        assert _add_months(datetime(2022, 1, 1), 12) == datetime(2023, 1, 1)

    def test_month_end_clamped(self):
        result = _add_months(datetime(2022, 1, 31), 1)
        assert result == datetime(2022, 2, 28)

    def test_negative_not_used_but_zero(self):
        assert _add_months(datetime(2022, 3, 15), 0) == datetime(2022, 3, 15)


class TestGenerateWindowsRolling:
    def setup_method(self):
        self.optimizer = WalkForwardOptimizer()
        self.start = datetime(2022, 1, 1)
        self.end = datetime(2024, 6, 30)

    def test_produces_windows(self):
        windows = self.optimizer.generate_windows(self.start, self.end, 12, 3, "rolling")
        assert len(windows) > 0

    def test_window_type_set(self):
        windows = self.optimizer.generate_windows(self.start, self.end, 12, 3, "rolling")
        for w in windows:
            assert w.window_type == "rolling"

    def test_test_start_is_day_after_train_end(self):
        windows = self.optimizer.generate_windows(self.start, self.end, 12, 3, "rolling")
        for w in windows:
            assert w.test_start == w.train_end + timedelta(days=1)

    def test_train_period_spans_12_months(self):
        windows = self.optimizer.generate_windows(self.start, self.end, 12, 3, "rolling")
        w = windows[0]
        expected_train_end = _add_months(w.train_start, 12) - timedelta(days=1)
        assert w.train_end == expected_train_end

    def test_rolling_train_start_advances_by_test_months(self):
        windows = self.optimizer.generate_windows(self.start, self.end, 12, 3, "rolling")
        if len(windows) >= 2:
            expected = _add_months(windows[0].train_start, 3)
            assert windows[1].train_start == expected

    def test_window_indices_sequential_from_zero(self):
        windows = self.optimizer.generate_windows(self.start, self.end, 12, 3, "rolling")
        for i, w in enumerate(windows):
            assert w.window_index == i

    def test_test_end_does_not_exceed_overall_end(self):
        windows = self.optimizer.generate_windows(self.start, self.end, 12, 3, "rolling")
        for w in windows:
            assert w.test_end <= self.end


class TestGenerateWindowsExpanding:
    def setup_method(self):
        self.optimizer = WalkForwardOptimizer()
        self.start = datetime(2022, 1, 1)
        self.end = datetime(2024, 6, 30)

    def test_produces_windows(self):
        windows = self.optimizer.generate_windows(self.start, self.end, 12, 3, "expanding")
        assert len(windows) > 0

    def test_window_type_set(self):
        windows = self.optimizer.generate_windows(self.start, self.end, 12, 3, "expanding")
        for w in windows:
            assert w.window_type == "expanding"

    def test_expanding_train_start_fixed(self):
        windows = self.optimizer.generate_windows(self.start, self.end, 12, 3, "expanding")
        if len(windows) >= 2:
            assert windows[0].train_start == windows[1].train_start == self.start

    def test_expanding_train_end_grows(self):
        windows = self.optimizer.generate_windows(self.start, self.end, 12, 3, "expanding")
        if len(windows) >= 2:
            assert windows[1].train_end > windows[0].train_end

    def test_expanding_second_train_end_equals_first_test_end(self):
        windows = self.optimizer.generate_windows(self.start, self.end, 12, 3, "expanding")
        if len(windows) >= 2:
            assert windows[1].train_end == windows[0].test_end


class TestGenerateWindowsEdgeCases:
    def setup_method(self):
        self.optimizer = WalkForwardOptimizer()

    def test_date_range_too_short_returns_empty(self):
        start = datetime(2023, 1, 1)
        end = datetime(2023, 6, 1)
        windows = self.optimizer.generate_windows(start, end, 12, 3, "rolling")
        assert windows == []

    def test_invalid_window_type_raises(self):
        start = datetime(2022, 1, 1)
        end = datetime(2024, 1, 1)
        with pytest.raises(ValueError):
            self.optimizer.generate_windows(start, end, 12, 3, "invalid_type")

    def test_train_months_zero_raises(self):
        start = datetime(2022, 1, 1)
        end = datetime(2024, 1, 1)
        with pytest.raises(ValueError):
            self.optimizer.generate_windows(start, end, 0, 3, "rolling")

    def test_test_months_zero_raises(self):
        start = datetime(2022, 1, 1)
        end = datetime(2024, 1, 1)
        with pytest.raises(ValueError):
            self.optimizer.generate_windows(start, end, 12, 0, "rolling")

    def test_start_equals_end_raises(self):
        dt = datetime(2023, 1, 1)
        with pytest.raises(ValueError):
            self.optimizer.generate_windows(dt, dt, 12, 3, "rolling")

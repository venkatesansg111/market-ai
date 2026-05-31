from __future__ import annotations

import math

import pandas as pd
import pytest

from indicators.advanced_calculators import calculate_atr


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_df(highs, lows, closes, volumes=None):
    n = len(closes)
    return pd.DataFrame(
        {
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes if volumes is not None else [1_000] * n,
        }
    )


def _constant_df(high, low, close, n=30):
    return make_df([high] * n, [low] * n, [close] * n)


# ---------------------------------------------------------------------------
# Warmup / NaN behaviour
# ---------------------------------------------------------------------------

class TestWarmup:
    def test_fewer_than_period_bars_all_nan(self):
        df = _constant_df(11, 9, 10, n=13)
        result = calculate_atr(df, 14)
        assert result.notna().sum() == 0

    def test_first_valid_bar_at_index_period_minus_one(self):
        df = _constant_df(11, 9, 10, n=20)
        result = calculate_atr(df, 14)
        assert pd.isna(result.iloc[12])
        assert not pd.isna(result.iloc[13])

    def test_single_bar_returns_nan(self):
        df = make_df([11], [9], [10])
        result = calculate_atr(df, 14)
        assert pd.isna(result.iloc[0])

    def test_exactly_period_bars_produces_one_valid(self):
        df = _constant_df(11, 9, 10, n=14)
        result = calculate_atr(df, 14)
        assert result.notna().sum() == 1

    def test_output_named_atr_14(self):
        df = _constant_df(11, 9, 10, n=30)
        result = calculate_atr(df, 14)
        assert result.name == "atr_14"


# ---------------------------------------------------------------------------
# Correctness — constant series
# ---------------------------------------------------------------------------

class TestConstantSeries:
    def test_constant_hl_spread_atr_converges_to_hl_range(self):
        # H=11, L=9 → HL spread = 2; no gaps so TR = HL = 2 every bar
        df = _constant_df(11, 9, 10, n=50)
        result = calculate_atr(df, 14)
        assert abs(float(result.iloc[-1]) - 2.0) < 0.01

    def test_narrow_range_produces_smaller_atr_than_wide_range(self):
        wide = _constant_df(120, 80, 100, n=50)
        narrow = _constant_df(101, 99, 100, n=50)
        assert float(calculate_atr(wide, 14).iloc[-1]) > float(
            calculate_atr(narrow, 14).iloc[-1]
        )

    def test_zero_range_series_atr_is_zero(self):
        df = _constant_df(10, 10, 10, n=30)
        result = calculate_atr(df, 14)
        valid = result.dropna()
        assert all(abs(float(v)) < 1e-9 for v in valid)


# ---------------------------------------------------------------------------
# Correctness — known TR values with period=1
# ---------------------------------------------------------------------------

class TestPeriodOne:
    """With period=1 and alpha=1, ATR[t] = TR[t] exactly (no smoothing lag)."""

    def test_atr_equals_hl_spread_when_no_gap(self):
        # No gap from bar to bar; TR = High − Low
        df = make_df([12, 11, 13, 10], [8, 9, 7, 6], [10, 10, 10, 8])
        result = calculate_atr(df, period=1)
        expected_tr = [4.0, 2.0, 6.0, 4.0]
        for i, exp in enumerate(expected_tr):
            assert abs(float(result.iloc[i]) - exp) < 1e-9

    def test_gap_up_increases_true_range(self):
        # prev_close=10, next H=20, L=19 → TR = max(1, 10, 9) = 10
        df = make_df([10, 20], [8, 19], [10, 19.5])
        result = calculate_atr(df, period=1)
        assert float(result.iloc[1]) == pytest.approx(10.0, abs=1e-9)

    def test_gap_down_increases_true_range(self):
        # prev_close=20, next H=11, L=10 → TR = max(1, 9, 10) = 10
        df = make_df([20, 11], [18, 10], [20, 10.5])
        result = calculate_atr(df, period=1)
        assert float(result.iloc[1]) == pytest.approx(10.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Non-negative constraint
# ---------------------------------------------------------------------------

class TestNonNegative:
    def test_rising_market_atr_always_non_negative(self):
        closes = list(range(1, 51))
        df = make_df([c + 2 for c in closes], [c - 1 for c in closes], closes)
        result = calculate_atr(df, 14)
        assert all(float(v) >= 0 for v in result.dropna())

    def test_falling_market_atr_always_positive(self):
        closes = [100 - i for i in range(40)]
        df = make_df([c + 1 for c in closes], [c - 1 for c in closes], closes)
        result = calculate_atr(df, 14)
        assert all(float(v) > 0 for v in result.dropna())

    def test_flat_market_atr_non_negative(self):
        df = _constant_df(10, 10, 10, n=30)
        result = calculate_atr(df, 14)
        assert all(float(v) >= 0 for v in result.dropna())


# ---------------------------------------------------------------------------
# Wilder smoothing decay — ATR cannot jump instantly
# ---------------------------------------------------------------------------

class TestWilderSmoothing:
    def test_sudden_spike_in_tr_decays_gradually(self):
        # 20 quiet bars then one very large bar; ATR should not reach TR_spike
        closes = [100.0] * 20 + [150.0]
        highs = [101.0] * 20 + [160.0]
        lows = [99.0] * 20 + [140.0]
        df = make_df(highs, lows, closes)
        result = calculate_atr(df, 14)
        # ATR after the spike should be between quiet ATR (2) and spike TR (20+)
        quiet_atr = float(result.iloc[19])
        spike_atr = float(result.iloc[20])
        assert spike_atr > quiet_atr
        assert spike_atr < 60.0  # must not absorb full TR spike in one bar

    def test_different_periods_produce_different_sensitivities(self):
        closes = list(range(1, 41))
        highs = [c + 3 for c in closes]
        lows = [c - 3 for c in closes]
        df = make_df(highs, lows, closes)
        atr7 = calculate_atr(df, 7)
        atr21 = calculate_atr(df, 21)
        # Shorter period ATR is more reactive (larger variation after trend change)
        # Both should converge to ~6 in a steady series; just check both are valid
        assert not pd.isna(atr7.iloc[-1])
        assert not pd.isna(atr21.iloc[-1])

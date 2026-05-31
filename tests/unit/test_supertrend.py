from __future__ import annotations

import math

import pandas as pd
import pytest

from indicators.advanced_calculators import calculate_supertrend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_df(highs, lows, closes):
    return pd.DataFrame({"high": highs, "low": lows, "close": closes})


def _trend_df(direction: str, n: int = 30, start: float = 100.0, step: float = 1.0):
    """Clean trending DataFrame with tight intrabar range."""
    prices = (
        [start + i * step for i in range(n)]
        if direction == "up"
        else [start - i * step for i in range(n)]
    )
    highs = [p + 0.5 for p in prices]
    lows = [p - 0.5 for p in prices]
    return make_df(highs, lows, prices)


def _flat_df(price: float = 100.0, n: int = 30):
    return make_df([price] * n, [price] * n, [price] * n)


# ---------------------------------------------------------------------------
# Warmup / NaN behaviour
# ---------------------------------------------------------------------------

class TestWarmup:
    def test_bars_before_atr_warmup_are_nan(self):
        df = _trend_df("up", n=20, step=2.0)
        st, direction = calculate_supertrend(df, period=10)
        # First 9 bars should be NaN (ATR period=10, min_periods=10 → 9 NaN)
        for i in range(9):
            assert math.isnan(float(st.iloc[i])), f"Bar {i} should be NaN"

    def test_first_valid_bar_at_period_index(self):
        df = _trend_df("up", n=30, step=2.0)
        st, direction = calculate_supertrend(df, period=10)
        assert math.isnan(float(st.iloc[8]))
        assert not math.isnan(float(st.iloc[9]))

    def test_direction_nan_during_warmup(self):
        df = _trend_df("up", n=30, step=2.0)
        _, direction = calculate_supertrend(df, period=10)
        for i in range(9):
            assert math.isnan(float(direction.iloc[i])), f"Direction bar {i} should be NaN"

    def test_insufficient_bars_all_nan(self):
        df = _trend_df("up", n=5, step=1.0)
        st, direction = calculate_supertrend(df, period=10)
        assert st.notna().sum() == 0
        assert direction.notna().sum() == 0

    def test_output_series_named_correctly(self):
        df = _trend_df("up", n=30, step=1.0)
        st, direction = calculate_supertrend(df, period=10)
        assert st.name == "supertrend"
        assert direction.name == "supertrend_direction"

    def test_output_same_length_as_input(self):
        df = _trend_df("up", n=40, step=1.0)
        st, direction = calculate_supertrend(df, period=10)
        assert len(st) == len(direction) == 40


# ---------------------------------------------------------------------------
# Direction values: only 1 or -1 for valid bars
# ---------------------------------------------------------------------------

class TestDirectionValues:
    def test_direction_is_1_or_minus1_for_valid_bars(self):
        df = _trend_df("up", n=50, step=1.0)
        _, direction = calculate_supertrend(df, period=10)
        for v in direction.dropna():
            assert float(v) in (1.0, -1.0), f"Direction must be 1 or -1, got {v}"

    def test_uptrend_direction_is_bullish(self):
        # Strong, clean uptrend should establish bullish direction
        df = _trend_df("up", n=60, step=3.0)
        _, direction = calculate_supertrend(df, period=10, multiplier=3.0)
        # Last bar of a strong uptrend should be bullish
        last_valid = direction.dropna().iloc[-1]
        assert float(last_valid) == 1.0

    def test_downtrend_direction_is_bearish(self):
        # Strong, clean downtrend should establish bearish direction
        df = _trend_df("down", n=60, step=3.0)
        _, direction = calculate_supertrend(df, period=10, multiplier=3.0)
        last_valid = direction.dropna().iloc[-1]
        assert float(last_valid) == -1.0


# ---------------------------------------------------------------------------
# Supertrend value properties
# ---------------------------------------------------------------------------

class TestSupertrendValues:
    def test_supertrend_positive_for_positive_prices(self):
        df = _trend_df("up", n=40, step=1.0)
        st, _ = calculate_supertrend(df, period=10)
        assert all(float(v) > 0 for v in st.dropna())

    def test_bullish_supertrend_below_close(self):
        # When direction=1 (bullish), Supertrend is the lower band, so it should
        # be below the closing price for a strong uptrend
        df = _trend_df("up", n=60, step=2.0)
        st, direction = calculate_supertrend(df, period=10, multiplier=3.0)
        closes = df["close"].values
        for i, (sv, dv) in enumerate(zip(st, direction)):
            if math.isnan(float(sv)):
                continue
            if float(dv) == 1.0:
                assert float(sv) <= closes[i] + 0.01  # allow tiny floating point error

    def test_bearish_supertrend_above_close(self):
        # When direction=-1 (bearish), Supertrend is the upper band, so it should
        # be above the closing price for a strong downtrend
        df = _trend_df("down", n=60, step=2.0)
        st, direction = calculate_supertrend(df, period=10, multiplier=3.0)
        closes = df["close"].values
        for i, (sv, dv) in enumerate(zip(st, direction)):
            if math.isnan(float(sv)):
                continue
            if float(dv) == -1.0:
                assert float(sv) >= closes[i] - 0.01


# ---------------------------------------------------------------------------
# Direction flip on price crossover
# ---------------------------------------------------------------------------

class TestDirectionFlip:
    def test_direction_flips_after_trend_reversal(self):
        """Price rises for 30 bars then falls sharply — direction should flip."""
        up_prices = [100 + i * 2.0 for i in range(30)]
        down_prices = [up_prices[-1] - i * 5.0 for i in range(1, 25)]
        all_prices = up_prices + down_prices
        highs = [p + 1.0 for p in all_prices]
        lows = [p - 1.0 for p in all_prices]
        df = make_df(highs, lows, all_prices)

        _, direction = calculate_supertrend(df, period=10, multiplier=3.0)
        valid_dir = direction.dropna()

        # There should be at least one direction flip in the series
        changes = (valid_dir.diff().abs() > 0).sum()
        assert changes >= 1

    def test_no_false_flips_in_clean_uptrend(self):
        """A monotonically rising price with adequate separation should not flip."""
        df = _trend_df("up", n=60, step=3.0)
        _, direction = calculate_supertrend(df, period=10, multiplier=3.0)
        valid_dir = direction.dropna()

        # Once established as bullish, a strong clean trend should not flip
        established = valid_dir.iloc[5:]  # skip early oscillation
        flip_count = int((established.diff().abs() > 0).sum())
        assert flip_count == 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_flat_price_does_not_crash(self):
        df = _flat_df(100.0, n=30)
        st, direction = calculate_supertrend(df, period=10)
        # Should not raise; some values may be NaN or valid
        assert len(st) == 30

    def test_very_high_multiplier_produces_wide_bands(self):
        df = _trend_df("up", n=40, step=1.0)
        st_narrow, _ = calculate_supertrend(df, period=10, multiplier=1.0)
        st_wide, _ = calculate_supertrend(df, period=10, multiplier=10.0)
        # Wider multiplier → bands further from price → supertrend further from close
        # For an uptrend, lower band is further below with high multiplier
        narrow_st = float(st_narrow.dropna().iloc[-1])
        wide_st = float(st_wide.dropna().iloc[-1])
        # Wide multiplier lower band should be further from the price (lower value)
        assert wide_st <= narrow_st

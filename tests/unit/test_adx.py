from __future__ import annotations

import pandas as pd
import pytest

from indicators.advanced_calculators import calculate_adx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_df(highs, lows, closes):
    return pd.DataFrame({"high": highs, "low": lows, "close": closes})


def _trend_df(direction: str, n: int = 50, start: float = 100.0, step: float = 1.0):
    """Generate a clean trending price series."""
    prices = [start + i * step for i in range(n)] if direction == "up" else [
        start - i * step for i in range(n)
    ]
    highs = [p + 0.5 for p in prices]
    lows = [p - 0.5 for p in prices]
    return make_df(highs, lows, prices)


def _flat_df(price: float = 100.0, n: int = 50):
    return make_df([price] * n, [price] * n, [price] * n)


# ---------------------------------------------------------------------------
# Warmup / NaN behaviour
# ---------------------------------------------------------------------------

class TestWarmup:
    def test_fewer_than_period_bars_mostly_nan(self):
        df = _trend_df("up", n=10)
        adx, plus_di, minus_di = calculate_adx(df, 14)
        # ADX needs ~28 bars; with only 10 bars all should be NaN
        assert adx.notna().sum() == 0

    def test_adx_nan_before_warmup_completes(self):
        df = _trend_df("up", n=30)
        adx, _, _ = calculate_adx(df, 14)
        # ADX requires two rounds of EWM (DI then DX); first ~27 bars are NaN
        assert pd.isna(adx.iloc[0])
        assert pd.isna(adx.iloc[13])

    def test_output_series_named_correctly(self):
        df = _trend_df("up", n=50)
        adx, plus_di, minus_di = calculate_adx(df, 14)
        assert adx.name == "adx_14"
        assert plus_di.name == "plus_di"
        assert minus_di.name == "minus_di"

    def test_all_three_series_same_length_as_input(self):
        df = _trend_df("up", n=50)
        adx, plus_di, minus_di = calculate_adx(df, 14)
        assert len(adx) == len(plus_di) == len(minus_di) == 50


# ---------------------------------------------------------------------------
# ADX range [0, 100]
# ---------------------------------------------------------------------------

class TestValueRange:
    def test_adx_non_negative(self):
        df = _trend_df("up", n=80)
        adx, _, _ = calculate_adx(df, 14)
        assert all(float(v) >= 0 for v in adx.dropna())

    def test_adx_at_most_100(self):
        df = _trend_df("up", n=80)
        adx, _, _ = calculate_adx(df, 14)
        assert all(float(v) <= 100.0 for v in adx.dropna())

    def test_plus_di_non_negative(self):
        df = _trend_df("up", n=80)
        _, plus_di, _ = calculate_adx(df, 14)
        assert all(float(v) >= 0 for v in plus_di.dropna())

    def test_minus_di_non_negative(self):
        df = _trend_df("down", n=80)
        _, _, minus_di = calculate_adx(df, 14)
        assert all(float(v) >= 0 for v in minus_di.dropna())


# ---------------------------------------------------------------------------
# Directional bias
# ---------------------------------------------------------------------------

class TestDirectionalBias:
    def test_uptrend_plus_di_greater_than_minus_di(self):
        df = _trend_df("up", n=60, step=2.0)
        _, plus_di, minus_di = calculate_adx(df, 14)
        # Use the last 20 valid bars where trend is well established
        valid_plus = plus_di.dropna().iloc[-20:]
        valid_minus = minus_di.dropna().iloc[-20:]
        # In a clean uptrend +DI should dominate
        assert (valid_plus.values > valid_minus.values).sum() > 15

    def test_downtrend_minus_di_greater_than_plus_di(self):
        df = _trend_df("down", n=60, step=2.0)
        _, plus_di, minus_di = calculate_adx(df, 14)
        valid_plus = plus_di.dropna().iloc[-20:]
        valid_minus = minus_di.dropna().iloc[-20:]
        # In a clean downtrend −DI should dominate
        assert (valid_minus.values > valid_plus.values).sum() > 15

    def test_flat_market_adx_low(self):
        # Price flatlines → negligible DM → ADX near zero
        df = _flat_df(100.0, n=60)
        adx, _, _ = calculate_adx(df, 14)
        valid = adx.dropna()
        # All ADX values should be near zero in a flat market
        assert all(float(v) < 5.0 for v in valid)


# ---------------------------------------------------------------------------
# Trend strength detection
# ---------------------------------------------------------------------------

class TestTrendStrength:
    def test_strong_trend_produces_higher_adx_than_weak_trend(self):
        # Compare ADX at the point just after warmup (before either series saturates
        # at 100). A "strong" trend has a high step relative to the ATR-range;
        # a "weak" trend has a small step.  We compare the mean across the first
        # 10 bars after warmup to avoid ceiling effects.
        strong = _trend_df("up", n=60, step=5.0)
        weak = _trend_df("up", n=60, step=0.1)
        adx_strong, _, _ = calculate_adx(strong, 14)
        adx_weak, _, _ = calculate_adx(weak, 14)
        # Take the earliest 10 valid bars to compare before ADX maxes out
        valid_strong = adx_strong.dropna().iloc[:10]
        valid_weak = adx_weak.dropna().iloc[:10]
        if len(valid_strong) == 0 or len(valid_weak) == 0:
            pytest.skip("Not enough valid ADX bars for comparison")
        assert float(valid_strong.mean()) > float(valid_weak.mean())

    def test_adx_rises_in_established_trend(self):
        df = _trend_df("up", n=80, step=2.0)
        adx, _, _ = calculate_adx(df, 14)
        valid = adx.dropna()
        # ADX should grow as the trend matures (compare first quarter vs last quarter)
        first_quarter = float(valid.iloc[:len(valid)//4].mean())
        last_quarter = float(valid.iloc[-len(valid)//4:].mean())
        assert last_quarter >= first_quarter


# ---------------------------------------------------------------------------
# Flat / edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_all_bars_same_high_low_close_no_dm(self):
        # Flat price → +DM = −DM = 0 → DX = 0/0 (undefined).
        # ADX will be NaN for all bars (both +DI and −DI are 0, so DX denominator=0).
        # The function must not raise; NaN is acceptable for a zero-range series.
        df = _flat_df(100.0, n=50)
        adx, plus_di, minus_di = calculate_adx(df, 14)
        # Must return three Series without raising
        assert isinstance(adx, pd.Series)
        assert isinstance(plus_di, pd.Series)
        assert isinstance(minus_di, pd.Series)
        # +DI and −DI should be near zero or NaN (no directional movement)
        for v in plus_di.dropna():
            assert float(v) < 5.0

    def test_returns_three_series(self):
        df = _trend_df("up", n=40)
        result = calculate_adx(df, 14)
        assert len(result) == 3
        assert all(isinstance(s, pd.Series) for s in result)

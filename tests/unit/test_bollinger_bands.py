from __future__ import annotations

import math

import pandas as pd
import pytest

from indicators.advanced_calculators import calculate_bollinger_bands


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _const_series(value: float, n: int = 30) -> pd.Series:
    return pd.Series([value] * n, dtype=float)


def _rising_series(start: float = 100.0, step: float = 1.0, n: int = 40) -> pd.Series:
    return pd.Series([start + i * step for i in range(n)], dtype=float)


def _falling_series(start: float = 140.0, step: float = 1.0, n: int = 40) -> pd.Series:
    return pd.Series([start - i * step for i in range(n)], dtype=float)


# ---------------------------------------------------------------------------
# Warmup / NaN behaviour
# ---------------------------------------------------------------------------

class TestWarmup:
    def test_fewer_than_period_bars_all_nan(self):
        closes = _const_series(100.0, n=19)
        middle, upper, lower, width = calculate_bollinger_bands(closes, period=20)
        assert middle.notna().sum() == 0
        assert upper.notna().sum() == 0

    def test_first_valid_bar_at_period_index(self):
        closes = _const_series(100.0, n=25)
        middle, upper, lower, width = calculate_bollinger_bands(closes, period=20)
        assert pd.isna(middle.iloc[18])
        assert not pd.isna(middle.iloc[19])

    def test_exactly_period_bars_gives_one_valid(self):
        closes = _const_series(100.0, n=20)
        middle, upper, lower, width = calculate_bollinger_bands(closes, period=20)
        assert middle.notna().sum() == 1

    def test_output_series_named_correctly(self):
        closes = _const_series(100.0, n=30)
        middle, upper, lower, width = calculate_bollinger_bands(closes)
        assert middle.name == "bb_middle"
        assert upper.name == "bb_upper"
        assert lower.name == "bb_lower"
        assert width.name == "bb_width"


# ---------------------------------------------------------------------------
# Constant price series — zero standard deviation
# ---------------------------------------------------------------------------

class TestConstantSeries:
    def test_middle_equals_price_on_constant_series(self):
        closes = _const_series(150.0, n=30)
        middle, _, _, _ = calculate_bollinger_bands(closes)
        valid = middle.dropna()
        assert all(abs(float(v) - 150.0) < 1e-9 for v in valid)

    def test_upper_equals_lower_on_constant_series(self):
        closes = _const_series(100.0, n=30)
        _, upper, lower, _ = calculate_bollinger_bands(closes)
        valid_upper = upper.dropna()
        valid_lower = lower.dropna()
        for u, l in zip(valid_upper, valid_lower):
            assert abs(float(u) - float(l)) < 1e-9

    def test_width_is_zero_on_constant_series(self):
        closes = _const_series(100.0, n=30)
        _, _, _, width = calculate_bollinger_bands(closes)
        valid = width.dropna()
        assert all(abs(float(v)) < 1e-9 for v in valid)

    def test_upper_equals_middle_on_constant_series(self):
        closes = _const_series(200.0, n=30)
        middle, upper, lower, _ = calculate_bollinger_bands(closes)
        for m, u in zip(middle.dropna(), upper.dropna()):
            assert abs(float(m) - float(u)) < 1e-9


# ---------------------------------------------------------------------------
# Band geometry — upper > middle > lower always
# ---------------------------------------------------------------------------

class TestBandGeometry:
    def test_upper_above_middle_for_volatile_series(self):
        import random
        random.seed(42)
        closes = pd.Series([100 + random.gauss(0, 3) for _ in range(50)])
        middle, upper, lower, _ = calculate_bollinger_bands(closes)
        for m, u in zip(middle.dropna(), upper.dropna()):
            assert float(u) >= float(m)

    def test_lower_below_middle_for_volatile_series(self):
        import random
        random.seed(0)
        closes = pd.Series([100 + random.gauss(0, 3) for _ in range(50)])
        middle, upper, lower, _ = calculate_bollinger_bands(closes)
        for m, l in zip(middle.dropna(), lower.dropna()):
            assert float(l) <= float(m)

    def test_upper_minus_lower_equals_four_std(self):
        closes = pd.Series([float(i) for i in range(1, 31)])
        middle, upper, lower, _ = calculate_bollinger_bands(closes, period=20, std_dev=2.0)
        # upper - lower should be 4 × std
        rolling_std = closes.rolling(20, min_periods=20).std(ddof=1)
        for i in range(19, 30):
            band_width = float(upper.iloc[i]) - float(lower.iloc[i])
            expected = 4.0 * float(rolling_std.iloc[i])
            assert abs(band_width - expected) < 1e-6


# ---------------------------------------------------------------------------
# Width — expansion and contraction
# ---------------------------------------------------------------------------

class TestBandWidth:
    def test_width_non_negative_for_random_series(self):
        import random
        random.seed(7)
        closes = pd.Series([100 + random.gauss(0, 5) for _ in range(60)])
        _, _, _, width = calculate_bollinger_bands(closes)
        assert all(float(v) >= 0 for v in width.dropna())

    def test_high_volatility_produces_wider_bands_than_low_volatility(self):
        import random
        random.seed(1)
        high_vol = pd.Series([100 + random.gauss(0, 10) for _ in range(50)])
        low_vol = pd.Series([100 + random.gauss(0, 0.5) for _ in range(50)])
        _, u_h, l_h, _ = calculate_bollinger_bands(high_vol)
        _, u_l, l_l, _ = calculate_bollinger_bands(low_vol)
        avg_width_high = float((u_h - l_h).dropna().mean())
        avg_width_low = float((u_l - l_l).dropna().mean())
        assert avg_width_high > avg_width_low

    def test_width_equals_zero_when_price_flat(self):
        closes = _const_series(50.0, n=30)
        _, _, _, width = calculate_bollinger_bands(closes)
        assert all(abs(float(v)) < 1e-9 for v in width.dropna())


# ---------------------------------------------------------------------------
# Moving average correctness
# ---------------------------------------------------------------------------

class TestMiddleBand:
    def test_middle_matches_simple_rolling_mean(self):
        closes = _rising_series(n=40)
        middle, _, _, _ = calculate_bollinger_bands(closes, period=20)
        expected = closes.rolling(20, min_periods=20).mean()
        for i in range(40):
            if pd.isna(expected.iloc[i]):
                assert pd.isna(middle.iloc[i])
            else:
                assert abs(float(middle.iloc[i]) - float(expected.iloc[i])) < 1e-9

    def test_middle_tracks_rising_prices(self):
        closes = _rising_series(n=40)
        middle, _, _, _ = calculate_bollinger_bands(closes, period=20)
        valid = middle.dropna()
        assert float(valid.iloc[-1]) > float(valid.iloc[0])

    def test_middle_tracks_falling_prices(self):
        closes = _falling_series(n=40)
        middle, _, _, _ = calculate_bollinger_bands(closes, period=20)
        valid = middle.dropna()
        assert float(valid.iloc[-1]) < float(valid.iloc[0])


# ---------------------------------------------------------------------------
# Custom std_dev multiplier
# ---------------------------------------------------------------------------

class TestMultiplier:
    def test_wider_multiplier_produces_wider_bands(self):
        closes = pd.Series([100 + (i % 5) for i in range(40)], dtype=float)
        _, u1, l1, _ = calculate_bollinger_bands(closes, period=20, std_dev=1.0)
        _, u2, l2, _ = calculate_bollinger_bands(closes, period=20, std_dev=3.0)
        band1 = float((u1 - l1).dropna().mean())
        band2 = float((u2 - l2).dropna().mean())
        assert band2 > band1

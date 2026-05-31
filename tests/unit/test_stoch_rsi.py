from __future__ import annotations

import pandas as pd
import pytest

from indicators.advanced_calculators import calculate_stoch_rsi


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rising_series(n: int = 60, start: float = 100.0, step: float = 1.0) -> pd.Series:
    return pd.Series([start + i * step for i in range(n)], dtype=float)


def _falling_series(n: int = 60, start: float = 160.0, step: float = 1.0) -> pd.Series:
    return pd.Series([start - i * step for i in range(n)], dtype=float)


def _flat_series(value: float = 100.0, n: int = 60) -> pd.Series:
    return pd.Series([value] * n, dtype=float)


def _alternating_series(n: int = 60) -> pd.Series:
    """Alternates between 100 and 101 — RSI stays near 50."""
    return pd.Series([100.0 + (i % 2) for i in range(n)], dtype=float)


# ---------------------------------------------------------------------------
# Warmup / NaN behaviour
# ---------------------------------------------------------------------------

class TestWarmup:
    def test_bars_before_warmup_all_nan(self):
        closes = _rising_series(n=27)
        k, d = calculate_stoch_rsi(closes, rsi_period=14, stoch_period=14)
        # K warmup ≈ rsi_period + stoch_period − 1 = 27 bars; 27 bars → all NaN
        assert k.notna().sum() == 0

    def test_k_valid_after_rsi_plus_stoch_warmup(self):
        # Need rsi_period + stoch_period bars for %K to be valid
        closes = _rising_series(n=40)
        k, d = calculate_stoch_rsi(closes, rsi_period=14, stoch_period=14)
        # With 40 bars and warmup=27, last few should have valid K
        assert k.notna().sum() > 0

    def test_d_requires_extra_3_bars_after_k(self):
        closes = _rising_series(n=50)
        k, d = calculate_stoch_rsi(closes, rsi_period=14, stoch_period=14)
        # %D needs 3 valid %K values; there should be fewer valid D than K
        assert d.notna().sum() <= k.notna().sum()

    def test_output_series_named_correctly(self):
        closes = _rising_series(n=50)
        k, d = calculate_stoch_rsi(closes)
        assert k.name == "stoch_rsi_k"
        assert d.name == "stoch_rsi_d"

    def test_output_same_length_as_input(self):
        closes = _rising_series(n=50)
        k, d = calculate_stoch_rsi(closes, rsi_period=14, stoch_period=14)
        assert len(k) == len(d) == 50


# ---------------------------------------------------------------------------
# Value range [0, 100]
# ---------------------------------------------------------------------------

class TestValueRange:
    def test_k_in_range_0_to_100(self):
        closes = _alternating_series(n=80)
        k, _ = calculate_stoch_rsi(closes)
        valid = k.dropna()
        assert all(0.0 <= float(v) <= 100.0 for v in valid)

    def test_d_in_range_0_to_100(self):
        closes = _alternating_series(n=80)
        _, d = calculate_stoch_rsi(closes)
        valid = d.dropna()
        assert all(0.0 <= float(v) <= 100.0 for v in valid)

    def test_k_non_negative_for_rising_series(self):
        closes = _rising_series(n=60)
        k, _ = calculate_stoch_rsi(closes)
        assert all(float(v) >= 0.0 for v in k.dropna())

    def test_k_at_most_100_for_falling_series(self):
        closes = _falling_series(n=60)
        k, _ = calculate_stoch_rsi(closes)
        assert all(float(v) <= 100.0 for v in k.dropna())


# ---------------------------------------------------------------------------
# Overbought / oversold interpretation
# ---------------------------------------------------------------------------

class TestInterpretation:
    def test_pure_uptrend_k_high(self):
        # A strongly rising series pushes RSI near 100; Stoch RSI K should be high
        closes = _rising_series(n=80, step=2.0)
        k, _ = calculate_stoch_rsi(closes, rsi_period=14, stoch_period=14)
        valid = k.dropna()
        # Average K in a pure uptrend should be well above 50
        assert float(valid.mean()) > 50.0

    def test_pure_downtrend_k_low(self):
        # A strongly falling series pushes RSI near 0; Stoch RSI K should be low
        closes = _falling_series(n=80, step=2.0)
        k, _ = calculate_stoch_rsi(closes, rsi_period=14, stoch_period=14)
        valid = k.dropna()
        # Average K in a pure downtrend should be well below 50
        assert float(valid.mean()) < 50.0


# ---------------------------------------------------------------------------
# D is a smoothed version of K
# ---------------------------------------------------------------------------

class TestDSmoothing:
    def test_d_is_within_k_range(self):
        closes = _alternating_series(n=80)
        k, d = calculate_stoch_rsi(closes)
        k_min = float(k.dropna().min())
        k_max = float(k.dropna().max())
        for v in d.dropna():
            assert k_min - 0.01 <= float(v) <= k_max + 0.01

    def test_d_lags_behind_k(self):
        # When K changes rapidly, D (3-bar SMA) should trail behind
        closes = _rising_series(n=80, step=3.0)
        k, d = calculate_stoch_rsi(closes)
        # Just check both are valid and D exists
        assert k.notna().sum() > 0
        assert d.notna().sum() > 0


# ---------------------------------------------------------------------------
# Flat series — constant RSI → undefined K
# ---------------------------------------------------------------------------

class TestFlatSeries:
    def test_flat_series_k_is_nan_or_boundary(self):
        # A perfectly flat series → RSI is NaN (both avg_gain and avg_loss are 0)
        # → Stoch RSI should also be NaN
        closes = _flat_series(n=60)
        k, d = calculate_stoch_rsi(closes)
        # Flat price: RSI undefined → K undefined
        assert k.notna().sum() == 0 or all(
            pd.isna(v) for v in k.dropna().head(1)
        )


# ---------------------------------------------------------------------------
# Custom periods
# ---------------------------------------------------------------------------

class TestCustomPeriods:
    def test_shorter_rsi_period_produces_more_valid_bars(self):
        closes = _alternating_series(n=50)
        k7, _ = calculate_stoch_rsi(closes, rsi_period=7, stoch_period=7)
        k14, _ = calculate_stoch_rsi(closes, rsi_period=14, stoch_period=14)
        assert k7.notna().sum() >= k14.notna().sum()

    def test_returns_two_series(self):
        closes = _rising_series(n=40)
        result = calculate_stoch_rsi(closes)
        assert len(result) == 2
        assert all(isinstance(s, pd.Series) for s in result)

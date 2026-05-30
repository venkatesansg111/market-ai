from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest

from indicators.indicator_calculators import (
    calculate_ema,
    calculate_macd,
    calculate_rsi,
    calculate_vwap_session,
)


def make_closes(values: list[float]) -> pd.Series:
    return pd.Series(values, dtype=float)


def make_ohlcv_df(n: int = 20, session_breaks: list[int] | None = None) -> pd.DataFrame:
    """Create a DataFrame with DatetimeIndex suitable for VWAP calculations."""
    base = datetime(2024, 1, 15, 9, 15)
    dates = []
    day_offset = 0
    for i in range(n):
        if session_breaks and i in session_breaks:
            day_offset += 1
        dates.append(base + timedelta(days=day_offset, minutes=i % 390))

    price = 22000.0
    rows = []
    for _ in dates:
        rows.append(
            {
                "high": price * 1.005,
                "low": price * 0.995,
                "close": price * 1.001,
                "volume": 1000.0,
            }
        )
        price *= 1.0005

    df = pd.DataFrame(rows, index=pd.DatetimeIndex(dates))
    return df


# ──────────────────────────────────────────────────────────────────────
# EMA
# ──────────────────────────────────────────────────────────────────────

class TestEMA:
    def test_ema_returns_series(self):
        closes = make_closes([float(i) for i in range(1, 21)])
        result = calculate_ema(closes, 10)
        assert isinstance(result, pd.Series)
        assert len(result) == 20

    def test_ema_rising_prices_produces_rising_ema(self):
        closes = make_closes([float(i) for i in range(1, 21)])
        ema = calculate_ema(closes, 5)
        valid = ema.dropna()
        assert len(valid) > 0
        assert valid.iloc[-1] > valid.iloc[0]

    def test_ema_warmup_nans(self):
        closes = make_closes([100.0] * 10)
        ema = calculate_ema(closes, 5)
        # First 4 values should be NaN (min_periods=period)
        assert ema.iloc[:4].isna().all()
        assert not pd.isna(ema.iloc[4])

    def test_ema_constant_series(self):
        closes = make_closes([100.0] * 20)
        ema = calculate_ema(closes, 5)
        valid = ema.dropna()
        assert all(abs(v - 100.0) < 0.001 for v in valid)

    def test_ema200_requires_200_bars(self):
        closes = make_closes([float(i) for i in range(1, 201)])
        ema = calculate_ema(closes, 200)
        assert pd.isna(ema.iloc[198])  # bar 199 still NaN
        assert not pd.isna(ema.iloc[199])  # bar 200 is first valid


# ──────────────────────────────────────────────────────────────────────
# RSI
# ──────────────────────────────────────────────────────────────────────

class TestRSI:
    def test_rsi_returns_series(self):
        closes = make_closes([float(i) for i in range(1, 21)])
        result = calculate_rsi(closes, 14)
        assert isinstance(result, pd.Series)

    def test_rsi_all_up_series_is_overbought(self):
        closes = make_closes([float(i) for i in range(1, 30)])
        rsi = calculate_rsi(closes, 14)
        valid = rsi.dropna()
        assert len(valid) > 0
        assert float(valid.iloc[-1]) > 70

    def test_rsi_all_down_series_is_oversold(self):
        closes = make_closes([float(30 - i) for i in range(30)])
        rsi = calculate_rsi(closes, 14)
        valid = rsi.dropna()
        assert len(valid) > 0
        assert float(valid.iloc[-1]) < 30

    def test_rsi_values_bounded_0_to_100(self):
        import random
        random.seed(42)
        prices = [100.0]
        for _ in range(50):
            prices.append(prices[-1] * (1 + random.gauss(0, 0.01)))
        rsi = calculate_rsi(make_closes(prices), 14)
        valid = rsi.dropna()
        assert all(0.0 <= v <= 100.0 for v in valid)

    def test_rsi_warmup_nans(self):
        closes = make_closes([float(i) for i in range(1, 30)])
        rsi = calculate_rsi(closes, 14)
        assert rsi.iloc[:14].isna().all()


# ──────────────────────────────────────────────────────────────────────
# VWAP
# ──────────────────────────────────────────────────────────────────────

class TestVWAP:
    def test_vwap_returns_series(self):
        df = make_ohlcv_df(10)
        result = calculate_vwap_session(df)
        assert isinstance(result, pd.Series)
        assert len(result) == 10

    def test_vwap_equal_to_typical_price_when_single_bar_per_session(self):
        dates = [datetime(2024, 1, 15, 9, 15)]
        df = pd.DataFrame(
            [{"high": 100.0, "low": 96.0, "close": 98.0, "volume": 1000.0}],
            index=pd.DatetimeIndex(dates),
        )
        vwap = calculate_vwap_session(df)
        expected = (100.0 + 96.0 + 98.0) / 3.0
        assert abs(float(vwap.iloc[0]) - expected) < 0.001

    def test_vwap_is_volume_weighted(self):
        dates = pd.date_range("2024-01-15 09:15", periods=3, freq="1min")
        # All same price; VWAP should equal typical price
        df = pd.DataFrame(
            {
                "high": [100.0, 100.0, 100.0],
                "low": [100.0, 100.0, 100.0],
                "close": [100.0, 100.0, 100.0],
                "volume": [1000.0, 2000.0, 3000.0],
            },
            index=dates,
        )
        vwap = calculate_vwap_session(df)
        # Typical price = 100 for all bars; VWAP = 100 regardless of volume
        assert all(abs(v - 100.0) < 0.001 for v in vwap.dropna())

    def test_vwap_resets_between_sessions(self):
        # Session 1: low prices; Session 2: high prices
        day1 = pd.date_range("2024-01-15 09:15", periods=3, freq="1min")
        day2 = pd.date_range("2024-01-16 09:15", periods=3, freq="1min")
        all_dates = day1.tolist() + day2.tolist()

        df = pd.DataFrame(
            {
                "high": [100.0, 101.0, 102.0, 500.0, 501.0, 502.0],
                "low": [99.0, 100.0, 101.0, 499.0, 500.0, 501.0],
                "close": [99.5, 100.5, 101.5, 499.5, 500.5, 501.5],
                "volume": [1000.0] * 6,
            },
            index=pd.DatetimeIndex(all_dates),
        )
        vwap = calculate_vwap_session(df)
        # Session 2 first VWAP should be near 499.8 (not cumulative from session 1)
        assert float(vwap.iloc[3]) < 502.0
        assert float(vwap.iloc[3]) > 498.0

    def test_vwap_empty_dataframe(self):
        df = pd.DataFrame(columns=["high", "low", "close", "volume"])
        result = calculate_vwap_session(df)
        assert len(result) == 0


# ──────────────────────────────────────────────────────────────────────
# MACD
# ──────────────────────────────────────────────────────────────────────

class TestMACD:
    def test_macd_returns_two_series(self):
        closes = make_closes([float(i) for i in range(1, 51)])
        macd_line, signal_line = calculate_macd(closes)
        assert isinstance(macd_line, pd.Series)
        assert isinstance(signal_line, pd.Series)
        assert len(macd_line) == len(closes)
        assert len(signal_line) == len(closes)

    def test_macd_warmup_nans(self):
        closes = make_closes([100.0] * 50)
        macd_line, signal_line = calculate_macd(closes, fast=12, slow=26, signal=9)
        # MACD line requires slow (26) bars; signal requires additional signal (9) bars
        assert macd_line.iloc[:25].isna().all()
        assert signal_line.iloc[:33].isna().all()

    def test_macd_positive_on_rising_prices(self):
        closes = make_closes([float(i) for i in range(1, 60)])
        macd_line, _ = calculate_macd(closes)
        valid = macd_line.dropna()
        # Rising prices → fast EMA > slow EMA → MACD > 0
        assert float(valid.iloc[-1]) > 0

    def test_macd_negative_on_falling_prices(self):
        closes = make_closes([float(60 - i) for i in range(60)])
        macd_line, _ = calculate_macd(closes)
        valid = macd_line.dropna()
        assert float(valid.iloc[-1]) < 0

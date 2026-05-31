from __future__ import annotations

import math

import numpy as np
import pandas as pd

from indicators.indicator_calculators import calculate_rsi


# ---------------------------------------------------------------------------
# ATR — Average True Range (Wilder's Smoothing)
# ---------------------------------------------------------------------------

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range using Wilder's smoothing (alpha = 1/period).

    True Range = max(High − Low, |High − Prev_Close|, |Low − Prev_Close|)
    ATR is then smoothed with EWM alpha=1/period, matching TradingView / Zerodha.

    Args:
        df:     DataFrame with columns high, low, close.
        period: Smoothing period (default 14).

    Returns:
        pd.Series of ATR values. NaN for the first (period − 1) bars.
        Always ≥ 0 for valid rows.
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    atr.name = "atr_14"
    return atr


# ---------------------------------------------------------------------------
# ADX — Average Directional Index with +DI / −DI
# ---------------------------------------------------------------------------

def calculate_adx(
    df: pd.DataFrame, period: int = 14
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """ADX, +DI, and −DI using Wilder's smoothing (alpha = 1/period).

    Algorithm:
        +DM = High − Prev_High  if (+DM > −DM and +DM > 0) else 0
        −DM = Prev_Low − Low    if (−DM > +DM and −DM > 0) else 0
        ATR = Wilder-smooth(True Range, period)
        +DI = 100 × Wilder-smooth(+DM, period) / ATR
        −DI = 100 × Wilder-smooth(−DM, period) / ATR
        DX  = 100 × |+DI − −DI| / (+DI + −DI)
        ADX = Wilder-smooth(DX, period)

    Args:
        df:     DataFrame with columns high, low, close.
        period: Smoothing period (default 14).

    Returns:
        Tuple (adx, plus_di, minus_di) — all aligned to df.index.
        NaN during warmup (~2 × period bars before ADX stabilises).
        ADX and DI values are in the range [0, 100].
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)

    # True Range
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    # Directional movement
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=high.index,
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=high.index,
    )

    alpha = 1.0 / period
    atr_w = tr.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    plus_dm_w = plus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    minus_dm_w = minus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean()

    plus_di = 100.0 * plus_dm_w / atr_w.replace(0.0, float("nan"))
    minus_di = 100.0 * minus_dm_w / atr_w.replace(0.0, float("nan"))

    dx_denom = (plus_di + minus_di).replace(0.0, float("nan"))
    dx = 100.0 * (plus_di - minus_di).abs() / dx_denom
    adx = dx.ewm(alpha=alpha, adjust=False, min_periods=period).mean()

    adx.name = "adx_14"
    plus_di.name = "plus_di"
    minus_di.name = "minus_di"
    return adx, plus_di, minus_di


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------

def calculate_bollinger_bands(
    closes: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Bollinger Bands using a simple moving average and rolling standard deviation.

    Middle = SMA(close, period)
    Upper  = Middle + std_dev × StdDev(close, period)
    Lower  = Middle − std_dev × StdDev(close, period)
    Width  = (Upper − Lower) / Middle  (normalised band width, dimensionless)

    Uses ddof=1 (sample std dev), matching most charting platforms.

    Args:
        closes:  Close price series.
        period:  Rolling window (default 20).
        std_dev: Number of standard deviations (default 2.0).

    Returns:
        Tuple (middle, upper, lower, width). NaN for the first (period − 1) bars.
    """
    middle = closes.rolling(window=period, min_periods=period).mean()
    std = closes.rolling(window=period, min_periods=period).std(ddof=1)

    upper = middle + std_dev * std
    lower = middle - std_dev * std
    width = (upper - lower) / middle.replace(0.0, float("nan"))

    middle.name = "bb_middle"
    upper.name = "bb_upper"
    lower.name = "bb_lower"
    width.name = "bb_width"
    return middle, upper, lower, width


# ---------------------------------------------------------------------------
# Supertrend
# ---------------------------------------------------------------------------

def calculate_supertrend(
    df: pd.DataFrame,
    period: int = 10,
    multiplier: float = 3.0,
) -> tuple[pd.Series, pd.Series]:
    """Supertrend indicator based on ATR-adjusted price bands.

    Algorithm:
        HL2         = (High + Low) / 2
        Raw Upper   = HL2 + multiplier × ATR(period)
        Raw Lower   = HL2 − multiplier × ATR(period)

        Final bands "lock" once price commits to a side:
          Final Upper[i] = min(Raw Upper[i], Final Upper[i−1])
                           unless Close[i−1] > Final Upper[i−1]  (price broke out → reset)
          Final Lower[i] = max(Raw Lower[i], Final Lower[i−1])
                           unless Close[i−1] < Final Lower[i−1]  (price broke out → reset)

        Direction:
          If previous supertrend == upper band (bearish):
              Close > Final Upper[i] → flip to bullish (use lower band)
              else stay bearish      (use upper band)
          If previous supertrend == lower band (bullish):
              Close < Final Lower[i] → flip to bearish (use upper band)
              else stay bullish      (use lower band)

    Args:
        df:         DataFrame with columns high, low, close.
        period:     ATR period (default 10).
        multiplier: Band multiplier (default 3.0).

    Returns:
        Tuple (supertrend_values, direction_values).
        direction: 1 = Bullish, −1 = Bearish, NaN during ATR warmup.
        NaN for bars before ATR warmup completes.
    """
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values

    atr_series = calculate_atr(df, period)
    atr = atr_series.values

    n = len(df)
    hl2 = (high + low) / 2.0
    raw_upper = hl2 + multiplier * atr
    raw_lower = hl2 - multiplier * atr

    final_upper = np.full(n, float("nan"))
    final_lower = np.full(n, float("nan"))
    supertrend_vals = np.full(n, float("nan"))
    direction_vals = np.full(n, float("nan"))

    # Find index of the first bar with a valid ATR value
    first_valid = -1
    for i in range(n):
        if not math.isnan(atr[i]):
            first_valid = i
            break

    if first_valid == -1:
        return (
            pd.Series(supertrend_vals, index=df.index, name="supertrend"),
            pd.Series(direction_vals, index=df.index, name="supertrend_direction"),
        )

    # Initialise bands at the first valid bar
    final_upper[first_valid] = raw_upper[first_valid]
    final_lower[first_valid] = raw_lower[first_valid]

    # Initial direction: bearish if close is below (or at) the upper band
    if close[first_valid] > raw_upper[first_valid]:
        direction_vals[first_valid] = 1.0
        supertrend_vals[first_valid] = final_lower[first_valid]
    else:
        direction_vals[first_valid] = -1.0
        supertrend_vals[first_valid] = final_upper[first_valid]

    for i in range(first_valid + 1, n):
        if math.isnan(atr[i]):
            continue

        prev_i = i - 1

        # ── Compute final bands ──────────────────────────────────────────
        # Upper band can only move down (tightens) unless price crossed above it
        if close[prev_i] > final_upper[prev_i]:
            final_upper[i] = raw_upper[i]
        else:
            final_upper[i] = min(raw_upper[i], final_upper[prev_i])

        # Lower band can only move up (tightens) unless price crossed below it
        if close[prev_i] < final_lower[prev_i]:
            final_lower[i] = raw_lower[i]
        else:
            final_lower[i] = max(raw_lower[i], final_lower[prev_i])

        # ── Determine trend direction ────────────────────────────────────
        prev_dir = direction_vals[prev_i]

        if prev_dir == -1.0:
            # Previous bar was bearish (supertrend = upper band)
            if close[i] > final_upper[i]:
                direction_vals[i] = 1.0
                supertrend_vals[i] = final_lower[i]
            else:
                direction_vals[i] = -1.0
                supertrend_vals[i] = final_upper[i]
        else:
            # Previous bar was bullish (supertrend = lower band)
            if close[i] < final_lower[i]:
                direction_vals[i] = -1.0
                supertrend_vals[i] = final_upper[i]
            else:
                direction_vals[i] = 1.0
                supertrend_vals[i] = final_lower[i]

    return (
        pd.Series(supertrend_vals, index=df.index, name="supertrend"),
        pd.Series(direction_vals, index=df.index, name="supertrend_direction"),
    )


# ---------------------------------------------------------------------------
# OBV — On Balance Volume
# ---------------------------------------------------------------------------

def calculate_obv(closes: pd.Series, volumes: pd.Series) -> pd.Series:
    """On Balance Volume: running cumulative volume conditioned on price direction.

    OBV[i] = OBV[i−1] + volume[i]   if close[i] > close[i−1]  (up-close)
    OBV[i] = OBV[i−1] − volume[i]   if close[i] < close[i−1]  (down-close)
    OBV[i] = OBV[i−1]                if close[i] == close[i−1] (unchanged)

    The first bar always contributes its full volume as a positive (baseline).
    No warmup period — all bars are valid from the first bar.

    Args:
        closes:  Close price series.
        volumes: Volume series aligned to closes.

    Returns:
        pd.Series of OBV values (integer-magnitude, stored as float).
    """
    price_change = closes.diff()

    # +1 for up-closes, -1 for down-closes, 0 for unchanged
    sign = np.sign(price_change.fillna(0.0))
    # First bar has no comparison → treat as positive (standard convention)
    sign.iloc[0] = 1.0

    obv = (sign * volumes).cumsum()
    obv.name = "obv"
    return obv


# ---------------------------------------------------------------------------
# Stochastic RSI
# ---------------------------------------------------------------------------

def calculate_stoch_rsi(
    closes: pd.Series,
    rsi_period: int = 14,
    stoch_period: int = 14,
) -> tuple[pd.Series, pd.Series]:
    """Stochastic RSI: applies Stochastic oscillator logic to the RSI series.

    RSI    = RSI(close, rsi_period)            (Wilder's smoothing)
    %K     = 100 × (RSI − min(RSI, stoch_period)) / (max − min)
    %D     = SMA(%K, 3)

    When the RSI range over the stoch_period window is 0 (constant RSI),
    %K is undefined (NaN) to avoid division by zero.

    Warmup:
        %K: rsi_period + stoch_period − 1 bars
        %D: rsi_period + stoch_period + 1 bars  (adds 3-bar SMA)

    Both %K and %D are in the range [0, 100] for valid values.

    Args:
        closes:       Close price series.
        rsi_period:   RSI calculation period (default 14).
        stoch_period: Rolling window applied to RSI (default 14).

    Returns:
        Tuple (%K, %D) — both aligned to closes.index.
    """
    rsi = calculate_rsi(closes, rsi_period)

    rsi_min = rsi.rolling(window=stoch_period, min_periods=stoch_period).min()
    rsi_max = rsi.rolling(window=stoch_period, min_periods=stoch_period).max()

    rsi_range = (rsi_max - rsi_min).replace(0.0, float("nan"))
    stoch_raw = (rsi - rsi_min) / rsi_range

    k = (stoch_raw * 100.0).clip(lower=0.0, upper=100.0)
    d = k.rolling(window=3, min_periods=3).mean()

    k.name = "stoch_rsi_k"
    d.name = "stoch_rsi_d"
    return k, d

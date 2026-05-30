from __future__ import annotations

import pandas as pd


def calculate_ema(closes: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average using pandas ewm (standard EMA formula).

    Uses span=period so alpha = 2/(period+1), matching most charting platforms.
    Returns NaN for the first (period-1) bars during warmup.
    """
    return closes.ewm(span=period, adjust=False, min_periods=period).mean()


def calculate_rsi(closes: pd.Series, period: int = 14) -> pd.Series:
    """RSI using Wilder's smoothing (alpha = 1/period), matching TradingView / Zerodha.

    Returns values in [0, 100]. Returns NaN for bars before warmup completes.
    For a flat price series both avg_gain and avg_loss are 0 — returns NaN (not 50).
    """
    delta = closes.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, float("nan"))
    return 100.0 - (100.0 / (1.0 + rs))


def calculate_vwap_session(df: pd.DataFrame) -> pd.Series:
    """Session-based VWAP that resets at the start of each calendar day.

    Args:
        df: DataFrame with columns high, low, close, volume. Index must be
            DatetimeIndex or coercible to one.

    Returns:
        pd.Series of VWAP values aligned to df.index, named 'vwap'.
        For daily candles each session has one bar so VWAP = typical price.
    """
    if df.empty:
        return pd.Series(dtype=float, name="vwap", index=df.index)

    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    tp_vol = typical_price * df["volume"].astype(float)
    volume = df["volume"].astype(float)

    # Normalize index to date for grouping; normalize() floors to midnight
    if isinstance(df.index, pd.DatetimeIndex):
        dates = df.index.normalize()
    else:
        dates = pd.to_datetime(df.index).normalize()

    temp = pd.DataFrame(
        {"tp_vol": tp_vol.values, "volume": volume.values, "date": dates},
        index=df.index,
    )
    cum_tpv = temp.groupby("date")["tp_vol"].cumsum()
    cum_vol = temp.groupby("date")["volume"].cumsum()

    vwap = cum_tpv / cum_vol.replace(0.0, float("nan"))
    vwap.name = "vwap"
    return vwap


def calculate_macd(
    closes: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series]:
    """MACD line and signal line using standard EMA parameters (12, 26, 9).

    Returns:
        (macd_line, signal_line) — both aligned to closes.index.
        NaN during warmup (first slow+signal-1 bars).
    """
    ema_fast = closes.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = closes.ewm(span=slow, adjust=False, min_periods=slow).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return macd_line, signal_line

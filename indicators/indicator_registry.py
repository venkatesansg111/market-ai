from __future__ import annotations

from indicators.indicator_metadata import IndicatorCategory, IndicatorDefinition

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
# Each entry maps the canonical short name to its IndicatorDefinition.
# Names are lowercase and match the IndicatorRecord field names exactly
# (multi-output indicators like ADX use the primary output as the key).

INDICATORS: dict[str, IndicatorDefinition] = {
    # ── Trend / moving averages ──────────────────────────────────────────
    "ema20": IndicatorDefinition(
        name="ema20",
        description="20-period Exponential Moving Average (span=20, alpha=2/21)",
        required_columns=["close"],
        output_columns=["ema20"],
        warmup_period=20,
        category=IndicatorCategory.TREND,
    ),
    "ema50": IndicatorDefinition(
        name="ema50",
        description="50-period Exponential Moving Average (span=50, alpha=2/51)",
        required_columns=["close"],
        output_columns=["ema50"],
        warmup_period=50,
        category=IndicatorCategory.TREND,
    ),
    "ema200": IndicatorDefinition(
        name="ema200",
        description="200-period Exponential Moving Average (span=200, alpha=2/201)",
        required_columns=["close"],
        output_columns=["ema200"],
        warmup_period=200,
        category=IndicatorCategory.TREND,
    ),
    # ── Momentum ─────────────────────────────────────────────────────────
    "rsi14": IndicatorDefinition(
        name="rsi14",
        description=(
            "14-period RSI using Wilder's smoothing (alpha=1/14). "
            "Range [0, 100]. Overbought >70, Oversold <30."
        ),
        required_columns=["close"],
        output_columns=["rsi14"],
        warmup_period=14,
        category=IndicatorCategory.MOMENTUM,
    ),
    "macd": IndicatorDefinition(
        name="macd",
        description=(
            "MACD(12,26,9): macd_line = EMA12 − EMA26; "
            "signal_line = EMA9 of macd_line. "
            "Warmup ≈ 34 bars (26+9−1)."
        ),
        required_columns=["close"],
        output_columns=["macd", "macd_signal"],
        warmup_period=34,
        category=IndicatorCategory.MOMENTUM,
    ),
    "stoch_rsi": IndicatorDefinition(
        name="stoch_rsi",
        description=(
            "Stochastic RSI: applies a 14-bar stochastic oscillator to RSI(14). "
            "%K = 100*(RSI − min14) / (max14 − min14); %D = SMA3(%K). "
            "Warmup ≈ 28 bars for %K, 31 for %D. Range [0, 100]."
        ),
        required_columns=["close"],
        output_columns=["stoch_rsi_k", "stoch_rsi_d"],
        warmup_period=28,
        category=IndicatorCategory.MOMENTUM,
    ),
    # ── Volatility ───────────────────────────────────────────────────────
    "vwap": IndicatorDefinition(
        name="vwap",
        description=(
            "Session VWAP: cumsum(TP×V)/cumsum(V) per calendar day. "
            "TP = (High+Low+Close)/3. Resets daily. No warmup."
        ),
        required_columns=["high", "low", "close", "volume"],
        output_columns=["vwap"],
        warmup_period=1,
        category=IndicatorCategory.VOLATILITY,
    ),
    "atr14": IndicatorDefinition(
        name="atr14",
        description=(
            "14-period Average True Range using Wilder's smoothing (alpha=1/14). "
            "TR = max(H−L, |H−PrevC|, |L−PrevC|). Always ≥ 0."
        ),
        required_columns=["high", "low", "close"],
        output_columns=["atr_14"],
        warmup_period=14,
        category=IndicatorCategory.VOLATILITY,
    ),
    "bb20": IndicatorDefinition(
        name="bb20",
        description=(
            "Bollinger Bands(20, 2): Middle=SMA20; "
            "Upper/Lower = Middle ± 2×StdDev(20). "
            "Width = (Upper−Lower)/Middle."
        ),
        required_columns=["close"],
        output_columns=["bb_middle", "bb_upper", "bb_lower", "bb_width"],
        warmup_period=20,
        category=IndicatorCategory.VOLATILITY,
    ),
    "supertrend": IndicatorDefinition(
        name="supertrend",
        description=(
            "Supertrend(10, 3): trend-following indicator based on ATR10. "
            "Upper/Lower bands = (H+L)/2 ± 3×ATR. "
            "Direction: 1=Bullish, −1=Bearish."
        ),
        required_columns=["high", "low", "close"],
        output_columns=["supertrend", "supertrend_direction"],
        warmup_period=10,
        category=IndicatorCategory.VOLATILITY,
    ),
    # ── Volume ───────────────────────────────────────────────────────────
    "obv": IndicatorDefinition(
        name="obv",
        description=(
            "On Balance Volume: running cumulative volume where up-close bars "
            "add volume and down-close bars subtract volume. No warmup."
        ),
        required_columns=["close", "volume"],
        output_columns=["obv"],
        warmup_period=1,
        category=IndicatorCategory.VOLUME,
    ),
    "adx14": IndicatorDefinition(
        name="adx14",
        description=(
            "ADX(14) with +DI and −DI using Wilder's smoothing. "
            "ADX range [0, 100]; trend strength: >25 strong, >50 very strong. "
            "Warmup ≈ 28 bars (ATR14 + DX smoothing)."
        ),
        required_columns=["high", "low", "close"],
        output_columns=["adx_14", "plus_di", "minus_di"],
        warmup_period=28,
        category=IndicatorCategory.TREND,
    ),
}


def get_indicator(name: str) -> IndicatorDefinition:
    """Return the IndicatorDefinition for *name* (case-insensitive).

    Raises:
        KeyError: if *name* is not registered. Message lists available names.
    """
    key = name.lower()
    if key not in INDICATORS:
        raise KeyError(
            f"Unknown indicator '{name}'. "
            f"Available: {list(INDICATORS)}"
        )
    return INDICATORS[key]


def list_indicators() -> list[str]:
    """Return all registered indicator names in registration order."""
    return list(INDICATORS)

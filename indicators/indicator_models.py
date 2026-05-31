from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True, slots=True)
class IndicatorRecord:
    """Domain model for a single row of computed indicators.

    All indicator fields are Optional because indicators have different warmup
    requirements (EMA200 needs 200 bars, ADX needs ~28 bars, etc.). Early rows
    will have None for indicators that have not yet warmed up.

    Phase 1 (original) fields: ema20, ema50, ema200, rsi14, vwap, macd, macd_signal
    Phase 4B (advanced) fields: atr_14, adx_14, plus_di, minus_di,
                                 bb_middle, bb_upper, bb_lower, bb_width,
                                 supertrend, supertrend_direction,
                                 obv, stoch_rsi_k, stoch_rsi_d
    """

    instrument: str
    candle_time: datetime
    timeframe: str
    # ── Phase 1 indicators ───────────────────────────────────────────────
    ema20: Optional[Decimal] = None
    ema50: Optional[Decimal] = None
    ema200: Optional[Decimal] = None
    rsi14: Optional[Decimal] = None
    vwap: Optional[Decimal] = None
    macd: Optional[Decimal] = None
    macd_signal: Optional[Decimal] = None
    # ── Phase 4B indicators ──────────────────────────────────────────────
    atr_14: Optional[Decimal] = None
    adx_14: Optional[Decimal] = None
    plus_di: Optional[Decimal] = None
    minus_di: Optional[Decimal] = None
    bb_middle: Optional[Decimal] = None
    bb_upper: Optional[Decimal] = None
    bb_lower: Optional[Decimal] = None
    bb_width: Optional[Decimal] = None
    supertrend: Optional[Decimal] = None
    supertrend_direction: Optional[int] = None   # 1 = Bullish, -1 = Bearish
    obv: Optional[Decimal] = None
    stoch_rsi_k: Optional[Decimal] = None
    stoch_rsi_d: Optional[Decimal] = None

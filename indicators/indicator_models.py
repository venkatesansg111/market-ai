from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True, slots=True)
class IndicatorRecord:
    """Domain model for a single row of computed indicators.

    All indicator fields are Optional because EMA200 requires 200 candles before
    the first valid value, and MACD requires 26+9=35 candles. Early rows will have
    None for indicators that haven't warmed up yet.
    """

    instrument: str
    candle_time: datetime
    timeframe: str
    ema20: Optional[Decimal] = None
    ema50: Optional[Decimal] = None
    ema200: Optional[Decimal] = None
    rsi14: Optional[Decimal] = None
    vwap: Optional[Decimal] = None
    macd: Optional[Decimal] = None
    macd_signal: Optional[Decimal] = None

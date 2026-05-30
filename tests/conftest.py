from __future__ import annotations

"""Shared pytest fixtures for unit and integration tests."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from data_providers.base import CandleData, Timeframe
from indicators.indicator_models import IndicatorRecord


# ──────────────────────────────────────────────────────────────────────
# Data factories
# ──────────────────────────────────────────────────────────────────────

def make_candle(
    instrument: str = "NIFTY 50",
    candle_time: datetime = datetime(2024, 1, 15, 9, 15),
    open: float = 22000.0,
    high: float = 22100.0,
    low: float = 21900.0,
    close: float = 22050.0,
    volume: int = 100000,
    timeframe: str = "1day",
) -> CandleData:
    return CandleData(
        instrument=instrument,
        candle_time=candle_time.isoformat(),
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
        timeframe=timeframe,
    )


def make_candle_series(
    n: int,
    instrument: str = "NIFTY 50",
    timeframe: str = "1day",
    start: datetime = datetime(2022, 1, 3),
    base_price: float = 20000.0,
) -> list[CandleData]:
    """Generate n synthetic daily candles with a slight upward drift."""
    candles = []
    price = base_price
    for i in range(n):
        multiplier = 1.001 if i % 2 == 0 else 0.9995
        price *= multiplier
        candles.append(
            CandleData(
                instrument=instrument,
                candle_time=(start + timedelta(days=i)).isoformat(),
                open=round(price * 0.999, 2),
                high=round(price * 1.002, 2),
                low=round(price * 0.997, 2),
                close=round(price, 2),
                volume=100000,
                timeframe=timeframe,
            )
        )
    return candles


def make_indicator(
    instrument: str = "NIFTY 50",
    timeframe: str = "1day",
    candle_time: datetime = datetime(2024, 1, 15, 15, 30),
    ema20: float = 22600.0,
    ema50: float = 22400.0,
    ema200: float = 22000.0,
    rsi14: float = 65.0,
    vwap: float = 22500.0,
    macd: float = 50.0,
    macd_signal: float = 30.0,
) -> IndicatorRecord:
    return IndicatorRecord(
        instrument=instrument,
        candle_time=candle_time,
        timeframe=timeframe,
        ema20=Decimal(str(ema20)),
        ema50=Decimal(str(ema50)),
        ema200=Decimal(str(ema200)),
        rsi14=Decimal(str(rsi14)),
        vwap=Decimal(str(vwap)),
        macd=Decimal(str(macd)),
        macd_signal=Decimal(str(macd_signal)),
    )

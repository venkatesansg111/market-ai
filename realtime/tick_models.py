from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from data_providers.base import CandleData, Timeframe


@dataclass(frozen=True, slots=True)
class TickData:
    """Immutable single-price tick arriving from a market data feed."""

    instrument: str
    tick_time: datetime
    price: Decimal
    volume: int = 0


@dataclass(slots=True)
class CandleDataRealtime:
    """Mutable in-memory OHLCV candle built incrementally from ticks."""

    instrument: str
    timeframe: Timeframe
    candle_open_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int = 0
    tick_count: int = 0
    is_finalized: bool = False

    def update(self, tick: TickData) -> None:
        if self.is_finalized:
            raise RuntimeError(
                f"Cannot update finalized candle {self.instrument} "
                f"{self.candle_open_time}"
            )
        if tick.price > self.high:
            self.high = tick.price
        if tick.price < self.low:
            self.low = tick.price
        self.close = tick.price
        self.volume += tick.volume
        self.tick_count += 1

    def finalize(self) -> None:
        self.is_finalized = True

    def to_candle_data(self) -> CandleData:
        """Convert to the universal CandleData DTO used by bulk_upsert."""
        return CandleData(
            instrument=self.instrument,
            candle_time=self.candle_open_time.isoformat(),
            open=float(self.open),
            high=float(self.high),
            low=float(self.low),
            close=float(self.close),
            volume=self.volume,
            timeframe=self.timeframe.value,
        )

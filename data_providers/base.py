from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Sequence


class Timeframe(str, Enum):
    MIN_1 = "1min"
    MIN_5 = "5min"
    MIN_15 = "15min"
    DAY_1 = "1day"


@dataclass(frozen=True, slots=True)
class CandleData:
    instrument: str
    candle_time: str        # ISO-8601 string; loader converts to datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    timeframe: str


class MarketDataProvider(ABC):
    """Abstract base — swap implementations without touching business logic."""

    @abstractmethod
    def get_historical_data(
        self,
        symbol: str,
        from_date: date,
        to_date: date,
        interval: Timeframe,
    ) -> Sequence[CandleData]:
        """Return a list of CandleData objects for the requested range."""

    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider identifier for logging."""

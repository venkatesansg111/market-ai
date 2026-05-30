from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SignalType(str, Enum):
    """Trade signal classification aligned to the 5-rule spec."""

    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    STRONG_SELL = "STRONG_SELL"
    SELL = "SELL"
    NO_TRADE = "NO_TRADE"


@dataclass(frozen=True)
class ConfidenceComponents:
    """Scored components that sum to the final confidence value.

    Each component score is signed: positive = bullish contribution,
    negative = bearish contribution.

    Ranges:
        ema_score:  [-30, 30]  — full alignment vs partial vs flat
        rsi_score:  [-20, 20]  — momentum confirmation
        vwap_score: [-20, 20]  — price vs VWAP
        macd_score: [-30, 30]  — MACD vs signal line

    confidence = clamp(50 + total // 2, 0, 100)
    This maps [-100, 100] raw score → [0, 100] confidence.
    """

    ema_score: int
    rsi_score: int
    vwap_score: int
    macd_score: int
    reasons: tuple[str, ...]

    @property
    def total(self) -> int:
        return self.ema_score + self.rsi_score + self.vwap_score + self.macd_score

    @property
    def confidence(self) -> int:
        raw = 50 + self.total // 2
        return max(0, min(100, raw))


@dataclass(frozen=True)
class SignalResult:
    """Final output of the signal engine for one (instrument, timeframe, candle_time)."""

    signal_type: SignalType
    confidence: int
    reason: str
    components: ConfidenceComponents

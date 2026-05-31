"""Immutable result models for the Multi-Timeframe Confluence Framework.

ConfluenceComponent — per-timeframe scoring detail.
ConfluenceResult    — aggregate result returned by ConfluenceEngineService.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from signals.signal_models import SignalType


@dataclass(frozen=True, slots=True)
class ConfluenceComponent:
    """Scoring contribution from a single timeframe's indicator rules.

    Attributes:
        timeframe:  Timeframe label (e.g. ``"1day"``, ``"15min"``).
        score:      Raw score for this timeframe. Positive = bullish
                    contribution, negative = bearish, zero = neutral/unavailable.
        bullish:    ``True`` when the net score is positive.
        bearish:    ``True`` when the net score is negative.
        reason:     Human-readable summary of rule evaluations for this timeframe.
    """

    timeframe: str
    score: int
    bullish: bool
    bearish: bool
    reason: str


@dataclass(frozen=True, slots=True)
class ConfluenceResult:
    """Aggregate result produced by :class:`~confluence.confluence_engine.ConfluenceEngineService`.

    Attributes:
        instrument:       Trading instrument (e.g. ``"NIFTY 50"``).
        signal_time:      Candle time of the entry bar that triggered evaluation.
        signal_type:      Derived signal (:class:`~signals.signal_models.SignalType`).
        confidence:       Overall confidence score in the range [0, 100].
                          50 = neutral, >50 = bullish bias, <50 = bearish bias.
        score:            Raw aggregate score across all timeframe components.
                          Range is approximately [-100, +100].
        trend_timeframe:  Label of the trend timeframe (e.g. ``"1day"``).
        setup_timeframe:  Label of the setup timeframe (e.g. ``"15min"``).
        entry_timeframe:  Label of the entry timeframe (e.g. ``"5min"``).
        strategy_name:    Name of the strategy that produced this result.
        reason:           Concatenated reasons from all active components.
        components:       Per-timeframe scoring breakdown, one per rule-set.
    """

    instrument: str
    signal_time: datetime
    signal_type: SignalType
    confidence: int
    score: int
    trend_timeframe: str
    setup_timeframe: str
    entry_timeframe: str
    strategy_name: str
    reason: str
    components: tuple[ConfluenceComponent, ...]

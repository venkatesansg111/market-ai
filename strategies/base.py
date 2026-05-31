from __future__ import annotations

from abc import ABC, abstractmethod

from indicators.indicator_models import IndicatorRecord
from strategies.strategy_models import CandleSnapshot, StrategySignal


class Strategy(ABC):
    """Abstract base for all user-facing trading strategies.

    Strategies are pure: they receive the current bar snapshot and indicator row,
    and return a StrategySignal. They must not write to any database, mutate shared
    state, or access data beyond the arguments passed to generate_signal().

    To add a new strategy:
        1. Subclass Strategy in strategies/<name>.py
        2. Implement all three abstract properties and generate_signal()
        3. Register it in strategies/registry.py

    The three abstract properties serve documentation and validation:
        - strategy_name:        short CLI key (e.g. "ema")
        - description:          human-readable summary for --list-strategies
        - required_indicators:  list of IndicatorRecord field names the strategy reads
    """

    @property
    @abstractmethod
    def strategy_name(self) -> str:
        """Short identifier used as the --strategy CLI value (e.g. 'ema')."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description shown in --list-strategies output."""

    @property
    @abstractmethod
    def required_indicators(self) -> list[str]:
        """IndicatorRecord field names this strategy reads (for docs/validation)."""

    @abstractmethod
    def generate_signal(
        self,
        candle: CandleSnapshot,
        indicators: IndicatorRecord,
    ) -> StrategySignal:
        """Evaluate the current bar and return a StrategySignal.

        Args:
            candle:     OHLCV data for the current bar (no look-ahead).
            indicators: Computed indicators aligned to candle.candle_time.

        Returns:
            StrategySignal with signal_type, confidence (0–100), and reason.
        """

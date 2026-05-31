from __future__ import annotations

from decimal import Decimal

from indicators.indicator_models import IndicatorRecord
from strategies.base import Strategy
from strategies.strategy_models import CandleSnapshot, StrategySignal


class StrategyEngineService:
    """Stateless orchestrator that applies a Strategy to a single bar.

    Responsibilities:
        - Build a CandleSnapshot from current_price + IndicatorRecord metadata
        - Delegate to strategy.generate_signal()
        - Return the resulting StrategySignal

    No persistence. No DB writes. No side effects.
    Callers are responsible for choosing and injecting the Strategy instance.
    """

    def evaluate(
        self,
        strategy: Strategy,
        indicators: IndicatorRecord,
        current_price: Decimal,
    ) -> StrategySignal:
        """Evaluate one strategy against the current bar.

        Args:
            strategy:      Strategy instance to evaluate.
            indicators:    IndicatorRecord for the current bar (no look-ahead).
            current_price: Close price of the current candle.

        Returns:
            StrategySignal produced by the strategy.
        """
        candle = CandleSnapshot(
            instrument=indicators.instrument,
            timeframe=indicators.timeframe,
            candle_time=indicators.candle_time,
            open=current_price,
            high=current_price,
            low=current_price,
            close=current_price,
        )
        return strategy.generate_signal(candle, indicators)

    def evaluate_all(
        self,
        indicators: IndicatorRecord,
        current_price: Decimal,
    ) -> dict[str, StrategySignal]:
        """Evaluate every registered strategy against the current bar.

        Returns:
            Mapping of strategy_name → StrategySignal for all registered strategies.
        """
        from strategies.registry import STRATEGIES

        return {
            name: self.evaluate(strat, indicators, current_price)
            for name, strat in STRATEGIES.items()
        }

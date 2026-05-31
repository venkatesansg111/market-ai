"""Multi-Timeframe Backtest Adapter.

Adapts a :class:`~strategies.multi_timeframe_base.MultiTimeframeStrategy` to
the :class:`~backtesting.strategy_base.Strategy` interface expected by
:class:`~backtesting.backtest_engine.BacktestEngine`.

Responsibilities:
    - Holds pre-loaded indicator lists for all required timeframes.
    - For each entry bar, calls :class:`~confluence.timeframe_alignment.TimeframeAlignmentService`
      to align higher-timeframe data without look-ahead bias.
    - Tracks the previous aligned record per timeframe so that
      history-dependent rules (e.g. OBV direction) have context.
    - Maps ``StrategySignal`` → ``TradeAction`` using position state, identical
      to the logic in :class:`~strategies.backtest_adapter.StrategyBacktestAdapter`.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from backtesting.backtest_models import TradeAction
from backtesting.strategy_base import Strategy as BacktestStrategy
from confluence.timeframe_alignment import TimeframeAlignmentService
from indicators.indicator_models import IndicatorRecord
from signals.signal_models import SignalType
from strategies.multi_timeframe_base import MultiTimeframeStrategy


class MultiTimeframeBacktestAdapter(BacktestStrategy):
    """Backtesting adapter for :class:`MultiTimeframeStrategy` implementations.

    Usage (handled automatically by :class:`~backtesting.backtest_engine.BacktestEngine`)::

        adapter = MultiTimeframeBacktestAdapter(
            strategy=TrendConfluenceStrategy(),
            all_indicators={
                "1day":  [...],   # IndicatorRecord list sorted ascending
                "15min": [...],
                "5min":  [...],
            },
        )

    Signal → TradeAction mapping:
        STRONG_BUY / BUY   → OPEN_LONG   (only when no open position)
        STRONG_SELL / SELL → CLOSE_LONG  (only when a position is open)
        NO_TRADE           → HOLD
    """

    def __init__(
        self,
        strategy: MultiTimeframeStrategy,
        all_indicators: dict[str, list[IndicatorRecord]],
        alignment_service: Optional[TimeframeAlignmentService] = None,
    ) -> None:
        self._strategy = strategy
        # All records sorted ascending by candle_time (invariant required by align()).
        self._all_indicators: dict[str, list[IndicatorRecord]] = {
            tf: sorted(recs, key=lambda r: r.candle_time)
            for tf, recs in all_indicators.items()
        }
        self._alignment = alignment_service or TimeframeAlignmentService()
        self._has_open_position: bool = False
        # Tracks the last aligned record per timeframe for OBV / history rules.
        self._prev_aligned: dict[str, Optional[IndicatorRecord]] = {}

    # ------------------------------------------------------------------
    # BacktestStrategy interface
    # ------------------------------------------------------------------

    def set_position_state(self, has_open_position: bool) -> None:
        self._has_open_position = has_open_position

    def generate_signal(
        self,
        indicator_row: IndicatorRecord,
        current_price: Decimal,
    ) -> TradeAction:
        entry_tf = indicator_row.timeframe
        entry_time = indicator_row.candle_time

        # Align all timeframes to the current entry bar.
        aligned = self._alignment.align(entry_time, entry_tf, self._all_indicators)
        # The entry row itself is authoritative for its timeframe.
        aligned[entry_tf] = indicator_row

        signal = self._strategy.generate_multi_signal(
            aligned_records=aligned,
            current_price=current_price,
            prev_aligned_records=dict(self._prev_aligned),
        )

        # Store aligned records as previous for the next bar.
        self._prev_aligned = {tf: rec for tf, rec in aligned.items()}

        if signal.signal_type in (SignalType.STRONG_BUY, SignalType.BUY):
            return TradeAction.OPEN_LONG if not self._has_open_position else TradeAction.HOLD

        if signal.signal_type in (SignalType.STRONG_SELL, SignalType.SELL):
            return TradeAction.CLOSE_LONG if self._has_open_position else TradeAction.HOLD

        return TradeAction.HOLD

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    @property
    def wrapped_strategy(self) -> MultiTimeframeStrategy:
        """Expose the underlying MTF strategy for testing / inspection."""
        return self._strategy

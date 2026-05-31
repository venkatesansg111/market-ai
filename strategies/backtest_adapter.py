from __future__ import annotations

from decimal import Decimal

from backtesting.backtest_models import TradeAction
from backtesting.strategy_base import Strategy as BacktestStrategy
from indicators.indicator_models import IndicatorRecord
from signals.signal_models import SignalType
from strategies.base import Strategy as BaseStrategy
from strategies.strategy_models import CandleSnapshot


class StrategyBacktestAdapter(BacktestStrategy):
    """Adapts a strategies.base.Strategy into the backtesting.strategy_base.Strategy interface.

    Bridges user-facing strategies (which return StrategySignal) to the backtest
    engine (which expects TradeAction). Maintains position state between bars so
    buy signals are only acted upon when there is no open position, and sell
    signals only when a position exists.

    Signal → TradeAction mapping:
        STRONG_BUY / BUY   → OPEN_LONG   (only when no open position)
        STRONG_SELL / SELL → CLOSE_LONG  (only when position is open)
        NO_TRADE           → HOLD
    """

    def __init__(self, strategy: BaseStrategy) -> None:
        self._strategy = strategy
        self._has_open_position: bool = False

    # Called by BacktestEngine before each bar to sync portfolio state.
    def set_position_state(self, has_open_position: bool) -> None:
        self._has_open_position = has_open_position

    def generate_signal(
        self,
        indicator_row: IndicatorRecord,
        current_price: Decimal,
    ) -> TradeAction:
        candle = CandleSnapshot(
            instrument=indicator_row.instrument,
            timeframe=indicator_row.timeframe,
            candle_time=indicator_row.candle_time,
            open=current_price,
            high=current_price,
            low=current_price,
            close=current_price,
        )
        result = self._strategy.generate_signal(candle, indicator_row)

        if result.signal_type in (SignalType.STRONG_BUY, SignalType.BUY):
            return TradeAction.OPEN_LONG if not self._has_open_position else TradeAction.HOLD

        if result.signal_type in (SignalType.STRONG_SELL, SignalType.SELL):
            return TradeAction.CLOSE_LONG if self._has_open_position else TradeAction.HOLD

        return TradeAction.HOLD

    @property
    def wrapped_strategy(self) -> BaseStrategy:
        """Expose the underlying strategy for inspection."""
        return self._strategy

from __future__ import annotations

from decimal import Decimal

from backtesting.backtest_models import TradeAction
from backtesting.strategy_base import Strategy
from indicators.indicator_models import IndicatorRecord
from signals.signal_engine import SignalEngineService
from signals.signal_models import SignalType


class SignalToTradeAdapter(Strategy):
    """Converts Phase 2 signal engine output into executable trade actions.

    Signal → Action mapping (LONG ONLY):
        STRONG_BUY  → OPEN_LONG   if no open position
        BUY         → OPEN_LONG   if no open position
        STRONG_SELL → CLOSE_LONG  if position exists
        SELL        → CLOSE_LONG  if position exists
        NO_TRADE    → HOLD        always

    The adapter is stateful: call set_position_state() before each bar so it
    knows whether to route buy signals to OPEN or to HOLD (de-dup logic).
    """

    def __init__(self) -> None:
        self._engine = SignalEngineService()
        self._has_open_position: bool = False

    def set_position_state(self, has_open_position: bool) -> None:
        """Sync position state from portfolio before calling generate_signal."""
        self._has_open_position = has_open_position

    def generate_signal(
        self,
        indicator_row: IndicatorRecord,
        current_price: Decimal,
    ) -> TradeAction:
        result = self._engine.evaluate_signal(indicator_row, current_price)

        if result.signal_type in (SignalType.STRONG_BUY, SignalType.BUY):
            return TradeAction.OPEN_LONG if not self._has_open_position else TradeAction.HOLD

        if result.signal_type in (SignalType.STRONG_SELL, SignalType.SELL):
            return TradeAction.CLOSE_LONG if self._has_open_position else TradeAction.HOLD

        return TradeAction.HOLD

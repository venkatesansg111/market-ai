from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from backtesting.backtest_models import TradeAction
from indicators.indicator_models import IndicatorRecord


class Strategy(ABC):
    """Abstract base for all backtesting strategies.

    Implementations receive the current indicator snapshot and market price,
    and return a TradeAction that the execution engine will act upon.

    No implementation should access future data — only the single row
    passed to generate_signal() represents the current moment in time.
    """

    @abstractmethod
    def generate_signal(
        self,
        indicator_row: IndicatorRecord,
        current_price: Decimal,
    ) -> TradeAction:
        """Return a trade action for the current bar.

        Args:
            indicator_row: Indicators computed on candles up to and including
                           the current candle_time (no look-ahead).
            current_price: The close price of the current candle.

        Returns:
            TradeAction.OPEN_LONG  — enter a long position
            TradeAction.CLOSE_LONG — exit the existing long position
            TradeAction.HOLD       — no action
        """

    def on_backtest_start(self) -> None:
        """Called once before the backtest loop begins. Override for setup."""

    def on_backtest_end(self) -> None:
        """Called once after the backtest loop ends. Override for teardown."""

"""Abstract base class for multi-timeframe trading strategies.

Extends :class:`~strategies.base.Strategy` with:
    - Timeframe declarations (trend / setup / entry).
    - :meth:`generate_multi_signal` for multi-timeframe signal generation.
    - A default :meth:`generate_signal` that falls back to entry-timeframe-only
      evaluation, ensuring backward compatibility with the single-timeframe
      :class:`~backtesting.strategy_base.Strategy` interface.

To add a new multi-timeframe strategy:
    1. Subclass :class:`MultiTimeframeStrategy`.
    2. Implement all abstract properties and :meth:`generate_multi_signal`.
    3. Register it in ``strategies/registry.py``.
    4. The :class:`~strategies.backtest_mtf_adapter.MultiTimeframeBacktestAdapter`
       will automatically handle alignment and higher-timeframe data loading.
"""
from __future__ import annotations

from abc import abstractmethod
from decimal import Decimal
from typing import Optional

from indicators.indicator_models import IndicatorRecord
from strategies.base import Strategy
from strategies.strategy_models import CandleSnapshot, StrategySignal


class MultiTimeframeStrategy(Strategy):
    """Abstract base for strategies that analyse multiple timeframes simultaneously.

    Implementors **must** define:
        - :attr:`trend_timeframe` — the macro-trend timeframe (e.g. ``"1day"``).
        - :attr:`setup_timeframe` — the intermediate timeframe (e.g. ``"15min"``).
        - :attr:`entry_timeframe` — the entry-trigger timeframe (e.g. ``"5min"``).
        - :meth:`generate_multi_signal` — the core signal logic.

    Plus the three properties inherited from :class:`~strategies.base.Strategy`:
        - :attr:`strategy_name`
        - :attr:`description`
        - :attr:`required_indicators`
    """

    @property
    @abstractmethod
    def trend_timeframe(self) -> str:
        """Macro-trend timeframe used for directional bias (e.g. ``"1day"``).

        The backtesting adapter will supply the last *completed* candle for this
        timeframe, aligned to each entry bar without look-ahead bias.
        """

    @property
    @abstractmethod
    def setup_timeframe(self) -> str:
        """Intermediate timeframe used for trade setup confirmation (e.g. ``"15min"``)."""

    @property
    @abstractmethod
    def entry_timeframe(self) -> str:
        """Lowest timeframe used to trigger the actual entry (e.g. ``"5min"``)."""

    @abstractmethod
    def generate_multi_signal(
        self,
        aligned_records: dict[str, Optional[IndicatorRecord]],
        current_price: Decimal,
        prev_aligned_records: Optional[dict[str, Optional[IndicatorRecord]]] = None,
    ) -> StrategySignal:
        """Generate a trading signal from aligned multi-timeframe data.

        Args:
            aligned_records:      Dict mapping timeframe string → ``IndicatorRecord``
                                  (or ``None`` if that timeframe has no data available).
                                  Keys include at minimum :attr:`trend_timeframe`,
                                  :attr:`setup_timeframe`, and :attr:`entry_timeframe`.
            current_price:        Closing price of the entry bar.
            prev_aligned_records: Optional dict mapping timeframe → previous bar's
                                  ``IndicatorRecord``. Supplied by the backtesting
                                  adapter for rules that need historical context
                                  (e.g. OBV direction).

        Returns:
            :class:`~strategies.strategy_models.StrategySignal`.
        """

    # ------------------------------------------------------------------
    # Single-timeframe fallback (Strategy ABC requirement)
    # ------------------------------------------------------------------

    def generate_signal(
        self,
        candle: CandleSnapshot,
        indicators: IndicatorRecord,
    ) -> StrategySignal:
        """Single-timeframe fallback for the :class:`~strategies.base.Strategy` interface.

        Constructs an ``aligned_records`` dict with only the entry-timeframe
        record populated (higher timeframes are ``None``).  Delegates to
        :meth:`generate_multi_signal`.

        This allows MTF strategies to be evaluated in single-timeframe contexts
        (e.g. the strategy engine, unit tests) without raising errors, though
        the signals will be weaker as higher-timeframe confluence is absent.
        """
        aligned: dict[str, Optional[IndicatorRecord]] = {
            self.trend_timeframe: None,
            self.setup_timeframe: None,
            self.entry_timeframe: indicators,
        }
        return self.generate_multi_signal(aligned, candle.close)

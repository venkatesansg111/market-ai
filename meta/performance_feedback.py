"""PerformanceFeedback — collect backtest results and feed into the learning system."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from backtesting.backtest_models import BacktestResult
from config import settings
from meta.meta_models import MetaSignal, RegimeType, StrategyPerformanceRecord
from meta.strategy_weights import StrategyWeightsManager
from utils.logger import get_logger

logger = get_logger(__name__, settings.log_dir, settings.log_level)


class PerformanceFeedback:
    """Converts :class:`BacktestResult` objects into :class:`StrategyPerformanceRecord`
    instances and routes them to the :class:`StrategyWeightsManager`.

    Usage::

        feedback = PerformanceFeedback(weights_manager)
        feedback.record(bt_result, meta_signal)
    """

    def __init__(self, weights_manager: StrategyWeightsManager) -> None:
        self._weights = weights_manager

    # ── Public API ────────────────────────────────────────────────────────

    def record(
        self,
        bt_result: BacktestResult,
        strategy_name: Optional[str] = None,
        regime_type: Optional[RegimeType] = None,
        meta_signal: Optional[MetaSignal] = None,
    ) -> StrategyPerformanceRecord:
        """Convert a BacktestResult into a StrategyPerformanceRecord and register it.

        Args:
            bt_result:     Completed backtest.
            strategy_name: Override strategy name (defaults to ``bt_result.strategy_name``).
            regime_type:   The regime the backtest was run under.
            meta_signal:   Optional :class:`MetaSignal`; its regime and strategy are used
                           if *strategy_name* / *regime_type* are omitted.

        Returns:
            The constructed :class:`StrategyPerformanceRecord`.
        """
        s_name = strategy_name or (
            meta_signal.selected_strategy if meta_signal else bt_result.strategy_name
        )
        r_type = regime_type or (
            meta_signal.regime_type if meta_signal else RegimeType.RANGING
        )

        record = self._to_record(bt_result, s_name, r_type)
        self._weights.record_performance(record)

        logger.info(
            "[PerformanceFeedback] Recorded %s in %s: composite=%.4f",
            s_name,
            r_type.value,
            record.composite_score(),
        )
        return record

    def record_batch(
        self,
        results: list[BacktestResult],
        regime_type: RegimeType,
    ) -> list[StrategyPerformanceRecord]:
        """Record multiple backtest results all belonging to the same regime."""
        return [self.record(r, regime_type=regime_type) for r in results]

    # ── Private helpers ───────────────────────────────────────────────────

    @staticmethod
    def _to_record(
        bt: BacktestResult,
        strategy_name: str,
        regime_type: RegimeType,
    ) -> StrategyPerformanceRecord:
        return StrategyPerformanceRecord(
            strategy_name=strategy_name,
            regime_type=regime_type,
            sharpe=float(bt.sharpe_ratio),
            cagr=float(bt.cagr_pct),
            max_drawdown=float(bt.max_drawdown_pct),
            win_rate=float(bt.win_rate_pct),
            expectancy=float(bt.expectancy),
            total_trades=bt.total_trades,
            recorded_at=datetime.utcnow(),
        )

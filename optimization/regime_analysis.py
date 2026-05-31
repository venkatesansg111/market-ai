"""RegimeAnalyzer — detect market regimes and measure strategy performance per regime."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Optional

from backtesting.backtest_models import BacktestConfig, BacktestResult
from config import settings
from optimization.optimization_models import RegimeResult
from optimization.strategy_factory import create_strategy
from strategies.base import Strategy
from utils.logger import get_logger

logger = get_logger(__name__, settings.log_dir, settings.log_level)

# Thresholds for regime classification
_ADX_TRENDING = 25.0
_ADX_RANGING = 20.0
_ATR_HIGH_VOL_RATIO = 1.5
_ATR_LOW_VOL_RATIO = 0.5


@dataclass
class _RegimePeriod:
    """Internal model for a single detected regime period."""
    regime: str
    start: datetime
    end: datetime


BacktestFn = Callable[[BacktestConfig, Strategy], BacktestResult]


def _classify_period(adx_value: float, atr_value: float, mean_atr: float) -> str:
    """Classify a single period into one of four market regimes."""
    atr_ratio = atr_value / mean_atr if mean_atr > 0 else 1.0

    if adx_value > _ADX_TRENDING:
        return "trending"
    if atr_ratio > _ATR_HIGH_VOL_RATIO:
        return "high_volatility"
    if atr_ratio < _ATR_LOW_VOL_RATIO:
        return "low_volatility"
    return "ranging"


class RegimeAnalyzer:
    """Detects market regimes from indicator data and evaluates strategies per regime.

    Regime detection uses monthly ADX and ATR averages:

    * **trending**        — monthly average ADX > 25
    * **high_volatility** — ADX ≤ 25 and ATR ratio > 1.5× historical mean
    * **low_volatility**  — ADX ≤ 25 and ATR ratio < 0.5× historical mean
    * **ranging**         — everything else

    Pass a *backtest_fn* for unit-test injection (avoids real DB calls).
    """

    def __init__(self, backtest_fn: Optional[BacktestFn] = None) -> None:
        self._backtest_fn = backtest_fn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_regimes(
        self,
        instrument: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[_RegimePeriod]:
        """Return a list of regime periods ordered chronologically."""
        rows = self._load_indicators(instrument, timeframe, start_date, end_date)
        return self._classify_regimes(rows)

    def analyze_strategy_by_regime(
        self,
        strategy_name: str,
        instrument: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        starting_capital: Decimal = Decimal("1000000"),
        params: Optional[dict] = None,
    ) -> list[RegimeResult]:
        """Run per-regime backtests and return :class:`RegimeResult` for each period.

        Skips regime periods where the backtest raises an exception.
        """
        regime_periods = self.detect_regimes(instrument, timeframe, start_date, end_date)

        if not regime_periods:
            logger.info(
                "[RegimeAnalyzer] No regime periods detected for %s %s", instrument, timeframe
            )
            return []

        results: list[RegimeResult] = []
        for period in regime_periods:
            try:
                strategy = create_strategy(strategy_name, params or {})
                config = BacktestConfig(
                    instrument=instrument,
                    timeframe=timeframe,
                    start_date=period.start,
                    end_date=period.end,
                    starting_capital=starting_capital,
                    strategy_name=strategy_name,
                )
                bt = self._run_backtest(config, strategy)
                results.append(
                    RegimeResult(
                        strategy_name=strategy_name,
                        instrument=instrument,
                        timeframe=timeframe,
                        regime=period.regime,
                        period_start=period.start,
                        period_end=period.end,
                        cagr=float(bt.cagr_pct),
                        sharpe=float(bt.sharpe_ratio),
                        win_rate=float(bt.win_rate_pct),
                        total_trades=bt.total_trades,
                    )
                )
            except Exception as exc:
                logger.error(
                    "[RegimeAnalyzer] Backtest failed for regime %s (%s → %s): %s",
                    period.regime, period.start.date(), period.end.date(), exc,
                )

        return results

    # ------------------------------------------------------------------
    # Regime classification (pure logic — easy to unit-test)
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_regimes(rows: list[Any]) -> list[_RegimePeriod]:
        """Convert a flat list of indicator rows into labelled regime periods."""
        if not rows:
            return []

        atr_values = [float(r.atr_14) for r in rows if r.atr_14 is not None]
        if not atr_values:
            return []

        mean_atr = sum(atr_values) / len(atr_values)

        # Group by (year, month)
        monthly: dict[tuple[int, int], list] = defaultdict(list)
        for r in rows:
            key = (r.candle_time.year, r.candle_time.month)
            monthly[key].append(r)

        periods: list[_RegimePeriod] = []
        for key in sorted(monthly):
            group = monthly[key]
            adx_vals = [float(r.adx_14) for r in group if r.adx_14 is not None]
            atr_vals = [float(r.atr_14) for r in group if r.atr_14 is not None]

            if not adx_vals or not atr_vals:
                continue

            avg_adx = sum(adx_vals) / len(adx_vals)
            avg_atr = sum(atr_vals) / len(atr_vals)
            regime = _classify_period(avg_adx, avg_atr, mean_atr)

            times = [r.candle_time for r in group]
            periods.append(_RegimePeriod(regime=regime, start=min(times), end=max(times)))

        return periods

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_indicators(
        self,
        instrument: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list:
        from database.connection import get_session
        from database.models import MarketIndicator
        from sqlalchemy import select

        try:
            with get_session() as session:
                rows = session.execute(
                    select(MarketIndicator)
                    .where(
                        MarketIndicator.instrument == instrument,
                        MarketIndicator.timeframe == timeframe,
                        MarketIndicator.candle_time >= start_date,
                        MarketIndicator.candle_time <= end_date,
                        MarketIndicator.adx_14.isnot(None),
                        MarketIndicator.atr_14.isnot(None),
                    )
                    .order_by(MarketIndicator.candle_time.asc())
                ).scalars().all()
            return list(rows)
        except Exception as exc:
            logger.error("[RegimeAnalyzer] Failed to load indicators: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Backtest runner
    # ------------------------------------------------------------------

    def _run_backtest(self, config: BacktestConfig, strategy: Strategy) -> BacktestResult:
        if self._backtest_fn is not None:
            return self._backtest_fn(config, strategy)
        from optimization.strategy_optimizer import OptimizationBacktestEngine
        return OptimizationBacktestEngine(strategy).run(config)

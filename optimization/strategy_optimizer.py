"""StrategyOptimizer — runs backtests across parameter grids and walk-forward windows."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Optional

from backtesting.backtest_engine import BacktestEngine
from backtesting.backtest_models import BacktestConfig, BacktestResult
from config import settings
from optimization.optimization_models import OptimizationResult, OptimizationWindow
from optimization.parameter_grid import ParameterGridGenerator
from optimization.strategy_factory import create_strategy
from optimization.strategy_ranker import StrategyRanker
from optimization.walk_forward import WalkForwardOptimizer
from strategies.base import Strategy
from utils.logger import get_logger

logger = get_logger(__name__, settings.log_dir, settings.log_level)


class OptimizationBacktestEngine(BacktestEngine):
    """BacktestEngine subclass that accepts a pre-built strategy instance.

    Bypasses the strategy registry so the optimizer can inject parameterized
    strategies without mutating shared singletons.
    """

    def __init__(self, strategy: Strategy) -> None:
        super().__init__()
        self._pre_built_strategy = strategy

    def _build_strategy(self, config: BacktestConfig):
        from strategies.backtest_adapter import StrategyBacktestAdapter
        from strategies.multi_timeframe_base import MultiTimeframeStrategy
        from strategies.backtest_mtf_adapter import MultiTimeframeBacktestAdapter
        from confluence.timeframe_alignment import TimeframeAlignmentService

        strat = self._pre_built_strategy

        if isinstance(strat, MultiTimeframeStrategy):
            if config.trend_timeframe:
                strat._trend_tf = config.trend_timeframe
            if config.setup_timeframe:
                strat._setup_tf = config.setup_timeframe
            if config.entry_timeframe:
                strat._entry_tf = config.entry_timeframe

            all_indicators = self._load_mtf_indicators(config, strat)
            return MultiTimeframeBacktestAdapter(
                strategy=strat,
                all_indicators=all_indicators,
                alignment_service=TimeframeAlignmentService(),
            )

        return StrategyBacktestAdapter(strat)


# Type alias for injectable backtest function
BacktestFn = Callable[[BacktestConfig, Strategy], BacktestResult]


class StrategyOptimizer:
    """Runs optimization and walk-forward analysis over parameter grids.

    Pass a *backtest_fn* to override the default ``OptimizationBacktestEngine``
    — useful for injecting mocks in unit tests::

        optimizer = StrategyOptimizer(backtest_fn=lambda cfg, strat: mock_result)
    """

    def __init__(
        self,
        backtest_fn: Optional[BacktestFn] = None,
    ) -> None:
        self._backtest_fn = backtest_fn
        self._grid_gen = ParameterGridGenerator()
        self._wf_optimizer = WalkForwardOptimizer()
        self._ranker = StrategyRanker()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def optimize(
        self,
        strategy_name: str,
        instrument: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        starting_capital: Decimal,
        parameter_grid: Optional[dict[str, list[Any]]] = None,
    ) -> list[OptimizationResult]:
        """Run a backtest for each valid parameter combination.

        Args:
            strategy_name:   Registered strategy key (e.g. ``"momentum"``).
            instrument:      Market instrument (e.g. ``"NIFTY 50"``).
            timeframe:       Primary timeframe (e.g. ``"5min"``).
            start_date:      Backtest start date.
            end_date:        Backtest end date.
            starting_capital: Initial capital.
            parameter_grid:  ``{param_name: [values…]}`` dict.  Defaults to
                             the strategy's built-in default grid.

        Returns:
            List of :class:`OptimizationResult` — one per valid combo.
        """
        grid = parameter_grid if parameter_grid is not None else ParameterGridGenerator.default_grid(strategy_name)
        combos = self._grid_gen.generate(grid)

        if not combos:
            logger.warning("[StrategyOptimizer] No valid parameter combinations for %s", strategy_name)
            return []

        logger.info(
            "[StrategyOptimizer] Optimizing %s | %s %s | %d param combos",
            strategy_name, instrument, timeframe, len(combos),
        )

        results: list[OptimizationResult] = []
        for i, params in enumerate(combos, 1):
            logger.debug("[StrategyOptimizer] Combo %d/%d: %s", i, len(combos), params)
            try:
                strategy = create_strategy(strategy_name, params)
                config = BacktestConfig(
                    instrument=instrument,
                    timeframe=timeframe,
                    start_date=start_date,
                    end_date=end_date,
                    starting_capital=starting_capital,
                    strategy_name=strategy_name,
                )
                bt_result = self._run_backtest(config, strategy)
                results.append(self._to_opt_result(
                    bt_result, strategy_name, instrument, timeframe, params,
                    train_start=None, train_end=None,
                    test_start=start_date, test_end=end_date,
                ))
            except Exception as exc:
                logger.error("[StrategyOptimizer] Combo %s failed: %s", params, exc)

        logger.info("[StrategyOptimizer] Completed %d/%d runs", len(results), len(combos))
        return results

    def walk_forward(
        self,
        strategy_name: str,
        instrument: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        starting_capital: Decimal,
        parameter_grid: Optional[dict[str, list[Any]]] = None,
        window_type: str = "rolling",
        train_months: int = 12,
        test_months: int = 3,
    ) -> list[OptimizationResult]:
        """Walk-forward optimization: find best params on train, evaluate on test.

        For each window, runs the full parameter grid on the training period,
        selects the top-ranked parameter set, then evaluates it on the test period.

        Returns:
            One :class:`OptimizationResult` per walk-forward window (test metrics).
        """
        windows = self._wf_optimizer.generate_windows(
            start_date, end_date, train_months, test_months, window_type
        )

        if not windows:
            logger.warning("[StrategyOptimizer] No walk-forward windows generated — date range too short?")
            return []

        logger.info(
            "[StrategyOptimizer] Walk-forward %s | %d windows | %s",
            strategy_name, len(windows), window_type,
        )

        results: list[OptimizationResult] = []
        for window in windows:
            try:
                wf_result = self._process_window(
                    strategy_name, instrument, timeframe, starting_capital,
                    parameter_grid, window,
                )
                if wf_result is not None:
                    results.append(wf_result)
            except Exception as exc:
                logger.error("[StrategyOptimizer] Window %d failed: %s", window.window_index, exc)

        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _process_window(
        self,
        strategy_name: str,
        instrument: str,
        timeframe: str,
        starting_capital: Decimal,
        parameter_grid: Optional[dict],
        window: OptimizationWindow,
    ) -> Optional[OptimizationResult]:
        train_results = self.optimize(
            strategy_name, instrument, timeframe,
            window.train_start, window.train_end, starting_capital,
            parameter_grid,
        )

        if not train_results:
            logger.warning("[StrategyOptimizer] No training results for window %d", window.window_index)
            return None

        ranked = self._ranker.rank(train_results)
        if not ranked:
            return None

        best_params = ranked[0].parameters
        logger.debug(
            "[StrategyOptimizer] Window %d best params: %s",
            window.window_index, best_params,
        )

        strategy = create_strategy(strategy_name, best_params)
        config = BacktestConfig(
            instrument=instrument,
            timeframe=timeframe,
            start_date=window.test_start,
            end_date=window.test_end,
            starting_capital=starting_capital,
            strategy_name=strategy_name,
        )
        bt_result = self._run_backtest(config, strategy)

        return self._to_opt_result(
            bt_result, strategy_name, instrument, timeframe, best_params,
            train_start=window.train_start, train_end=window.train_end,
            test_start=window.test_start, test_end=window.test_end,
        )

    def _run_backtest(self, config: BacktestConfig, strategy: Strategy) -> BacktestResult:
        if self._backtest_fn is not None:
            return self._backtest_fn(config, strategy)
        return OptimizationBacktestEngine(strategy).run(config)

    @staticmethod
    def _to_opt_result(
        bt: BacktestResult,
        strategy_name: str,
        instrument: str,
        timeframe: str,
        params: dict,
        train_start: Optional[datetime],
        train_end: Optional[datetime],
        test_start: datetime,
        test_end: datetime,
    ) -> OptimizationResult:
        return OptimizationResult(
            run_id=OptimizationResult.new_run_id(),
            strategy_name=strategy_name,
            instrument=instrument,
            timeframe=timeframe,
            parameters=dict(params),
            timeframe_config={},
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
            cagr=float(bt.cagr_pct),
            sharpe=float(bt.sharpe_ratio),
            sortino=float(bt.sortino_ratio),
            max_drawdown=float(bt.max_drawdown_pct),
            profit_factor=float(bt.profit_factor),
            win_rate=float(bt.win_rate_pct),
            expectancy=float(bt.expectancy),
            total_trades=bt.total_trades,
        )

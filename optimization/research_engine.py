"""ResearchEngineService — single orchestration entry point for Phase 5 research."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from config import settings
from optimization.optimization_models import (
    OptimizationResult,
    RankingScore,
    RegimeResult,
    ResearchReport,
)
from optimization.optimization_reporting import OptimizationReporter
from optimization.regime_analysis import RegimeAnalyzer
from optimization.strategy_optimizer import StrategyOptimizer
from optimization.strategy_ranker import StrategyRanker
from utils.logger import get_logger

logger = get_logger(__name__, settings.log_dir, settings.log_level)

_DEFAULT_CAPITAL = Decimal("1000000")


class ResearchEngineService:
    """Orchestrates optimization, walk-forward, regime analysis, ranking, and reporting.

    All dependencies are injectable for unit testing::

        engine = ResearchEngineService(
            optimizer=mock_optimizer,
            ranker=mock_ranker,
            regime_analyzer=mock_analyzer,
            reporter=mock_reporter,
        )
    """

    def __init__(
        self,
        optimizer: Optional[StrategyOptimizer] = None,
        ranker: Optional[StrategyRanker] = None,
        regime_analyzer: Optional[RegimeAnalyzer] = None,
        reporter: Optional[OptimizationReporter] = None,
    ) -> None:
        self._optimizer = optimizer or StrategyOptimizer()
        self._ranker = ranker or StrategyRanker()
        self._regime_analyzer = regime_analyzer or RegimeAnalyzer()
        self._reporter = reporter or OptimizationReporter()

    # ------------------------------------------------------------------
    # Individual run modes
    # ------------------------------------------------------------------

    def run_optimization(
        self,
        strategy_name: str,
        instrument: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        parameter_grid: Optional[dict[str, list[Any]]] = None,
        starting_capital: Optional[Decimal] = None,
    ) -> list[OptimizationResult]:
        """Run parameter optimization for a single strategy."""
        return self._optimizer.optimize(
            strategy_name=strategy_name,
            instrument=instrument,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            starting_capital=starting_capital or _DEFAULT_CAPITAL,
            parameter_grid=parameter_grid,
        )

    def run_walk_forward(
        self,
        strategy_name: str,
        instrument: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        window_type: str = "rolling",
        train_months: int = 12,
        test_months: int = 3,
        parameter_grid: Optional[dict[str, list[Any]]] = None,
        starting_capital: Optional[Decimal] = None,
    ) -> list[OptimizationResult]:
        """Run walk-forward optimization for a single strategy."""
        return self._optimizer.walk_forward(
            strategy_name=strategy_name,
            instrument=instrument,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            starting_capital=starting_capital or _DEFAULT_CAPITAL,
            parameter_grid=parameter_grid,
            window_type=window_type,
            train_months=train_months,
            test_months=test_months,
        )

    def run_regime_analysis(
        self,
        strategy_name: str,
        instrument: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[RegimeResult]:
        """Detect market regimes and evaluate strategy performance per regime."""
        return self._regime_analyzer.analyze_strategy_by_regime(
            strategy_name=strategy_name,
            instrument=instrument,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
        )

    def rank_results(self, results: list[OptimizationResult]) -> list[RankingScore]:
        """Return ranked scores for a set of optimization results."""
        return self._ranker.rank(results)

    # ------------------------------------------------------------------
    # Full research run
    # ------------------------------------------------------------------

    def run_full_research(
        self,
        instrument: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        strategies: Optional[list[str]] = None,
        parameter_grids: Optional[dict[str, dict]] = None,
        starting_capital: Optional[Decimal] = None,
        train_months: int = 12,
        test_months: int = 3,
        window_type: str = "rolling",
    ) -> ResearchReport:
        """Run the full research pipeline across all specified strategies.

        Steps performed:
        1. Parameter optimization (all strategies)
        2. Walk-forward optimization (all strategies)
        3. Regime analysis (all strategies)
        4. Strategy ranking
        5. Build ResearchReport

        Args:
            instrument:      Market instrument (e.g. ``"NIFTY 50"``).
            timeframe:       Primary timeframe (e.g. ``"5min"``).
            start_date:      Analysis period start.
            end_date:        Analysis period end.
            strategies:      Strategy names to test. Defaults to all registered strategies.
            parameter_grids: Per-strategy custom grids. Missing entries use defaults.
            starting_capital: Initial capital. Defaults to 1,000,000.
            train_months:    Walk-forward training window length.
            test_months:     Walk-forward test window length.
            window_type:     ``"rolling"`` or ``"expanding"``.

        Returns:
            :class:`ResearchReport` with all findings consolidated.
        """
        if strategies is None:
            from strategies.registry import list_strategies
            strategies = list_strategies()

        capital = starting_capital or _DEFAULT_CAPITAL
        grids = parameter_grids or {}

        all_opt: list[OptimizationResult] = []
        all_wf: list[OptimizationResult] = []
        all_regime: list[RegimeResult] = []

        for strat_name in strategies:
            logger.info("[ResearchEngine] Processing strategy: %s", strat_name)
            grid = grids.get(strat_name)

            try:
                opt = self.run_optimization(
                    strat_name, instrument, timeframe,
                    start_date, end_date, grid, capital,
                )
                all_opt.extend(opt)
            except Exception as exc:
                logger.error("[ResearchEngine] Optimization failed for %s: %s", strat_name, exc)

            try:
                wf = self.run_walk_forward(
                    strat_name, instrument, timeframe,
                    start_date, end_date, window_type, train_months, test_months, grid, capital,
                )
                all_wf.extend(wf)
            except Exception as exc:
                logger.error("[ResearchEngine] Walk-forward failed for %s: %s", strat_name, exc)

            try:
                regime = self.run_regime_analysis(
                    strat_name, instrument, timeframe, start_date, end_date
                )
                all_regime.extend(regime)
            except Exception as exc:
                logger.error("[ResearchEngine] Regime analysis failed for %s: %s", strat_name, exc)

        rankings = self._ranker.rank(all_opt) if all_opt else []

        report = ResearchReport(
            title="Market AI Research Report",
            generated_at=datetime.utcnow(),
            instrument=instrument,
            timeframe=timeframe,
            analysis_start=start_date,
            analysis_end=end_date,
            strategy_rankings=rankings,
            regime_results=all_regime,
            optimization_results=all_opt,
            walk_forward_results=all_wf,
            parameter_winners=self._extract_winners(rankings),
            summary=self._build_summary(rankings, all_regime, all_opt, all_wf),
        )

        logger.info(
            "[ResearchEngine] Research complete — %d opt results, %d wf results, "
            "%d regime results, %d rankings",
            len(all_opt), len(all_wf), len(all_regime), len(rankings),
        )
        return report

    def save_report(self, report: ResearchReport, output_dir: Optional[Path] = None) -> dict[str, Path]:
        """Persist *report* to *output_dir* (defaults to ``reports/research/``)."""
        target = Path(output_dir) if output_dir else Path(settings.reports_dir) / "research"
        return self._reporter.save_all(report, target)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_winners(rankings: list[RankingScore]) -> dict[str, Any]:
        """Return the best parameter set per strategy name."""
        winners: dict[str, Any] = {}
        for rs in rankings:
            if rs.strategy_name not in winners:
                winners[rs.strategy_name] = rs.parameters
        return winners

    @staticmethod
    def _build_summary(
        rankings: list[RankingScore],
        regime_results: list[RegimeResult],
        opt_results: list[OptimizationResult],
        wf_results: list[OptimizationResult],
    ) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "total_optimization_runs": len(opt_results),
            "total_walk_forward_windows": len(wf_results),
            "total_regime_periods": len(regime_results),
            "strategies_ranked": len({rs.strategy_name for rs in rankings}),
        }
        if rankings:
            best = rankings[0]
            summary["best_strategy"] = best.strategy_name
            summary["best_composite_score"] = best.composite_score
            summary["best_cagr"] = best.cagr
            summary["best_sharpe"] = best.sharpe

        if regime_results:
            regimes_seen = {rr.regime for rr in regime_results}
            summary["regimes_detected"] = sorted(regimes_seen)
            best_trending = max(
                (rr for rr in regime_results if rr.regime == "trending"),
                key=lambda r: r.cagr, default=None,
            )
            if best_trending:
                summary["best_trending_strategy"] = best_trending.strategy_name

        return summary

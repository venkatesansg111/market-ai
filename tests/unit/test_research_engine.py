"""Unit tests for ResearchEngineService — all dependencies injected via mocks."""
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from optimization.optimization_models import (
    OptimizationResult,
    RankingScore,
    RegimeResult,
    ResearchReport,
)
from optimization.research_engine import ResearchEngineService


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _opt_result(strategy_name="strat_a", cagr=10.0) -> OptimizationResult:
    return OptimizationResult(
        run_id="r1",
        strategy_name=strategy_name,
        instrument="TEST",
        timeframe="5min",
        parameters={"rsi_buy_threshold": 60},
        timeframe_config={},
        train_start=None,
        train_end=None,
        test_start=datetime(2023, 1, 1),
        test_end=datetime(2024, 1, 1),
        cagr=cagr,
        sharpe=1.0,
        sortino=1.5,
        max_drawdown=5.0,
        profit_factor=1.5,
        win_rate=55.0,
        expectancy=100.0,
        total_trades=50,
    )


def _ranking(strategy_name="strat_a", rank=1) -> RankingScore:
    return RankingScore(
        rank=rank,
        strategy_name=strategy_name,
        parameters={"rsi_buy_threshold": 60},
        composite_score=0.8,
        cagr=10.0,
        sharpe=1.0,
        sortino=1.5,
        profit_factor=1.5,
        win_rate=55.0,
        max_drawdown=5.0,
    )


def _regime_result(strategy_name="strat_a", regime="trending") -> RegimeResult:
    return RegimeResult(
        strategy_name=strategy_name,
        instrument="TEST",
        timeframe="5min",
        regime=regime,
        period_start=datetime(2023, 1, 1),
        period_end=datetime(2023, 3, 31),
        cagr=12.0,
        sharpe=1.2,
        win_rate=58.0,
        total_trades=20,
    )


def _make_engine(
    opt_results=None,
    wf_results=None,
    regime_results=None,
    rankings=None,
) -> ResearchEngineService:
    optimizer = MagicMock()
    optimizer.optimize.return_value = opt_results or [_opt_result()]
    optimizer.walk_forward.return_value = wf_results or [_opt_result()]

    ranker = MagicMock()
    ranker.rank.return_value = rankings or [_ranking()]

    regime_analyzer = MagicMock()
    regime_analyzer.analyze_strategy_by_regime.return_value = regime_results or [_regime_result()]

    reporter = MagicMock()
    reporter.save_all.return_value = {"json": Path("report.json"), "csv": Path("report.csv"), "markdown": Path("report.md")}

    return ResearchEngineService(
        optimizer=optimizer,
        ranker=ranker,
        regime_analyzer=regime_analyzer,
        reporter=reporter,
    )


# ──────────────────────────────────────────────────────────────────────
# Individual run modes
# ──────────────────────────────────────────────────────────────────────

class TestRunOptimization:
    def test_delegates_to_optimizer(self):
        engine = _make_engine()
        result = engine.run_optimization(
            "strat_a", "TEST", "5min",
            datetime(2023, 1, 1), datetime(2024, 1, 1),
        )
        assert len(result) == 1
        engine._optimizer.optimize.assert_called_once()

    def test_returns_list(self):
        engine = _make_engine()
        result = engine.run_optimization(
            "strat_a", "TEST", "5min",
            datetime(2023, 1, 1), datetime(2024, 1, 1),
        )
        assert isinstance(result, list)


class TestRunWalkForward:
    def test_delegates_to_optimizer_walk_forward(self):
        engine = _make_engine()
        result = engine.run_walk_forward(
            "strat_a", "TEST", "5min",
            datetime(2023, 1, 1), datetime(2024, 1, 1),
        )
        engine._optimizer.walk_forward.assert_called_once()
        assert isinstance(result, list)


class TestRunRegimeAnalysis:
    def test_delegates_to_regime_analyzer(self):
        engine = _make_engine()
        result = engine.run_regime_analysis(
            "strat_a", "TEST", "5min",
            datetime(2023, 1, 1), datetime(2024, 1, 1),
        )
        engine._regime_analyzer.analyze_strategy_by_regime.assert_called_once()
        assert isinstance(result, list)


class TestRankResults:
    def test_delegates_to_ranker(self):
        engine = _make_engine()
        opt_results = [_opt_result()]
        result = engine.rank_results(opt_results)
        engine._ranker.rank.assert_called_once_with(opt_results)
        assert isinstance(result, list)


# ──────────────────────────────────────────────────────────────────────
# Full research run
# ──────────────────────────────────────────────────────────────────────

class TestRunFullResearch:
    def test_returns_research_report(self):
        engine = _make_engine()
        report = engine.run_full_research(
            "TEST", "5min",
            datetime(2023, 1, 1), datetime(2024, 1, 1),
            strategies=["strat_a"],
        )
        assert isinstance(report, ResearchReport)

    def test_report_has_optimization_results(self):
        opt = [_opt_result("strat_a", cagr=15.0)]
        engine = _make_engine(opt_results=opt)
        report = engine.run_full_research(
            "TEST", "5min",
            datetime(2023, 1, 1), datetime(2024, 1, 1),
            strategies=["strat_a"],
        )
        assert len(report.optimization_results) == 1

    def test_report_has_walk_forward_results(self):
        wf = [_opt_result("strat_a")]
        engine = _make_engine(wf_results=wf)
        report = engine.run_full_research(
            "TEST", "5min",
            datetime(2023, 1, 1), datetime(2024, 1, 1),
            strategies=["strat_a"],
        )
        assert len(report.walk_forward_results) == 1

    def test_report_has_regime_results(self):
        regime = [_regime_result()]
        engine = _make_engine(regime_results=regime)
        report = engine.run_full_research(
            "TEST", "5min",
            datetime(2023, 1, 1), datetime(2024, 1, 1),
            strategies=["strat_a"],
        )
        assert len(report.regime_results) == 1

    def test_report_has_rankings(self):
        engine = _make_engine(rankings=[_ranking("strat_a", rank=1)])
        report = engine.run_full_research(
            "TEST", "5min",
            datetime(2023, 1, 1), datetime(2024, 1, 1),
            strategies=["strat_a"],
        )
        assert len(report.strategy_rankings) > 0

    def test_multiple_strategies_processed(self):
        engine = _make_engine()
        report = engine.run_full_research(
            "TEST", "5min",
            datetime(2023, 1, 1), datetime(2024, 1, 1),
            strategies=["strat_a", "strat_b"],
        )
        assert engine._optimizer.optimize.call_count == 2

    def test_optimizer_exception_does_not_abort_run(self):
        optimizer = MagicMock()
        optimizer.optimize.side_effect = RuntimeError("DB failure")
        optimizer.walk_forward.return_value = []

        ranker = MagicMock()
        ranker.rank.return_value = []

        regime_analyzer = MagicMock()
        regime_analyzer.analyze_strategy_by_regime.return_value = []

        reporter = MagicMock()
        engine = ResearchEngineService(
            optimizer=optimizer,
            ranker=ranker,
            regime_analyzer=regime_analyzer,
            reporter=reporter,
        )
        report = engine.run_full_research(
            "TEST", "5min",
            datetime(2023, 1, 1), datetime(2024, 1, 1),
            strategies=["strat_a"],
        )
        assert isinstance(report, ResearchReport)
        assert report.optimization_results == []

    def test_summary_contains_expected_keys(self):
        engine = _make_engine()
        report = engine.run_full_research(
            "TEST", "5min",
            datetime(2023, 1, 1), datetime(2024, 1, 1),
            strategies=["strat_a"],
        )
        assert "total_optimization_runs" in report.summary
        assert "total_walk_forward_windows" in report.summary
        assert "strategies_ranked" in report.summary

    def test_parameter_winners_populated(self):
        engine = _make_engine(rankings=[_ranking("strat_a", rank=1)])
        report = engine.run_full_research(
            "TEST", "5min",
            datetime(2023, 1, 1), datetime(2024, 1, 1),
            strategies=["strat_a"],
        )
        assert "strat_a" in report.parameter_winners


# ──────────────────────────────────────────────────────────────────────
# save_report
# ──────────────────────────────────────────────────────────────────────

class TestSaveReport:
    def test_delegates_to_reporter(self):
        engine = _make_engine()
        report = ResearchReport(
            title="Test",
            generated_at=datetime(2024, 1, 1),
            instrument="TEST",
            timeframe="5min",
            analysis_start=datetime(2023, 1, 1),
            analysis_end=datetime(2024, 1, 1),
            strategy_rankings=[],
            regime_results=[],
            optimization_results=[],
            walk_forward_results=[],
            parameter_winners={},
            summary={},
        )
        paths = engine.save_report(report, Path("/tmp/test_reports"))
        engine._reporter.save_all.assert_called_once()
        assert isinstance(paths, dict)

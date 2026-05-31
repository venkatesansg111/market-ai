"""Unit tests for StrategyRanker."""
from datetime import datetime

import pytest

from optimization.optimization_models import OptimizationResult
from optimization.strategy_ranker import StrategyRanker, _normalize


def _make_result(
    strategy_name="strat_a",
    cagr=10.0,
    sharpe=1.0,
    sortino=1.5,
    max_drawdown=5.0,
    profit_factor=1.5,
    win_rate=55.0,
) -> OptimizationResult:
    return OptimizationResult(
        run_id="test-id",
        strategy_name=strategy_name,
        instrument="TEST",
        timeframe="5min",
        parameters={},
        timeframe_config={},
        train_start=None,
        train_end=None,
        test_start=datetime(2023, 1, 1),
        test_end=datetime(2024, 1, 1),
        cagr=cagr,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=max_drawdown,
        profit_factor=profit_factor,
        win_rate=win_rate,
        expectancy=100.0,
        total_trades=50,
    )


class TestNormalize:
    def test_basic_normalization(self):
        result = _normalize([0.0, 50.0, 100.0])
        assert result == [0.0, 0.5, 1.0]

    def test_all_equal_returns_half(self):
        result = _normalize([5.0, 5.0, 5.0])
        assert result == [0.5, 0.5, 0.5]

    def test_empty_returns_empty(self):
        assert _normalize([]) == []

    def test_invert(self):
        result = _normalize([0.0, 100.0], invert=True)
        assert result == [1.0, 0.0]

    def test_single_value_all_equal(self):
        result = _normalize([42.0])
        assert result == [0.5]


class TestStrategyRankerRank:
    def setup_method(self):
        self.ranker = StrategyRanker()

    def test_empty_returns_empty(self):
        assert self.ranker.rank([]) == []

    def test_single_result(self):
        r = _make_result()
        rankings = self.ranker.rank([r])
        assert len(rankings) == 1
        assert rankings[0].rank == 1
        assert rankings[0].strategy_name == "strat_a"

    def test_higher_cagr_ranks_first(self):
        low = _make_result(strategy_name="low", cagr=5.0, sharpe=1.0, sortino=1.0,
                           max_drawdown=5.0, profit_factor=1.2, win_rate=50.0)
        high = _make_result(strategy_name="high", cagr=30.0, sharpe=1.0, sortino=1.0,
                            max_drawdown=5.0, profit_factor=1.2, win_rate=50.0)
        rankings = self.ranker.rank([low, high])
        assert rankings[0].strategy_name == "high"
        assert rankings[1].strategy_name == "low"

    def test_lower_drawdown_ranks_higher_when_else_equal(self):
        big_dd = _make_result(strategy_name="big_dd", max_drawdown=30.0)
        small_dd = _make_result(strategy_name="small_dd", max_drawdown=5.0)
        rankings = self.ranker.rank([big_dd, small_dd])
        assert rankings[0].strategy_name == "small_dd"

    def test_ranks_are_sequential(self):
        results = [_make_result(strategy_name=f"s{i}", cagr=float(i)) for i in range(5)]
        rankings = self.ranker.rank(results)
        assert [r.rank for r in rankings] == [1, 2, 3, 4, 5]

    def test_composite_score_between_0_and_1(self):
        results = [_make_result(strategy_name=f"s{i}", cagr=float(i * 5)) for i in range(3)]
        rankings = self.ranker.rank(results)
        for r in rankings:
            assert 0.0 <= r.composite_score <= 1.0

    def test_composite_score_rounded_to_6_places(self):
        results = [_make_result(strategy_name=f"s{i}", cagr=float(i)) for i in range(3)]
        rankings = self.ranker.rank(results)
        for r in rankings:
            assert r.composite_score == round(r.composite_score, 6)

    def test_parameters_copied(self):
        params = {"rsi_buy_threshold": 60}
        r = OptimizationResult(
            run_id="x",
            strategy_name="s",
            instrument="T",
            timeframe="5min",
            parameters=params,
            timeframe_config={},
            train_start=None,
            train_end=None,
            test_start=datetime(2023, 1, 1),
            test_end=datetime(2024, 1, 1),
            cagr=10.0,
            sharpe=1.0,
            sortino=1.0,
            max_drawdown=5.0,
            profit_factor=1.2,
            win_rate=50.0,
            expectancy=100.0,
            total_trades=10,
        )
        rankings = self.ranker.rank([r])
        assert rankings[0].parameters == params


class TestStrategyRankerTopWorst:
    def setup_method(self):
        self.ranker = StrategyRanker()
        self.results = [
            _make_result(strategy_name=f"s{i}", cagr=float(i * 10))
            for i in range(1, 8)
        ]

    def test_top_n_returns_n(self):
        top = self.ranker.top_n(self.results, n=3)
        assert len(top) == 3

    def test_top_n_best_first(self):
        top = self.ranker.top_n(self.results, n=3)
        assert top[0].rank == 1

    def test_worst_n_returns_n(self):
        worst = self.ranker.worst_n(self.results, n=3)
        assert len(worst) == 3

    def test_worst_n_lowest_score_first(self):
        worst = self.ranker.worst_n(self.results, n=3)
        assert worst[0].rank == len(self.results)


class TestStableStrategies:
    def setup_method(self):
        self.ranker = StrategyRanker()

    def test_returns_at_most_top_n(self):
        results = [
            _make_result(strategy_name=f"s{i % 3}", cagr=float(i))
            for i in range(9)
        ]
        stable = self.ranker.stable_strategies(results, top_n=2)
        assert len(stable) <= 2

    def test_single_result_per_strategy_cv_zero(self):
        results = [
            _make_result(strategy_name="only_one", cagr=10.0)
        ]
        stable = self.ranker.stable_strategies(results)
        assert len(stable) == 1

    def test_empty_returns_empty(self):
        assert self.ranker.stable_strategies([]) == []

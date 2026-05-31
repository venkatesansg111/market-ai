"""Unit tests for StrategyOptimizer — uses injected backtest_fn to avoid DB."""
from datetime import datetime
from decimal import Decimal

import pytest

from backtesting.backtest_models import BacktestResult
from optimization.optimization_models import OptimizationResult
from optimization.strategy_optimizer import StrategyOptimizer


def _mock_bt_result(cagr=10.0, sharpe=1.0) -> BacktestResult:
    return BacktestResult(
        run_name="",
        strategy_name="momentum",
        instrument="TEST",
        timeframe="5min",
        start_date=datetime(2023, 1, 1),
        end_date=datetime(2024, 1, 1),
        starting_capital=Decimal("1000000"),
        ending_capital=Decimal("1100000"),
        total_return_pct=Decimal(str(cagr)),
        cagr_pct=Decimal(str(cagr)),
        win_rate_pct=Decimal("55.0"),
        profit_factor=Decimal("1.5"),
        max_drawdown_pct=Decimal("5.0"),
        sharpe_ratio=Decimal(str(sharpe)),
        sortino_ratio=Decimal("1.5"),
        calmar_ratio=Decimal("1.0"),
        expectancy=Decimal("100.0"),
        total_trades=50,
        winning_trades=28,
        losing_trades=22,
        avg_winner=Decimal("200"),
        avg_loser=Decimal("100"),
        avg_holding_minutes=Decimal("30"),
        longest_win_streak=5,
        longest_loss_streak=3,
        recovery_factor=Decimal("2.0"),
        equity_curve=[],
        trades=[],
        monthly_returns={},
        yearly_returns={},
    )


def _make_optimizer(cagr=10.0, sharpe=1.0) -> StrategyOptimizer:
    return StrategyOptimizer(backtest_fn=lambda cfg, strat: _mock_bt_result(cagr, sharpe))


START = datetime(2022, 1, 1)
END = datetime(2024, 6, 30)
CAPITAL = Decimal("1000000")


class TestOptimize:
    def test_returns_list_of_results(self):
        optimizer = _make_optimizer()
        results = optimizer.optimize("momentum", "TEST", "5min", START, END, CAPITAL)
        assert isinstance(results, list)
        assert len(results) > 0

    def test_results_are_optimization_result_type(self):
        optimizer = _make_optimizer()
        results = optimizer.optimize("momentum", "TEST", "5min", START, END, CAPITAL)
        for r in results:
            assert isinstance(r, OptimizationResult)

    def test_metrics_transferred_correctly(self):
        optimizer = _make_optimizer(cagr=25.0, sharpe=2.0)
        results = optimizer.optimize("momentum", "TEST", "5min", START, END, CAPITAL)
        r = results[0]
        assert r.cagr == pytest.approx(25.0)
        assert r.sharpe == pytest.approx(2.0)

    def test_strategy_name_and_instrument_set(self):
        optimizer = _make_optimizer()
        results = optimizer.optimize("momentum", "NIFTY 50", "5min", START, END, CAPITAL)
        for r in results:
            assert r.strategy_name == "momentum"
            assert r.instrument == "NIFTY 50"

    def test_custom_grid_used(self):
        optimizer = _make_optimizer()
        grid = {"rsi_buy_threshold": [60, 65], "rsi_sell_threshold": [40]}
        results = optimizer.optimize("momentum", "TEST", "5min", START, END, CAPITAL, grid)
        assert len(results) == 2

    def test_invalid_grid_all_filtered_returns_empty(self):
        optimizer = _make_optimizer()
        grid = {"ema_fast": [20], "ema_slow": [10]}
        results = optimizer.optimize("ema", "TEST", "5min", START, END, CAPITAL, grid)
        assert results == []

    def test_train_start_end_none_for_single_optimization(self):
        optimizer = _make_optimizer()
        results = optimizer.optimize("momentum", "TEST", "5min", START, END, CAPITAL)
        for r in results:
            assert r.train_start is None
            assert r.train_end is None

    def test_test_start_end_match_input(self):
        optimizer = _make_optimizer()
        results = optimizer.optimize("momentum", "TEST", "5min", START, END, CAPITAL)
        for r in results:
            assert r.test_start == START
            assert r.test_end == END


class TestWalkForward:
    def test_returns_list_of_results(self):
        optimizer = _make_optimizer()
        results = optimizer.walk_forward("momentum", "TEST", "5min", START, END, CAPITAL)
        assert isinstance(results, list)
        assert len(results) > 0

    def test_each_result_has_train_metadata(self):
        optimizer = _make_optimizer()
        results = optimizer.walk_forward("momentum", "TEST", "5min", START, END, CAPITAL)
        for r in results:
            assert r.train_start is not None
            assert r.train_end is not None

    def test_short_date_range_returns_empty(self):
        optimizer = _make_optimizer()
        start = datetime(2023, 1, 1)
        end = datetime(2023, 6, 1)
        results = optimizer.walk_forward("momentum", "TEST", "5min", start, end, CAPITAL)
        assert results == []

    def test_expanding_produces_results(self):
        optimizer = _make_optimizer()
        results = optimizer.walk_forward(
            "momentum", "TEST", "5min", START, END, CAPITAL,
            window_type="expanding",
        )
        assert len(results) > 0

"""Unit tests for RegimeAnalyzer — uses mock rows and injectable backtest_fn."""
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backtesting.backtest_models import BacktestResult
from optimization.regime_analysis import RegimeAnalyzer, _classify_period


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _row(candle_time: datetime, adx: float, atr: float):
    return SimpleNamespace(candle_time=candle_time, adx_14=adx, atr_14=atr)


def _mock_bt_result(cagr=10.0, sharpe=1.0) -> BacktestResult:
    return BacktestResult(
        run_name="",
        strategy_name="momentum",
        instrument="TEST",
        timeframe="5min",
        start_date=datetime(2023, 1, 1),
        end_date=datetime(2023, 3, 31),
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
        total_trades=30,
        winning_trades=16,
        losing_trades=14,
        avg_winner=Decimal("200"),
        avg_loser=Decimal("100"),
        avg_holding_minutes=Decimal("30"),
        longest_win_streak=4,
        longest_loss_streak=3,
        recovery_factor=Decimal("2.0"),
        equity_curve=[],
        trades=[],
        monthly_returns={},
        yearly_returns={},
    )


# ──────────────────────────────────────────────────────────────────────
# _classify_period
# ──────────────────────────────────────────────────────────────────────

class TestClassifyPeriod:
    def test_trending_high_adx(self):
        assert _classify_period(30.0, 100.0, 100.0) == "trending"

    def test_high_volatility(self):
        assert _classify_period(20.0, 200.0, 100.0) == "high_volatility"

    def test_low_volatility(self):
        assert _classify_period(20.0, 30.0, 100.0) == "low_volatility"

    def test_ranging(self):
        assert _classify_period(15.0, 100.0, 100.0) == "ranging"

    def test_mean_atr_zero_defaults_to_1(self):
        # atr_value / mean_atr where mean_atr=0 defaults to 1.0 (no high/low vol)
        assert _classify_period(15.0, 0.0, 0.0) == "ranging"

    def test_exactly_at_adx_threshold(self):
        # ADX > 25 is trending, so 25.0 is NOT trending
        assert _classify_period(25.0, 100.0, 100.0) != "trending"

    def test_adx_26_is_trending(self):
        assert _classify_period(26.0, 100.0, 100.0) == "trending"


# ──────────────────────────────────────────────────────────────────────
# RegimeAnalyzer._classify_regimes
# ──────────────────────────────────────────────────────────────────────

class TestClassifyRegimes:
    def test_empty_rows_returns_empty(self):
        assert RegimeAnalyzer._classify_regimes([]) == []

    def test_all_none_atr_returns_empty(self):
        rows = [_row(datetime(2023, 1, 15), adx=20.0, atr=None)]
        # atr is None — should be skipped
        result = RegimeAnalyzer._classify_regimes(rows)
        assert result == []

    def test_single_month_produces_one_period(self):
        rows = [
            _row(datetime(2023, 1, 10), adx=30.0, atr=100.0),
            _row(datetime(2023, 1, 20), adx=30.0, atr=100.0),
        ]
        result = RegimeAnalyzer._classify_regimes(rows)
        assert len(result) == 1
        assert result[0].regime == "trending"

    def test_two_months_produce_two_periods(self):
        rows = [
            _row(datetime(2023, 1, 10), adx=30.0, atr=100.0),
            _row(datetime(2023, 2, 10), adx=15.0, atr=100.0),
        ]
        result = RegimeAnalyzer._classify_regimes(rows)
        assert len(result) == 2

    def test_period_start_is_min_candle_time(self):
        rows = [
            _row(datetime(2023, 1, 5), adx=30.0, atr=100.0),
            _row(datetime(2023, 1, 15), adx=30.0, atr=100.0),
            _row(datetime(2023, 1, 25), adx=30.0, atr=100.0),
        ]
        result = RegimeAnalyzer._classify_regimes(rows)
        assert result[0].start == datetime(2023, 1, 5)
        assert result[0].end == datetime(2023, 1, 25)


# ──────────────────────────────────────────────────────────────────────
# RegimeAnalyzer.analyze_strategy_by_regime (injectable backtest_fn)
# ──────────────────────────────────────────────────────────────────────

class TestAnalyzeStrategyByRegime:
    def _make_analyzer(self, rows, bt_result=None):
        analyzer = RegimeAnalyzer(backtest_fn=lambda cfg, strat: bt_result or _mock_bt_result())
        analyzer._load_indicators = MagicMock(return_value=rows)
        return analyzer

    def test_no_rows_returns_empty(self):
        analyzer = self._make_analyzer([])
        result = analyzer.analyze_strategy_by_regime(
            "momentum", "TEST", "5min",
            datetime(2023, 1, 1), datetime(2023, 12, 31),
        )
        assert result == []

    def test_returns_regime_results(self):
        rows = [_row(datetime(2023, 1, 10), adx=30.0, atr=100.0)]
        analyzer = self._make_analyzer(rows)
        results = analyzer.analyze_strategy_by_regime(
            "momentum", "TEST", "5min",
            datetime(2023, 1, 1), datetime(2023, 12, 31),
        )
        assert len(results) == 1

    def test_regime_result_has_correct_regime(self):
        rows = [_row(datetime(2023, 1, 10), adx=30.0, atr=100.0)]
        analyzer = self._make_analyzer(rows)
        results = analyzer.analyze_strategy_by_regime(
            "momentum", "TEST", "5min",
            datetime(2023, 1, 1), datetime(2023, 12, 31),
        )
        assert results[0].regime == "trending"

    def test_cagr_transferred_from_backtest(self):
        rows = [_row(datetime(2023, 1, 10), adx=30.0, atr=100.0)]
        bt = _mock_bt_result(cagr=22.5)
        analyzer = self._make_analyzer(rows, bt)
        results = analyzer.analyze_strategy_by_regime(
            "momentum", "TEST", "5min",
            datetime(2023, 1, 1), datetime(2023, 12, 31),
        )
        assert results[0].cagr == pytest.approx(22.5)

    def test_backtest_exception_skips_period(self):
        rows = [
            _row(datetime(2023, 1, 10), adx=30.0, atr=100.0),
            _row(datetime(2023, 2, 10), adx=30.0, atr=100.0),
        ]
        call_count = [0]

        def failing_fn(cfg, strat):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("DB error")
            return _mock_bt_result()

        analyzer = RegimeAnalyzer(backtest_fn=failing_fn)
        analyzer._load_indicators = MagicMock(return_value=rows)
        results = analyzer.analyze_strategy_by_regime(
            "momentum", "TEST", "5min",
            datetime(2023, 1, 1), datetime(2023, 12, 31),
        )
        assert len(results) == 1

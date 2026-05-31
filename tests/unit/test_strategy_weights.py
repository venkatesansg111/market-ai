"""Unit tests for StrategyWeightsManager."""
from datetime import datetime

import pytest

from meta.meta_models import RegimeType, StrategyPerformanceRecord
from meta.strategy_weights import StrategyWeightsManager, _normalize


def _perf(
    strategy="ema",
    regime=RegimeType.TRENDING_UP,
    sharpe=1.5,
    cagr=15.0,
    max_drawdown=8.0,
    win_rate=60.0,
    expectancy=200.0,
    total_trades=30,
) -> StrategyPerformanceRecord:
    return StrategyPerformanceRecord(
        strategy_name=strategy,
        regime_type=regime,
        sharpe=sharpe,
        cagr=cagr,
        max_drawdown=max_drawdown,
        win_rate=win_rate,
        expectancy=expectancy,
        total_trades=total_trades,
        recorded_at=datetime(2024, 1, 1),
    )


class TestNormalize:
    def test_sums_to_one(self):
        w = _normalize({"a": 3.0, "b": 1.0})
        assert abs(sum(w.values()) - 1.0) < 1e-6

    def test_all_zero_equal_split(self):
        w = _normalize({"a": 0.0, "b": 0.0, "c": 0.0})
        for v in w.values():
            assert abs(v - 1 / 3) < 0.001

    def test_single_entry(self):
        w = _normalize({"only": 5.0})
        assert w["only"] == pytest.approx(1.0)


class TestRecordPerformance:
    def setup_method(self):
        self.mgr = StrategyWeightsManager(window=5)

    def test_records_without_error(self):
        self.mgr.record_performance(_perf())

    def test_rolling_history_updated(self):
        for _ in range(3):
            self.mgr.record_performance(_perf(strategy="ema"))
        hist = self.mgr.rolling_performance("ema", RegimeType.TRENDING_UP)
        assert len(hist) == 3

    def test_window_limit_respected(self):
        for _ in range(10):
            self.mgr.record_performance(_perf(strategy="ema"))
        hist = self.mgr.rolling_performance("ema", RegimeType.TRENDING_UP)
        assert len(hist) <= 5

    def test_separate_regime_separate_history(self):
        self.mgr.record_performance(_perf(strategy="ema", regime=RegimeType.TRENDING_UP))
        self.mgr.record_performance(_perf(strategy="ema", regime=RegimeType.RANGING))
        assert len(self.mgr.rolling_performance("ema", RegimeType.TRENDING_UP)) == 1
        assert len(self.mgr.rolling_performance("ema", RegimeType.RANGING)) == 1


class TestGetWeights:
    def setup_method(self):
        self.mgr = StrategyWeightsManager()

    def test_returns_dict(self):
        self.mgr.record_performance(_perf("ema"))
        self.mgr.record_performance(_perf("momentum"))
        weights = self.mgr.get_weights(RegimeType.TRENDING_UP)
        assert isinstance(weights, dict)

    def test_weights_sum_to_one(self):
        self.mgr.record_performance(_perf("ema"))
        self.mgr.record_performance(_perf("momentum"))
        weights = self.mgr.get_weights(RegimeType.TRENDING_UP)
        assert abs(sum(weights.values()) - 1.0) < 1e-5

    def test_better_performer_gets_higher_weight(self):
        self.mgr.record_performance(_perf("good_strat", sharpe=3.0, cagr=40.0))
        self.mgr.record_performance(_perf("bad_strat", sharpe=0.2, cagr=2.0, max_drawdown=40.0))
        weights = self.mgr.get_weights(RegimeType.TRENDING_UP, ["good_strat", "bad_strat"])
        assert weights["good_strat"] > weights["bad_strat"]

    def test_no_history_uses_fit_score(self):
        self.mgr.set_regime_fit("ema", RegimeType.TRENDING_UP, 0.9)
        self.mgr.set_regime_fit("momentum", RegimeType.TRENDING_UP, 0.5)
        weights = self.mgr.get_weights(RegimeType.TRENDING_UP, ["ema", "momentum"])
        assert weights["ema"] > weights["momentum"]

    def test_empty_strategy_names_uses_all_known(self):
        self.mgr.record_performance(_perf("ema"))
        self.mgr.record_performance(_perf("momentum"))
        weights = self.mgr.get_weights(RegimeType.TRENDING_UP)
        assert len(weights) == 2

    def test_regime_fit_set(self):
        self.mgr.set_regime_fit("ema", RegimeType.RANGING, 0.15)
        fit = self.mgr._regime_fit["ema"][RegimeType.RANGING]
        assert fit == pytest.approx(0.15)

    def test_fit_clamped_to_0_1(self):
        self.mgr.set_regime_fit("ema", RegimeType.RANGING, 5.0)
        assert self.mgr._regime_fit["ema"][RegimeType.RANGING] == 1.0


class TestCompositeScore:
    def test_low_trades_returns_zero(self):
        rec = _perf(total_trades=4)
        assert rec.composite_score() == 0.0

    def test_strong_perf_high_score(self):
        rec = _perf(sharpe=3.0, cagr=50.0, max_drawdown=5.0, win_rate=70.0, total_trades=50)
        assert rec.composite_score() > 0.7

    def test_poor_perf_low_score(self):
        rec = _perf(sharpe=0.1, cagr=1.0, max_drawdown=45.0, win_rate=30.0, total_trades=10)
        assert rec.composite_score() < 0.3

    def test_score_between_0_and_1(self):
        for sharpe in [0.0, 0.5, 1.0, 2.0, 4.0]:
            rec = _perf(sharpe=sharpe, total_trades=20)
            assert 0.0 <= rec.composite_score() <= 1.0


class TestReset:
    def test_reset_clears_history(self):
        mgr = StrategyWeightsManager()
        mgr.record_performance(_perf())
        mgr.reset()
        assert mgr.all_strategy_names() == []

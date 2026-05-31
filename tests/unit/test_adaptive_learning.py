"""Unit tests for AdaptiveLearningEngine."""
from datetime import datetime

import pytest

from meta.adaptive_learning import AdaptiveLearningEngine
from meta.meta_models import LearningState, RegimeType, StrategyPerformanceRecord
from meta.strategy_scoring import StrategyScorer
from meta.strategy_weights import StrategyWeightsManager


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _perf(
    strategy="ema",
    regime=RegimeType.TRENDING_UP,
    sharpe=1.5,
    cagr=20.0,
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


def _make_engine(lr=0.10):
    scorer = StrategyScorer()
    weights = StrategyWeightsManager()
    engine = AdaptiveLearningEngine(
        scorer=scorer,
        weights_manager=weights,
        learning_rate=lr,
        persist_fn=lambda state: None,   # no-op
        load_fn=lambda: None,
    )
    return engine, scorer, weights


# ──────────────────────────────────────────────────────────────────────
# update()
# ──────────────────────────────────────────────────────────────────────

class TestUpdate:
    def test_empty_records_no_op(self):
        engine, scorer, _ = _make_engine()
        original = scorer.get_score("ema", RegimeType.TRENDING_UP)
        engine.update([])
        assert scorer.get_score("ema", RegimeType.TRENDING_UP) == original

    def test_record_updates_scorer(self):
        engine, scorer, _ = _make_engine(lr=0.5)
        original = scorer.get_score("ema", RegimeType.TRENDING_UP)
        rec = _perf(strategy="ema", regime=RegimeType.TRENDING_UP)
        engine.update([rec])
        updated = scorer.get_score("ema", RegimeType.TRENDING_UP)
        # With lr=0.5 the score must move from original
        assert updated != pytest.approx(original)

    def test_low_trades_record_skipped(self):
        engine, scorer, _ = _make_engine(lr=1.0)
        original = scorer.get_score("ema", RegimeType.TRENDING_UP)
        rec = _perf(strategy="ema", regime=RegimeType.TRENDING_UP, total_trades=3)
        engine.update([rec])
        assert scorer.get_score("ema", RegimeType.TRENDING_UP) == pytest.approx(original)

    def test_state_version_incremented(self):
        engine, _, _ = _make_engine()
        initial_version = engine.current_state().version
        engine.update([_perf()])
        assert engine.current_state().version == initial_version + 1

    def test_persist_fn_called(self):
        persisted = []
        scorer = StrategyScorer()
        weights = StrategyWeightsManager()
        engine = AdaptiveLearningEngine(
            scorer=scorer,
            weights_manager=weights,
            persist_fn=lambda state: persisted.append(state),
            load_fn=lambda: None,
        )
        engine.update([_perf()])
        assert len(persisted) == 1

    def test_blending_formula(self):
        lr = 0.2
        engine, scorer, _ = _make_engine(lr=lr)
        old_score = scorer.get_score("momentum", RegimeType.RANGING)
        rec = _perf(strategy="momentum", regime=RegimeType.RANGING, sharpe=3.0, cagr=50.0,
                    max_drawdown=5.0, win_rate=70.0, expectancy=400.0, total_trades=30)
        target = rec.composite_score() * 100.0
        expected = old_score * (1 - lr) + target * lr
        engine.update([rec])
        result = scorer.get_score("momentum", RegimeType.RANGING)
        assert result == pytest.approx(expected, rel=1e-3)

    def test_override_stored_in_state(self):
        engine, scorer, _ = _make_engine()
        engine.update([_perf(strategy="ema", regime=RegimeType.RANGING)])
        state = engine.current_state()
        assert "ema" in state.scoring_overrides
        assert "ranging" in state.scoring_overrides["ema"]

    def test_performance_history_stored(self):
        engine, _, _ = _make_engine()
        engine.update([_perf(strategy="ema", regime=RegimeType.TRENDING_UP)])
        key = "ema:trending_up"
        state = engine.current_state()
        assert key in state.performance_history
        assert len(state.performance_history[key]) == 1

    def test_multiple_records_processed(self):
        engine, scorer, _ = _make_engine()
        records = [
            _perf(strategy="ema", regime=RegimeType.TRENDING_UP),
            _perf(strategy="momentum", regime=RegimeType.RANGING),
        ]
        engine.update(records)
        assert engine.current_state().version > 1


# ──────────────────────────────────────────────────────────────────────
# load_state()
# ──────────────────────────────────────────────────────────────────────

class TestLoadState:
    def test_load_none_returns_empty_state(self):
        engine, _, _ = _make_engine()
        state = engine.load_state()
        assert isinstance(state, LearningState)

    def test_load_applies_overrides_to_scorer(self):
        saved_state = LearningState(
            scoring_overrides={"ema": {"trending_up": 42.0}},
            regime_weights={},
            performance_history={},
            last_updated=datetime(2024, 1, 1),
            version=5,
        )
        scorer = StrategyScorer()
        engine = AdaptiveLearningEngine(
            scorer=scorer,
            weights_manager=StrategyWeightsManager(),
            persist_fn=lambda s: None,
            load_fn=lambda: saved_state,
        )
        engine.load_state()
        assert scorer.get_score("ema", RegimeType.TRENDING_UP) == pytest.approx(42.0)

    def test_load_updates_version(self):
        saved_state = LearningState(
            scoring_overrides={},
            regime_weights={},
            performance_history={},
            last_updated=datetime(2024, 1, 1),
            version=7,
        )
        engine, _, _ = _make_engine()
        engine._load_fn = lambda: saved_state
        engine.load_state()
        assert engine.current_state().version == 7


# ──────────────────────────────────────────────────────────────────────
# reset()
# ──────────────────────────────────────────────────────────────────────

class TestReset:
    def test_reset_restores_baseline_scores(self):
        engine, scorer, _ = _make_engine(lr=1.0)
        original = scorer.get_score("ema", RegimeType.TRENDING_UP)
        engine.update([_perf(strategy="ema", regime=RegimeType.TRENDING_UP, sharpe=0.1, cagr=1.0)])
        engine.reset()
        assert scorer.get_score("ema", RegimeType.TRENDING_UP) == pytest.approx(original)

    def test_reset_clears_state(self):
        engine, _, _ = _make_engine()
        engine.update([_perf()])
        engine.reset()
        state = engine.current_state()
        assert state.scoring_overrides == {}
        assert state.performance_history == {}
        assert state.version == 1

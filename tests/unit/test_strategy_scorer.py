"""Unit tests for StrategyScorer."""
from datetime import datetime

import pytest

from meta.meta_models import MarketRegime, RegimeType, StrategyScore
from meta.strategy_scoring import StrategyScorer, _BASE_SCORES


def _regime(regime_type: RegimeType, confidence: float = 0.80) -> MarketRegime:
    return MarketRegime(
        regime_type=regime_type,
        confidence=confidence,
        timestamp=datetime(2024, 1, 1),
        supporting_features={},
    )


class TestScoreStrategy:
    def setup_method(self):
        self.scorer = StrategyScorer()

    def test_returns_strategy_score_type(self):
        regime = _regime(RegimeType.TRENDING_UP)
        result = self.scorer.score_strategy("ema", regime)
        assert isinstance(result, StrategyScore)

    def test_strategy_name_preserved(self):
        result = self.scorer.score_strategy("momentum", _regime(RegimeType.RANGING))
        assert result.strategy_name == "momentum"

    def test_regime_type_preserved(self):
        result = self.scorer.score_strategy("ema", _regime(RegimeType.HIGH_VOLATILITY))
        assert result.regime_type == RegimeType.HIGH_VOLATILITY

    def test_score_in_valid_range(self):
        for rt in RegimeType:
            result = self.scorer.score_strategy("ema", _regime(rt))
            assert 0.0 <= result.score <= 100.0

    def test_high_confidence_score_close_to_base(self):
        regime = _regime(RegimeType.TRENDING_UP, confidence=1.0)
        result = self.scorer.score_strategy("ema", regime)
        base = _BASE_SCORES["ema"][RegimeType.TRENDING_UP]
        assert abs(result.score - base) < 1.0

    def test_unknown_strategy_returns_default_score(self):
        result = self.scorer.score_strategy("nonexistent_strategy", _regime(RegimeType.RANGING))
        assert 0.0 <= result.score <= 100.0

    def test_momentum_trending_up_beats_ranging(self):
        trend_score = self.scorer.score_strategy("momentum", _regime(RegimeType.TRENDING_UP))
        range_score = self.scorer.score_strategy("momentum", _regime(RegimeType.RANGING))
        assert trend_score.score > range_score.score

    def test_mean_reversion_ranging_beats_trending(self):
        range_score = self.scorer.score_strategy("mean_reversion", _regime(RegimeType.RANGING))
        trend_score = self.scorer.score_strategy("mean_reversion", _regime(RegimeType.TRENDING_UP))
        assert range_score.score > trend_score.score

    def test_ema_trending_highest_score(self):
        regime = _regime(RegimeType.TRENDING_UP, confidence=1.0)
        result = self.scorer.score_strategy("ema", regime)
        assert result.score >= 90.0

    def test_confidence_affects_score(self):
        high_conf = self.scorer.score_strategy("ema", _regime(RegimeType.TRENDING_UP, 1.0))
        low_conf = self.scorer.score_strategy("ema", _regime(RegimeType.TRENDING_UP, 0.3))
        assert high_conf.score > low_conf.score


class TestScoreAll:
    def setup_method(self):
        self.scorer = StrategyScorer()

    def test_returns_list_of_strategy_scores(self):
        regime = _regime(RegimeType.TRENDING_UP)
        scores = self.scorer.score_all(regime)
        assert isinstance(scores, list)
        assert all(isinstance(s, StrategyScore) for s in scores)

    def test_scores_sorted_descending(self):
        regime = _regime(RegimeType.TRENDING_UP)
        scores = self.scorer.score_all(regime)
        for i in range(len(scores) - 1):
            assert scores[i].score >= scores[i + 1].score

    def test_all_registered_strategies_scored(self):
        regime = _regime(RegimeType.RANGING)
        scores = self.scorer.score_all(regime)
        names = {s.strategy_name for s in scores}
        assert "momentum" in names
        assert "mean_reversion" in names
        assert "ema" in names

    def test_strategy_names_filter(self):
        regime = _regime(RegimeType.RANGING)
        scores = self.scorer.score_all(regime, strategy_names=["ema", "momentum"])
        assert len(scores) == 2
        assert {s.strategy_name for s in scores} == {"ema", "momentum"}

    def test_best_for_trending_up_is_trend_strategy(self):
        regime = _regime(RegimeType.TRENDING_UP, confidence=1.0)
        scores = self.scorer.score_all(regime)
        assert scores[0].strategy_name in ("ema", "trend_confluence")

    def test_best_for_ranging_is_mean_reversion(self):
        regime = _regime(RegimeType.RANGING, confidence=1.0)
        scores = self.scorer.score_all(regime)
        assert scores[0].strategy_name == "mean_reversion"


class TestUpdateScore:
    def setup_method(self):
        self.scorer = StrategyScorer()

    def test_update_changes_score(self):
        self.scorer.update_score("ema", RegimeType.RANGING, 75.0)
        assert self.scorer.get_score("ema", RegimeType.RANGING) == 75.0

    def test_update_clamps_above_100(self):
        self.scorer.update_score("ema", RegimeType.RANGING, 150.0)
        assert self.scorer.get_score("ema", RegimeType.RANGING) == 100.0

    def test_update_clamps_below_zero(self):
        self.scorer.update_score("ema", RegimeType.RANGING, -10.0)
        assert self.scorer.get_score("ema", RegimeType.RANGING) == 0.0

    def test_new_strategy_created(self):
        self.scorer.update_score("new_strat", RegimeType.TRENDING_UP, 70.0)
        assert self.scorer.get_score("new_strat", RegimeType.TRENDING_UP) == 70.0

    def test_reset_restores_baseline(self):
        original = self.scorer.get_score("ema", RegimeType.TRENDING_UP)
        self.scorer.update_score("ema", RegimeType.TRENDING_UP, 10.0)
        self.scorer.reset_to_baseline()
        assert self.scorer.get_score("ema", RegimeType.TRENDING_UP) == original

    def test_apply_overrides_bulk(self):
        overrides = {"momentum": {"trending_up": 55.0, "ranging": 8.0}}
        self.scorer.apply_overrides(overrides)
        assert self.scorer.get_score("momentum", RegimeType.TRENDING_UP) == 55.0
        assert self.scorer.get_score("momentum", RegimeType.RANGING) == 8.0

    def test_apply_overrides_invalid_regime_ignored(self):
        overrides = {"momentum": {"invalid_regime_xyz": 50.0}}
        self.scorer.apply_overrides(overrides)
        assert self.scorer.get_score("momentum", RegimeType.TRENDING_UP) > 0

"""Unit tests for StrategyRouter."""
from datetime import datetime

import pytest

from meta.meta_models import MarketRegime, MetaSignal, RegimeType, RoutingMode, StrategyScore
from meta.strategy_router import StrategyRouter, _normalize_weights


def _regime(regime_type=RegimeType.TRENDING_UP, confidence=0.80):
    return MarketRegime(
        regime_type=regime_type,
        confidence=confidence,
        timestamp=datetime(2024, 1, 1),
        supporting_features={},
    )


def _scores(names_and_scores: list[tuple[str, float]], regime_type=RegimeType.TRENDING_UP):
    return [
        StrategyScore(
            strategy_name=name,
            regime_type=regime_type,
            score=score,
            confidence=0.80,
        )
        for name, score in sorted(names_and_scores, key=lambda x: -x[1])
    ]


class TestNormalizeWeights:
    def test_basic_normalization(self):
        w = _normalize_weights({"a": 60.0, "b": 40.0})
        assert abs(w["a"] - 0.6) < 0.001
        assert abs(w["b"] - 0.4) < 0.001

    def test_sums_to_one(self):
        w = _normalize_weights({"a": 30.0, "b": 50.0, "c": 20.0})
        assert abs(sum(w.values()) - 1.0) < 1e-5

    def test_all_zero_equal_weights(self):
        w = _normalize_weights({"a": 0.0, "b": 0.0})
        assert abs(w["a"] - 0.5) < 0.001
        assert abs(w["b"] - 0.5) < 0.001

    def test_single_entry_weight_is_one(self):
        w = _normalize_weights({"only": 42.0})
        assert w["only"] == pytest.approx(1.0)


class TestSingleBestRouting:
    def setup_method(self):
        self.router = StrategyRouter(mode=RoutingMode.SINGLE_BEST)

    def test_returns_meta_signal(self):
        signal = self.router.route(
            _regime(), _scores([("ema", 90), ("momentum", 70)]), "NIFTY 50", "5min"
        )
        assert isinstance(signal, MetaSignal)

    def test_selects_highest_scoring_strategy(self):
        signal = self.router.route(
            _regime(), _scores([("ema", 90), ("momentum", 70)]), "NIFTY 50", "5min"
        )
        assert signal.selected_strategy == "ema"

    def test_weight_is_1_for_selected(self):
        signal = self.router.route(
            _regime(), _scores([("ema", 90)]), "NIFTY 50", "5min"
        )
        assert signal.strategy_weights == {"ema": 1.0}

    def test_routing_mode_set_correctly(self):
        signal = self.router.route(
            _regime(), _scores([("ema", 90)]), "NIFTY 50", "5min"
        )
        assert signal.routing_mode == RoutingMode.SINGLE_BEST

    def test_instrument_and_timeframe_preserved(self):
        signal = self.router.route(
            _regime(), _scores([("ema", 90)]), "NIFTY BANK", "15min"
        )
        assert signal.instrument == "NIFTY BANK"
        assert signal.timeframe == "15min"

    def test_regime_type_preserved(self):
        regime = _regime(RegimeType.RANGING)
        signal = self.router.route(
            regime, _scores([("mean_reversion", 85)], RegimeType.RANGING), "NIFTY 50", "5min"
        )
        assert signal.regime_type == RegimeType.RANGING

    def test_empty_scores_raises(self):
        with pytest.raises(ValueError):
            self.router.route(_regime(), [], "NIFTY 50", "5min")

    def test_reasoning_mentions_strategy_name(self):
        signal = self.router.route(
            _regime(), _scores([("ema", 90)]), "NIFTY 50", "5min"
        )
        assert "ema" in signal.reasoning

    def test_explicit_timestamp_used(self):
        ts = datetime(2025, 6, 15)
        signal = self.router.route(
            _regime(), _scores([("ema", 90)]), "NIFTY 50", "5min", timestamp=ts
        )
        assert signal.timestamp == ts


class TestWeightedBlendRouting:
    def setup_method(self):
        self.router = StrategyRouter(mode=RoutingMode.WEIGHTED_BLEND, blend_min_score=30.0)

    def test_returns_meta_signal(self):
        signal = self.router.route(
            _regime(), _scores([("ema", 90), ("momentum", 70), ("vwap", 50)]), "N50", "5min"
        )
        assert isinstance(signal, MetaSignal)

    def test_routing_mode_weighted(self):
        signal = self.router.route(
            _regime(), _scores([("ema", 90), ("momentum", 70)]), "N50", "5min"
        )
        assert signal.routing_mode == RoutingMode.WEIGHTED_BLEND

    def test_weights_sum_to_one(self):
        signal = self.router.route(
            _regime(), _scores([("ema", 90), ("momentum", 70), ("vwap", 50)]), "N50", "5min"
        )
        assert abs(sum(signal.strategy_weights.values()) - 1.0) < 1e-4

    def test_all_below_threshold_falls_back_to_single(self):
        router = StrategyRouter(mode=RoutingMode.WEIGHTED_BLEND, blend_min_score=95.0)
        scores = _scores([("ema", 90), ("momentum", 70)])
        signal = router.route(_regime(), scores, "N50", "5min")
        assert signal.routing_mode == RoutingMode.SINGLE_BEST

    def test_highest_score_has_highest_weight(self):
        signal = self.router.route(
            _regime(), _scores([("ema", 90), ("momentum", 70), ("vwap", 50)]), "N50", "5min"
        )
        weights = signal.strategy_weights
        best = max(weights, key=lambda k: weights[k])
        assert best == "ema"

    def test_max_blend_strategies_respected(self):
        router = StrategyRouter(mode=RoutingMode.WEIGHTED_BLEND, blend_max=2, blend_min_score=0.0)
        scores = _scores([("ema", 90), ("momentum", 70), ("vwap", 50), ("mean_reversion", 40)])
        signal = router.route(_regime(), scores, "N50", "5min")
        assert len(signal.strategy_weights) <= 2

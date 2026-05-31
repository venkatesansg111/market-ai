"""Unit tests for MetaStrategyEngine — all dependencies injected via mocks."""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from meta.meta_models import (
    MarketRegime,
    MetaSignal,
    RegimeType,
    RoutingMode,
    StrategyScore,
)
from meta.meta_strategy_engine import MetaStrategyEngine
from meta.regime_detector import RegimeDetector
from meta.strategy_router import StrategyRouter
from meta.strategy_scoring import StrategyScorer


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _make_regime(regime_type=RegimeType.TRENDING_UP, confidence=0.80):
    return MarketRegime(
        regime_type=regime_type,
        confidence=confidence,
        timestamp=datetime(2024, 1, 1),
        supporting_features={"adx": 30.0},
    )


def _make_signal(strategy="ema", regime_type=RegimeType.TRENDING_UP):
    return MetaSignal(
        instrument="NIFTY 50",
        timeframe="5min",
        selected_strategy=strategy,
        regime_type=regime_type,
        confidence=0.80,
        strategy_weights={strategy: 1.0},
        routing_mode=RoutingMode.SINGLE_BEST,
        reasoning="test",
        timestamp=datetime(2024, 1, 1),
    )


def _make_engine(
    regime=None,
    signal=None,
    adaptive=False,
) -> MetaStrategyEngine:
    mock_detector = MagicMock(spec=RegimeDetector)
    mock_detector.detect_from_row.return_value = regime or _make_regime()
    mock_detector.detect_from_series.return_value = [regime or _make_regime()]
    mock_detector.detect_latest.return_value = regime or _make_regime()

    mock_scorer = MagicMock(spec=StrategyScorer)
    mock_scorer.score_all.return_value = [
        StrategyScore("ema", RegimeType.TRENDING_UP, 90.0, 0.8),
        StrategyScore("momentum", RegimeType.TRENDING_UP, 70.0, 0.8),
    ]

    mock_router = MagicMock(spec=StrategyRouter)
    mock_router.route.return_value = signal or _make_signal()

    return MetaStrategyEngine(
        detector=mock_detector,
        scorer=mock_scorer,
        router=mock_router,
        enable_adaptive_learning=adaptive,
    )


def _indicator_row():
    return SimpleNamespace(
        adx_14=30.0,
        atr_14=100.0,
        supertrend_direction=1,
        ema20=120.0,
        ema50=100.0,
        ema200=80.0,
        bb_width=0.02,
        candle_time=datetime(2024, 1, 1),
    )


# ──────────────────────────────────────────────────────────────────────
# analyze
# ──────────────────────────────────────────────────────────────────────

class TestAnalyze:
    def test_returns_meta_signal(self):
        engine = _make_engine()
        result = engine.analyze(_indicator_row(), "NIFTY 50", "5min")
        assert isinstance(result, MetaSignal)

    def test_calls_detector_with_row(self):
        engine = _make_engine()
        row = _indicator_row()
        engine.analyze(row, "NIFTY 50", "5min")
        engine._detector.detect_from_row.assert_called_once()

    def test_calls_scorer_with_regime(self):
        engine = _make_engine()
        engine.analyze(_indicator_row(), "NIFTY 50", "5min")
        engine._scorer.score_all.assert_called_once()

    def test_calls_router_with_scores(self):
        engine = _make_engine()
        engine.analyze(_indicator_row(), "NIFTY 50", "5min")
        engine._router.route.assert_called_once()

    def test_instrument_passed_to_router(self):
        engine = _make_engine()
        engine.analyze(_indicator_row(), "NIFTY BANK", "15min")
        call_kwargs = engine._router.route.call_args
        assert call_kwargs.kwargs["instrument"] == "NIFTY BANK"

    def test_timeframe_passed_to_router(self):
        engine = _make_engine()
        engine.analyze(_indicator_row(), "NIFTY 50", "15min")
        call_kwargs = engine._router.route.call_args
        assert call_kwargs.kwargs["timeframe"] == "15min"

    def test_strategy_names_filter_forwarded(self):
        engine = _make_engine()
        engine.analyze(_indicator_row(), "NIFTY 50", "5min", strategy_names=["ema"])
        engine._scorer.score_all.assert_called_once()
        args = engine._scorer.score_all.call_args
        assert args.args[1] == ["ema"] or args.kwargs.get("strategy_names") == ["ema"]


# ──────────────────────────────────────────────────────────────────────
# analyze_series
# ──────────────────────────────────────────────────────────────────────

class TestAnalyzeSeries:
    def test_empty_rows_returns_empty(self):
        engine = _make_engine()
        engine._detector.detect_from_series.return_value = []
        result = engine.analyze_series([], "NIFTY 50", "5min")
        assert result == []

    def test_returns_one_signal_per_regime(self):
        regimes = [_make_regime(RegimeType.TRENDING_UP), _make_regime(RegimeType.RANGING)]
        engine = _make_engine()
        engine._detector.detect_from_series.return_value = regimes
        result = engine.analyze_series(
            [_indicator_row(), _indicator_row()], "NIFTY 50", "5min"
        )
        assert len(result) == 2

    def test_each_result_is_meta_signal(self):
        regimes = [_make_regime(), _make_regime()]
        engine = _make_engine()
        engine._detector.detect_from_series.return_value = regimes
        results = engine.analyze_series(
            [_indicator_row(), _indicator_row()], "NIFTY 50", "5min"
        )
        assert all(isinstance(s, MetaSignal) for s in results)


# ──────────────────────────────────────────────────────────────────────
# analyze_from_regime
# ──────────────────────────────────────────────────────────────────────

class TestAnalyzeFromRegime:
    def test_skips_detector(self):
        engine = _make_engine()
        regime = _make_regime(RegimeType.RANGING)
        engine.analyze_from_regime(regime, "NIFTY 50", "5min")
        engine._detector.detect_from_row.assert_not_called()

    def test_routes_correctly(self):
        engine = _make_engine()
        regime = _make_regime(RegimeType.RANGING)
        result = engine.analyze_from_regime(regime, "NIFTY 50", "5min")
        assert isinstance(result, MetaSignal)


# ──────────────────────────────────────────────────────────────────────
# current_regime
# ──────────────────────────────────────────────────────────────────────

class TestCurrentRegime:
    def test_returns_regime(self):
        engine = _make_engine()
        regime = engine.current_regime([_indicator_row()])
        assert isinstance(regime, MarketRegime)

    def test_empty_returns_none(self):
        engine = _make_engine()
        engine._detector.detect_latest.return_value = None
        result = engine.current_regime([])
        assert result is None


# ──────────────────────────────────────────────────────────────────────
# ingest_backtest_result (adaptive learning)
# ──────────────────────────────────────────────────────────────────────

class TestIngestBacktestResult:
    def test_no_op_when_adaptive_disabled(self):
        engine = _make_engine(adaptive=False)
        engine._learning = MagicMock()
        engine.ingest_backtest_result(MagicMock())
        engine._learning.update.assert_not_called()

    def test_calls_feedback_when_adaptive_enabled(self):
        engine = _make_engine(adaptive=False)
        engine._adaptive = True
        engine._feedback = MagicMock()
        engine._learning = MagicMock()
        engine._feedback.record.return_value = MagicMock()
        signal = _make_signal()
        engine.ingest_backtest_result(MagicMock(), meta_signal=signal)
        engine._feedback.record.assert_called_once()
        engine._learning.update.assert_called_once()


# ──────────────────────────────────────────────────────────────────────
# Integration: real detector + scorer + router (no DB)
# ──────────────────────────────────────────────────────────────────────

class TestIntegration:
    def test_trending_up_selects_trend_strategy(self):
        row = SimpleNamespace(
            adx_14=35.0, atr_14=100.0, supertrend_direction=1,
            ema20=130.0, ema50=110.0, ema200=90.0, bb_width=0.02,
            candle_time=datetime(2024, 1, 1),
        )
        engine = MetaStrategyEngine()
        signal = engine.analyze(row, "NIFTY 50", "5min", mean_atr=100.0)
        assert signal.selected_strategy in ("ema", "trend_confluence")
        assert signal.regime_type == RegimeType.TRENDING_UP

    def test_ranging_selects_mean_reversion(self):
        row = SimpleNamespace(
            adx_14=12.0, atr_14=100.0, supertrend_direction=0,
            ema20=100.0, ema50=100.0, ema200=100.0, bb_width=0.01,
            candle_time=datetime(2024, 1, 1),
        )
        engine = MetaStrategyEngine()
        signal = engine.analyze(row, "NIFTY 50", "5min", mean_atr=100.0)
        assert signal.selected_strategy == "mean_reversion"
        assert signal.regime_type == RegimeType.RANGING

    def test_signal_has_all_required_fields(self):
        row = SimpleNamespace(
            adx_14=20.0, atr_14=100.0, supertrend_direction=0,
            ema20=100.0, ema50=100.0, ema200=100.0, bb_width=0.02,
            candle_time=datetime(2024, 1, 1),
        )
        engine = MetaStrategyEngine()
        signal = engine.analyze(row, "NIFTY 50", "5min")
        assert signal.instrument == "NIFTY 50"
        assert signal.timeframe == "5min"
        assert signal.selected_strategy != ""
        assert signal.reasoning != ""
        assert isinstance(signal.strategy_weights, dict)

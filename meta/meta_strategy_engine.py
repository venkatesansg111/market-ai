"""MetaStrategyEngine — orchestrates regime detection, scoring, and routing."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from config import settings
from meta.adaptive_learning import AdaptiveLearningEngine
from meta.meta_models import MarketRegime, MetaSignal, RegimeType, RoutingMode
from meta.performance_feedback import PerformanceFeedback
from meta.regime_detector import RegimeDetector
from meta.strategy_router import StrategyRouter
from meta.strategy_scoring import StrategyScorer
from meta.strategy_weights import StrategyWeightsManager
from utils.logger import get_logger

logger = get_logger(__name__, settings.log_dir, settings.log_level)


class MetaStrategyEngine:
    """Top-level orchestrator for the Meta Strategy system.

    Wires together:

    * :class:`~meta.regime_detector.RegimeDetector` — market regime classification
    * :class:`~meta.strategy_scoring.StrategyScorer` — per-regime strategy scoring
    * :class:`~meta.strategy_router.StrategyRouter` — strategy selection
    * :class:`~meta.strategy_weights.StrategyWeightsManager` — adaptive weights
    * :class:`~meta.adaptive_learning.AdaptiveLearningEngine` — feedback learning
    * :class:`~meta.performance_feedback.PerformanceFeedback` — result ingestion

    All dependencies are injectable for unit testing::

        engine = MetaStrategyEngine(
            detector=mock_detector,
            scorer=mock_scorer,
            router=mock_router,
        )

    Typical usage::

        signal = engine.analyze(
            row=indicator_row,
            instrument="NIFTY 50",
            timeframe="5min",
            mean_atr=150.0,
        )
        strategy = signal.selected_strategy
    """

    def __init__(
        self,
        detector: Optional[RegimeDetector] = None,
        scorer: Optional[StrategyScorer] = None,
        router: Optional[StrategyRouter] = None,
        weights_manager: Optional[StrategyWeightsManager] = None,
        learning_engine: Optional[AdaptiveLearningEngine] = None,
        feedback: Optional[PerformanceFeedback] = None,
        routing_mode: RoutingMode = RoutingMode.SINGLE_BEST,
        enable_adaptive_learning: bool = False,
    ) -> None:
        self._detector = detector or RegimeDetector()
        self._scorer = scorer or StrategyScorer()
        self._router = router or StrategyRouter(mode=routing_mode)
        self._weights = weights_manager or StrategyWeightsManager()
        self._learning = learning_engine or AdaptiveLearningEngine(
            scorer=self._scorer,
            weights_manager=self._weights,
        )
        self._feedback = feedback or PerformanceFeedback(self._weights)
        self._adaptive = enable_adaptive_learning

        if self._adaptive:
            self._learning.load_state()

    # ── Primary API ───────────────────────────────────────────────────────

    def analyze(
        self,
        row: Any,
        instrument: str,
        timeframe: str,
        mean_atr: float = 0.0,
        strategy_names: Optional[list[str]] = None,
        timestamp: Optional[datetime] = None,
    ) -> MetaSignal:
        """Detect regime and select strategy from a single indicator row.

        Args:
            row:             MarketIndicator row (or compatible object).
            instrument:      Instrument name (e.g. ``"NIFTY 50"``).
            timeframe:       Timeframe string (e.g. ``"5min"``).
            mean_atr:        Historical mean ATR for volatility ratio computation.
            strategy_names:  Restrict scoring to this subset of strategy names.
            timestamp:       Override timestamp; defaults to ``row.candle_time``.

        Returns:
            :class:`MetaSignal` with selected strategy and regime metadata.
        """
        regime = self._detector.detect_from_row(row, mean_atr, timestamp)
        return self._select(regime, instrument, timeframe, strategy_names, timestamp)

    def analyze_series(
        self,
        rows: list[Any],
        instrument: str,
        timeframe: str,
        strategy_names: Optional[list[str]] = None,
    ) -> list[MetaSignal]:
        """Run analysis over a chronological series of indicator rows.

        Returns one :class:`MetaSignal` per row (excluding skipped rows).
        """
        if not rows:
            return []
        regimes = self._detector.detect_from_series(rows)
        signals = []
        for regime in regimes:
            sig = self._select(regime, instrument, timeframe, strategy_names)
            signals.append(sig)
        return signals

    def analyze_from_regime(
        self,
        regime: MarketRegime,
        instrument: str,
        timeframe: str,
        strategy_names: Optional[list[str]] = None,
        timestamp: Optional[datetime] = None,
    ) -> MetaSignal:
        """Select strategy directly from a pre-detected :class:`MarketRegime`."""
        return self._select(regime, instrument, timeframe, strategy_names, timestamp)

    # ── Learning / feedback ───────────────────────────────────────────────

    def ingest_backtest_result(
        self,
        bt_result: Any,
        meta_signal: Optional[MetaSignal] = None,
        regime_type: Optional[RegimeType] = None,
    ) -> None:
        """Feed a BacktestResult back into the adaptive learning system.

        Only active when *enable_adaptive_learning* is ``True``.
        """
        if not self._adaptive:
            return
        record = self._feedback.record(bt_result, meta_signal=meta_signal, regime_type=regime_type)
        self._learning.update([record])

    def current_regime(
        self,
        rows: list[Any],
    ) -> Optional[MarketRegime]:
        """Convenience: detect the regime for the most recent row."""
        return self._detector.detect_latest(rows)

    # ── Private helpers ───────────────────────────────────────────────────

    def _select(
        self,
        regime: MarketRegime,
        instrument: str,
        timeframe: str,
        strategy_names: Optional[list[str]],
        timestamp: Optional[datetime] = None,
    ) -> MetaSignal:
        scores = self._scorer.score_all(regime, strategy_names)

        logger.debug(
            "[MetaEngine] Regime=%s (conf=%.2f) | top=%s score=%.1f",
            regime.regime_type.value,
            regime.confidence,
            scores[0].strategy_name if scores else "N/A",
            scores[0].score if scores else 0.0,
        )

        return self._router.route(
            regime=regime,
            scores=scores,
            instrument=instrument,
            timeframe=timeframe,
            timestamp=timestamp,
        )

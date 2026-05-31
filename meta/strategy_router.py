"""StrategyRouter — select best strategy or weighted blend from scored candidates."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from meta.meta_models import (
    MarketRegime,
    MetaSignal,
    RoutingMode,
    StrategyScore,
)

# Minimum score to include a strategy in weighted blend
_BLEND_MIN_SCORE = 30.0
# Maximum strategies in a weighted blend
_BLEND_MAX_STRATEGIES = 3


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    """Normalize weights so they sum to 1.0; return equal weights if all zero."""
    total = sum(weights.values())
    if total <= 0:
        n = len(weights)
        return {k: round(1.0 / n, 6) for k in weights}
    return {k: round(v / total, 6) for k, v in weights.items()}


class StrategyRouter:
    """Routes strategy selection based on regime scores.

    Modes:

    * **SINGLE_BEST** — selects the top-scoring strategy.
    * **WEIGHTED_BLEND** — distributes weight among the top-N eligible strategies;
      the highest-weight strategy is set as ``selected_strategy``.

    Usage::

        router = StrategyRouter()
        signal = router.route(
            regime=regime,
            scores=scorer.score_all(regime),
            instrument="NIFTY 50",
            timeframe="5min",
        )
    """

    def __init__(
        self,
        mode: RoutingMode = RoutingMode.SINGLE_BEST,
        blend_max: int = _BLEND_MAX_STRATEGIES,
        blend_min_score: float = _BLEND_MIN_SCORE,
    ) -> None:
        self.mode = mode
        self._blend_max = blend_max
        self._blend_min_score = blend_min_score

    # ── Public API ────────────────────────────────────────────────────────

    def route(
        self,
        regime: MarketRegime,
        scores: list[StrategyScore],
        instrument: str,
        timeframe: str,
        timestamp: Optional[datetime] = None,
    ) -> MetaSignal:
        """Produce a :class:`MetaSignal` for the given regime and score list.

        Args:
            regime:     The detected market regime.
            scores:     Sorted list of :class:`StrategyScore` (descending score).
            instrument: Target instrument (e.g. ``"NIFTY 50"``).
            timeframe:  Target timeframe (e.g. ``"5min"``).
            timestamp:  Override timestamp; defaults to ``regime.timestamp``.
        """
        if not scores:
            raise ValueError("scores list must not be empty")

        ts = timestamp or regime.timestamp

        if self.mode == RoutingMode.WEIGHTED_BLEND:
            return self._route_weighted(regime, scores, instrument, timeframe, ts)
        return self._route_single(regime, scores, instrument, timeframe, ts)

    # ── Private helpers ───────────────────────────────────────────────────

    def _route_single(
        self,
        regime: MarketRegime,
        scores: list[StrategyScore],
        instrument: str,
        timeframe: str,
        timestamp: datetime,
    ) -> MetaSignal:
        best = scores[0]
        reasoning = (
            f"Selected '{best.strategy_name}' (score={best.score:.1f}) "
            f"as best fit for regime '{regime.regime_type.value}' "
            f"(confidence={regime.confidence:.2f})"
        )
        return MetaSignal(
            instrument=instrument,
            timeframe=timeframe,
            selected_strategy=best.strategy_name,
            regime_type=regime.regime_type,
            confidence=regime.confidence,
            strategy_weights={best.strategy_name: 1.0},
            routing_mode=RoutingMode.SINGLE_BEST,
            reasoning=reasoning,
            timestamp=timestamp,
        )

    def _route_weighted(
        self,
        regime: MarketRegime,
        scores: list[StrategyScore],
        instrument: str,
        timeframe: str,
        timestamp: datetime,
    ) -> MetaSignal:
        eligible = [
            s for s in scores if s.score >= self._blend_min_score
        ][: self._blend_max]

        if not eligible:
            return self._route_single(regime, scores, instrument, timeframe, timestamp)

        raw_weights = {s.strategy_name: s.score for s in eligible}
        weights = _normalize_weights(raw_weights)

        best_name = max(weights, key=lambda k: weights[k])
        strategy_list = ", ".join(
            f"{k}={v:.2f}" for k, v in sorted(weights.items(), key=lambda x: -x[1])
        )
        reasoning = (
            f"Weighted blend for regime '{regime.regime_type.value}': [{strategy_list}] "
            f"(confidence={regime.confidence:.2f})"
        )
        return MetaSignal(
            instrument=instrument,
            timeframe=timeframe,
            selected_strategy=best_name,
            regime_type=regime.regime_type,
            confidence=regime.confidence,
            strategy_weights=weights,
            routing_mode=RoutingMode.WEIGHTED_BLEND,
            reasoning=reasoning,
            timestamp=timestamp,
        )

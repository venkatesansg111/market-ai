"""StrategyScorer — static + adaptive scoring matrix for strategies per regime."""
from __future__ import annotations

from copy import deepcopy
from typing import Optional

from meta.meta_models import MarketRegime, RegimeType, StrategyScore

# ── Static baseline scoring matrix ───────────────────────────────────────────
# scores are in [0, 100]: higher = more suitable for that regime
_BASE_SCORES: dict[str, dict[RegimeType, float]] = {
    "momentum": {
        RegimeType.TRENDING_UP: 90.0,
        RegimeType.TRENDING_DOWN: 70.0,
        RegimeType.RANGING: 10.0,
        RegimeType.HIGH_VOLATILITY: 60.0,
        RegimeType.LOW_VOLATILITY: 30.0,
    },
    "mean_reversion": {
        RegimeType.TRENDING_UP: 15.0,
        RegimeType.TRENDING_DOWN: 15.0,
        RegimeType.RANGING: 85.0,
        RegimeType.HIGH_VOLATILITY: 20.0,
        RegimeType.LOW_VOLATILITY: 80.0,
    },
    "ema": {
        RegimeType.TRENDING_UP: 95.0,
        RegimeType.TRENDING_DOWN: 80.0,
        RegimeType.RANGING: 15.0,
        RegimeType.HIGH_VOLATILITY: 50.0,
        RegimeType.LOW_VOLATILITY: 40.0,
    },
    "vwap": {
        RegimeType.TRENDING_UP: 75.0,
        RegimeType.TRENDING_DOWN: 70.0,
        RegimeType.RANGING: 60.0,
        RegimeType.HIGH_VOLATILITY: 55.0,
        RegimeType.LOW_VOLATILITY: 45.0,
    },
    "trend_confluence": {
        RegimeType.TRENDING_UP: 95.0,
        RegimeType.TRENDING_DOWN: 90.0,
        RegimeType.RANGING: 15.0,
        RegimeType.HIGH_VOLATILITY: 45.0,
        RegimeType.LOW_VOLATILITY: 35.0,
    },
    "supertrend_confluence": {
        RegimeType.TRENDING_UP: 90.0,
        RegimeType.TRENDING_DOWN: 85.0,
        RegimeType.RANGING: 20.0,
        RegimeType.HIGH_VOLATILITY: 50.0,
        RegimeType.LOW_VOLATILITY: 30.0,
    },
    "momentum_confluence": {
        RegimeType.TRENDING_UP: 85.0,
        RegimeType.TRENDING_DOWN: 75.0,
        RegimeType.RANGING: 25.0,
        RegimeType.HIGH_VOLATILITY: 65.0,
        RegimeType.LOW_VOLATILITY: 35.0,
    },
}

# Fallback score for unknown strategy × regime combinations
_DEFAULT_SCORE = 50.0


class StrategyScorer:
    """Scores strategies against a detected market regime.

    The scoring matrix starts from :data:`_BASE_SCORES` and can be updated
    by the adaptive learning engine at runtime::

        scorer = StrategyScorer()
        scores = scorer.score_all(regime)

        # After learning:
        scorer.update_score("ema", RegimeType.RANGING, 25.0)
    """

    def __init__(self) -> None:
        self._scores: dict[str, dict[RegimeType, float]] = deepcopy(_BASE_SCORES)

    # ── Public API ────────────────────────────────────────────────────────

    def score_all(
        self,
        regime: MarketRegime,
        strategy_names: Optional[list[str]] = None,
    ) -> list[StrategyScore]:
        """Score every known strategy (or *strategy_names* subset) for *regime*.

        Returns scores sorted descending by score value.
        """
        names = strategy_names or list(self._scores)
        scores = [self.score_strategy(name, regime) for name in names]
        scores.sort(key=lambda s: s.score, reverse=True)
        return scores

    def score_strategy(self, strategy_name: str, regime: MarketRegime) -> StrategyScore:
        """Return the score for a single strategy in the given regime."""
        regime_map = self._scores.get(strategy_name, {})
        base_score = regime_map.get(regime.regime_type, _DEFAULT_SCORE)
        adjusted = min(max(base_score * regime.confidence + base_score * (1 - regime.confidence) * 0.5, 0.0), 100.0)

        return StrategyScore(
            strategy_name=strategy_name,
            regime_type=regime.regime_type,
            score=round(adjusted, 4),
            confidence=regime.confidence,
        )

    def update_score(
        self,
        strategy_name: str,
        regime_type: RegimeType,
        new_score: float,
    ) -> None:
        """Override the score for a (strategy, regime) pair.

        New score is clamped to [0, 100].
        """
        clamped = min(max(new_score, 0.0), 100.0)
        if strategy_name not in self._scores:
            self._scores[strategy_name] = {}
        self._scores[strategy_name][regime_type] = clamped

    def get_score(self, strategy_name: str, regime_type: RegimeType) -> float:
        """Return the raw base score for a (strategy, regime) pair."""
        return self._scores.get(strategy_name, {}).get(regime_type, _DEFAULT_SCORE)

    def all_strategy_names(self) -> list[str]:
        """Return all strategy names registered in the scorer."""
        return list(self._scores)

    def reset_to_baseline(self) -> None:
        """Reset all scores to the static baseline."""
        self._scores = deepcopy(_BASE_SCORES)

    def apply_overrides(self, overrides: dict[str, dict[str, float]]) -> None:
        """Bulk-apply score overrides from the learning state.

        *overrides* maps ``strategy_name → {regime_type_value → score}``.
        """
        for strategy_name, regime_map in overrides.items():
            for regime_str, score in regime_map.items():
                try:
                    regime_type = RegimeType(regime_str)
                    self.update_score(strategy_name, regime_type, score)
                except ValueError:
                    pass

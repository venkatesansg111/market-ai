"""StrategyWeightsManager — maintain adaptive per-strategy per-regime weights."""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Optional

from meta.meta_models import RegimeType, StrategyPerformanceRecord

# Rolling window size for performance averaging
_DEFAULT_WINDOW = 10


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    """Normalize weight dict to sum to 1.0; equal split on all-zero."""
    total = sum(weights.values())
    if total <= 0:
        n = len(weights)
        return {k: round(1.0 / n, 6) for k in weights}
    return {k: round(v / total, 6) for k, v in weights.items()}


class StrategyWeightsManager:
    """Tracks rolling performance per (strategy, regime) and exposes adaptive weights.

    Weight formula::

        weight(strategy, regime) = perf_score(strategy, regime) * regime_fit(strategy, regime)

    Where:

    * ``perf_score`` is the rolling-average composite performance score [0, 1]
    * ``regime_fit`` is the base scoring-matrix value / 100 [0, 1]

    Weights are normalised to sum = 1.0 within a regime.

    Usage::

        mgr = StrategyWeightsManager()
        mgr.record_performance(record)
        weights = mgr.get_weights(RegimeType.TRENDING_UP)
    """

    def __init__(self, window: int = _DEFAULT_WINDOW) -> None:
        self._window = window
        # {strategy_name: {regime_type: deque[float]}}
        self._history: dict[str, dict[RegimeType, deque[float]]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=self._window))
        )
        # Regime fit scores injected from StrategyScorer (strategy → regime → 0..1)
        self._regime_fit: dict[str, dict[RegimeType, float]] = {}

    # ── Public API ────────────────────────────────────────────────────────

    def set_regime_fit(self, strategy_name: str, regime_type: RegimeType, fit: float) -> None:
        """Inject a regime fit score (base_score / 100) from the scoring matrix."""
        if strategy_name not in self._regime_fit:
            self._regime_fit[strategy_name] = {}
        self._regime_fit[strategy_name][regime_type] = min(max(fit, 0.0), 1.0)

    def record_performance(self, record: StrategyPerformanceRecord) -> None:
        """Add a performance record to the rolling window."""
        score = record.composite_score()
        self._history[record.strategy_name][record.regime_type].append(score)

    def get_weights(
        self,
        regime_type: RegimeType,
        strategy_names: Optional[list[str]] = None,
    ) -> dict[str, float]:
        """Return normalised weights for all (or specified) strategies in *regime_type*.

        If no performance history exists for a strategy, its weight is based solely
        on the regime fit score (or 0.5 if that is also absent).
        """
        names = strategy_names or list(self._history) or []
        if not names:
            return {}

        raw: dict[str, float] = {}
        for name in names:
            perf_score = self._rolling_mean(name, regime_type)
            fit = self._regime_fit.get(name, {}).get(regime_type, 0.5)
            raw[name] = perf_score * fit if perf_score > 0 else fit * 0.5

        return _normalize(raw)

    def rolling_performance(
        self,
        strategy_name: str,
        regime_type: RegimeType,
    ) -> list[float]:
        """Return the raw performance history for a (strategy, regime) pair."""
        return list(self._history[strategy_name][regime_type])

    def all_strategy_names(self) -> list[str]:
        """All strategy names with recorded history."""
        return list(self._history)

    def reset(self) -> None:
        """Clear all recorded performance history."""
        self._history.clear()

    # ── Private helpers ───────────────────────────────────────────────────

    def _rolling_mean(self, strategy_name: str, regime_type: RegimeType) -> float:
        history = self._history.get(strategy_name, {}).get(regime_type, deque())
        if not history:
            return 0.0
        return sum(history) / len(history)

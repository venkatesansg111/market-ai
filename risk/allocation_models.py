"""Phase 8 — Allocation Models: ERC, Inverse-Volatility, Strategy-Performance."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional

from risk.risk_models import AllocationModelType, AllocationWeight

logger = logging.getLogger(__name__)

_TINY = 1e-12


class AllocationModel(ABC):
    @abstractmethod
    def allocate(
        self,
        symbols: list[str],
        strategy_names: list[str],
        volatilities: dict[str, float],  # annualised vol per symbol
        **kwargs,
    ) -> list[AllocationWeight]:
        """Return normalised weights summing to 1.0."""
        ...


# ──────────────────────────────────────────────────────────────────────
# 1. Equal Weight
# ──────────────────────────────────────────────────────────────────────

class EqualWeightModel(AllocationModel):
    def allocate(
        self,
        symbols: list[str],
        strategy_names: list[str],
        volatilities: dict[str, float],
        **kwargs,
    ) -> list[AllocationWeight]:
        if not symbols:
            return []
        n = len(symbols)
        w = 1.0 / n
        return [
            AllocationWeight(
                symbol=sym,
                strategy_name=strategy_names[i] if i < len(strategy_names) else "",
                weight=w,
                model=AllocationModelType.EQUAL_WEIGHT,
                volatility=volatilities.get(sym),
            )
            for i, sym in enumerate(symbols)
        ]


# ──────────────────────────────────────────────────────────────────────
# 2. Inverse Volatility Weighting
# ──────────────────────────────────────────────────────────────────────

class InverseVolatilityModel(AllocationModel):
    """
    Weight each asset by 1/vol, then normalise.
    Lower volatility → higher allocation.
    """

    def allocate(
        self,
        symbols: list[str],
        strategy_names: list[str],
        volatilities: dict[str, float],
        **kwargs,
    ) -> list[AllocationWeight]:
        if not symbols:
            return []

        inv_vols: list[float] = []
        for sym in symbols:
            vol = volatilities.get(sym, 0.0)
            inv_vols.append(1.0 / max(vol, _TINY))

        total = sum(inv_vols)
        if total <= 0:
            return EqualWeightModel().allocate(symbols, strategy_names, volatilities)

        return [
            AllocationWeight(
                symbol=sym,
                strategy_name=strategy_names[i] if i < len(strategy_names) else "",
                weight=inv_vols[i] / total,
                model=AllocationModelType.INVERSE_VOLATILITY,
                volatility=volatilities.get(sym),
            )
            for i, sym in enumerate(symbols)
        ]


# ──────────────────────────────────────────────────────────────────────
# 3. Equal Risk Contribution (ERC)
# ──────────────────────────────────────────────────────────────────────

class EqualRiskContributionModel(AllocationModel):
    """
    Each asset contributes equal risk to the portfolio.

    Iterative Newton-style algorithm converging to ERC weights.
    For diagonal covariance (no pairwise correlation) this simplifies
    to inverse-vol; with a full cov matrix it iterates to ERC.
    """

    def __init__(self, max_iter: int = 200, tolerance: float = 1e-8) -> None:
        self._max_iter = max_iter
        self._tolerance = tolerance

    def allocate(
        self,
        symbols: list[str],
        strategy_names: list[str],
        volatilities: dict[str, float],
        cov_matrix: list[list[float]] | None = None,  # n×n
        **kwargs,
    ) -> list[AllocationWeight]:
        if not symbols:
            return []

        n = len(symbols)
        vols = [max(volatilities.get(sym, 0.01), _TINY) for sym in symbols]

        # Build covariance matrix (diagonal if not provided)
        if cov_matrix is None or len(cov_matrix) != n:
            cov = [[vols[i] ** 2 if i == j else 0.0 for j in range(n)] for i in range(n)]
        else:
            cov = cov_matrix

        # Start with inverse-vol weights
        inv_v = [1.0 / v for v in vols]
        total = sum(inv_v)
        weights = [x / total for x in inv_v]

        for _ in range(self._max_iter):
            # Portfolio variance = w^T Σ w
            port_var = sum(
                weights[i] * weights[j] * cov[i][j]
                for i in range(n)
                for j in range(n)
            )
            port_std = max(port_var ** 0.5, _TINY)

            # Marginal risk contributions
            mrc = [
                sum(weights[j] * cov[i][j] for j in range(n)) / port_std
                for i in range(n)
            ]
            # Risk contributions
            rc = [weights[i] * mrc[i] for i in range(n)]
            target_rc = port_std / n

            # Gradient step
            new_weights = [
                max(_TINY, weights[i] * target_rc / max(rc[i], _TINY))
                for i in range(n)
            ]
            total_w = sum(new_weights)
            new_weights = [w / total_w for w in new_weights]

            # Check convergence
            diff = max(abs(new_weights[i] - weights[i]) for i in range(n))
            weights = new_weights
            if diff < self._tolerance:
                break

        return [
            AllocationWeight(
                symbol=symbols[i],
                strategy_name=strategy_names[i] if i < len(strategy_names) else "",
                weight=weights[i],
                model=AllocationModelType.EQUAL_RISK,
                volatility=vols[i],
            )
            for i in range(n)
        ]


# ──────────────────────────────────────────────────────────────────────
# 4. Strategy Performance Allocation
# ──────────────────────────────────────────────────────────────────────

class StrategyPerformanceAllocationModel(AllocationModel):
    """
    Allocate capital across strategies based on rolling performance scores.

    scores: dict[strategy_name → float] (higher = better, e.g. Sharpe)
    Negative scores are clipped to zero (don't allocate to underperforming strategies).
    """

    def allocate(
        self,
        symbols: list[str],
        strategy_names: list[str],
        volatilities: dict[str, float],
        strategy_scores: dict[str, float] | None = None,
        **kwargs,
    ) -> list[AllocationWeight]:
        if not symbols:
            return []

        scores = strategy_scores or {}
        raw = [max(0.0, scores.get(strategy_names[i] if i < len(strategy_names) else "", 0.0)) for i in range(len(symbols))]
        total = sum(raw)

        if total <= 0:
            # Fall back to equal weight
            return EqualWeightModel().allocate(symbols, strategy_names, volatilities)

        return [
            AllocationWeight(
                symbol=symbols[i],
                strategy_name=strategy_names[i] if i < len(strategy_names) else "",
                weight=raw[i] / total,
                model=AllocationModelType.STRATEGY_PERFORMANCE,
                volatility=volatilities.get(symbols[i]),
            )
            for i in range(len(symbols))
        ]


# ──────────────────────────────────────────────────────────────────────
# Factory
# ──────────────────────────────────────────────────────────────────────

def get_allocation_model(model_type: AllocationModelType) -> AllocationModel:
    mapping: dict[AllocationModelType, AllocationModel] = {
        AllocationModelType.EQUAL_WEIGHT: EqualWeightModel(),
        AllocationModelType.INVERSE_VOLATILITY: InverseVolatilityModel(),
        AllocationModelType.EQUAL_RISK: EqualRiskContributionModel(),
        AllocationModelType.STRATEGY_PERFORMANCE: StrategyPerformanceAllocationModel(),
    }
    return mapping.get(model_type, EqualWeightModel())

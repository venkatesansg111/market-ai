"""Data models for Phase 6 Meta Strategy Engine."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class RegimeType(str, Enum):
    """Market regime classification."""

    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"


class RoutingMode(str, Enum):
    """Strategy routing mode."""

    SINGLE_BEST = "single_best"
    WEIGHTED_BLEND = "weighted_blend"


@dataclass(frozen=True)
class MarketRegime:
    """Detected market regime for an instrument + timeframe at a point in time."""

    regime_type: RegimeType
    confidence: float
    timestamp: datetime
    supporting_features: dict[str, Any]

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")


@dataclass(frozen=True)
class StrategyScore:
    """Score of a single strategy for a given regime."""

    strategy_name: str
    regime_type: RegimeType
    score: float
    confidence: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 100.0:
            raise ValueError(f"score must be in [0, 100], got {self.score}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")


@dataclass(frozen=True)
class MetaSignal:
    """Output signal from the Meta Strategy Engine."""

    instrument: str
    timeframe: str
    selected_strategy: str
    regime_type: RegimeType
    confidence: float
    strategy_weights: dict[str, float]
    routing_mode: RoutingMode
    reasoning: str
    timestamp: datetime
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")


@dataclass
class StrategyPerformanceRecord:
    """Single performance measurement for a strategy in a given regime."""

    strategy_name: str
    regime_type: RegimeType
    sharpe: float
    cagr: float
    max_drawdown: float
    win_rate: float
    expectancy: float
    total_trades: int
    recorded_at: datetime = field(default_factory=datetime.utcnow)

    def composite_score(self) -> float:
        """Compute a single [0, 1] performance score from multiple metrics."""
        if self.total_trades < 5:
            return 0.0

        sharpe_norm = min(max(self.sharpe / 3.0, 0.0), 1.0)
        cagr_norm = min(max(self.cagr / 50.0, 0.0), 1.0)
        dd_norm = 1.0 - min(max(self.max_drawdown / 50.0, 0.0), 1.0)
        wr_norm = min(max(self.win_rate / 100.0, 0.0), 1.0)
        exp_norm = min(max(self.expectancy / 500.0, 0.0), 1.0)

        return (
            sharpe_norm * 0.30
            + cagr_norm * 0.25
            + dd_norm * 0.20
            + wr_norm * 0.15
            + exp_norm * 0.10
        )


@dataclass
class LearningState:
    """Persisted state of the adaptive learning engine."""

    scoring_overrides: dict[str, dict[str, float]]
    regime_weights: dict[str, dict[str, float]]
    performance_history: dict[str, list[float]]
    last_updated: datetime
    version: int = 1

    @classmethod
    def empty(cls) -> LearningState:
        return cls(
            scoring_overrides={},
            regime_weights={},
            performance_history={},
            last_updated=datetime.utcnow(),
            version=1,
        )

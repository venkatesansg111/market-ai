"""Data models for Phase 5 optimization, ranking, regime analysis, and research reporting."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass(frozen=True)
class OptimizationWindow:
    """Single train/test time split for walk-forward analysis."""

    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    window_type: str  # "rolling" or "expanding"
    window_index: int

    @property
    def train_days(self) -> int:
        return (self.train_end - self.train_start).days

    @property
    def test_days(self) -> int:
        return (self.test_end - self.test_start).days


@dataclass
class OptimizationResult:
    """Result of running a single parameter combination over a date range."""

    run_id: str
    strategy_name: str
    instrument: str
    timeframe: str
    parameters: dict[str, Any]
    timeframe_config: dict[str, str]
    train_start: Optional[datetime]
    train_end: Optional[datetime]
    test_start: datetime
    test_end: datetime
    cagr: float
    sharpe: float
    sortino: float
    max_drawdown: float
    profit_factor: float
    win_rate: float
    expectancy: float
    total_trades: int
    created_at: datetime = field(default_factory=datetime.utcnow)

    @staticmethod
    def new_run_id() -> str:
        return str(uuid.uuid4())


@dataclass(frozen=True)
class RankingScore:
    """Weighted composite ranking score for a strategy+parameter combination."""

    rank: int
    strategy_name: str
    parameters: dict
    composite_score: float
    cagr: float
    sharpe: float
    sortino: float
    profit_factor: float
    win_rate: float
    max_drawdown: float


@dataclass(frozen=True)
class RegimeResult:
    """Strategy performance statistics within a specific market regime period."""

    strategy_name: str
    instrument: str
    timeframe: str
    regime: str  # "trending" | "ranging" | "high_volatility" | "low_volatility"
    period_start: datetime
    period_end: datetime
    cagr: float
    sharpe: float
    win_rate: float
    total_trades: int


@dataclass
class ResearchReport:
    """Aggregated research report combining all Phase 5 analyses."""

    title: str
    generated_at: datetime
    instrument: str
    timeframe: str
    analysis_start: datetime
    analysis_end: datetime
    strategy_rankings: list[RankingScore]
    regime_results: list[RegimeResult]
    optimization_results: list[OptimizationResult]
    walk_forward_results: list[OptimizationResult]
    parameter_winners: dict[str, Any]
    summary: dict[str, Any]

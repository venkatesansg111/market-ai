"""Phase 5 — Quant Research Lab.

Exports the primary service and supporting models for parameter optimization,
walk-forward analysis, strategy ranking, regime analysis, and research reporting.
"""
from __future__ import annotations

from optimization.optimization_models import (
    OptimizationResult,
    OptimizationWindow,
    RankingScore,
    RegimeResult,
    ResearchReport,
)
from optimization.parameter_grid import ParameterGridGenerator
from optimization.regime_analysis import RegimeAnalyzer
from optimization.research_engine import ResearchEngineService
from optimization.strategy_optimizer import StrategyOptimizer
from optimization.strategy_ranker import StrategyRanker
from optimization.walk_forward import WalkForwardOptimizer

__all__ = [
    "OptimizationResult",
    "OptimizationWindow",
    "ParameterGridGenerator",
    "RankingScore",
    "RegimeAnalyzer",
    "RegimeResult",
    "ResearchEngineService",
    "ResearchReport",
    "StrategyOptimizer",
    "StrategyRanker",
    "WalkForwardOptimizer",
]

"""ORM models for Phase 5 optimization tables."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database.models import Base


class OptimizationRun(Base):
    """One optimization run (single strategy + param combo backtest)."""

    __tablename__ = "optimization_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    strategy_name: Mapped[str] = mapped_column(String(100), nullable=False)
    instrument: Mapped[str] = mapped_column(String(50), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    parameters: Mapped[str] = mapped_column(Text, nullable=False)
    train_start: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    train_end: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    test_start: Mapped[datetime] = mapped_column(nullable=False)
    test_end: Mapped[datetime] = mapped_column(nullable=False)
    cagr: Mapped[float] = mapped_column(Float, nullable=False)
    sharpe: Mapped[float] = mapped_column(Float, nullable=False)
    sortino: Mapped[float] = mapped_column(Float, nullable=False)
    max_drawdown: Mapped[float] = mapped_column(Float, nullable=False)
    profit_factor: Mapped[float] = mapped_column(Float, nullable=False)
    win_rate: Mapped[float] = mapped_column(Float, nullable=False)
    expectancy: Mapped[float] = mapped_column(Float, nullable=False)
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_opt_runs_strategy_instrument", "strategy_name", "instrument"),
        Index("ix_opt_runs_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<OptimizationRun {self.strategy_name} {self.instrument} cagr={self.cagr:.2f}>"


class StrategyRanking(Base):
    """Persisted ranking score for a strategy + parameter combination."""

    __tablename__ = "strategy_rankings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    strategy_name: Mapped[str] = mapped_column(String(100), nullable=False)
    parameters: Mapped[str] = mapped_column(Text, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    composite_score: Mapped[float] = mapped_column(Float, nullable=False)
    cagr: Mapped[float] = mapped_column(Float, nullable=False)
    sharpe: Mapped[float] = mapped_column(Float, nullable=False)
    sortino: Mapped[float] = mapped_column(Float, nullable=False)
    profit_factor: Mapped[float] = mapped_column(Float, nullable=False)
    win_rate: Mapped[float] = mapped_column(Float, nullable=False)
    max_drawdown: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_strategy_rankings_name_score", "strategy_name", "composite_score"),
    )

    def __repr__(self) -> str:
        return f"<StrategyRanking #{self.rank} {self.strategy_name} score={self.composite_score:.4f}>"


class RegimeAnalysisResult(Base):
    """Backtest result for a strategy within a specific market regime period."""

    __tablename__ = "regime_analysis_results"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    strategy_name: Mapped[str] = mapped_column(String(100), nullable=False)
    instrument: Mapped[str] = mapped_column(String(50), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    regime: Mapped[str] = mapped_column(String(30), nullable=False)
    period_start: Mapped[datetime] = mapped_column(nullable=False)
    period_end: Mapped[datetime] = mapped_column(nullable=False)
    cagr: Mapped[float] = mapped_column(Float, nullable=False)
    sharpe: Mapped[float] = mapped_column(Float, nullable=False)
    win_rate: Mapped[float] = mapped_column(Float, nullable=False)
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_regime_results_strategy_regime", "strategy_name", "regime"),
        Index("ix_regime_results_instrument_tf", "instrument", "timeframe"),
    )

    def __repr__(self) -> str:
        return (
            f"<RegimeAnalysisResult {self.strategy_name} {self.regime} "
            f"{self.period_start.date()} → {self.period_end.date()}>"
        )

"""ORM models for Phase 6 Meta Strategy Engine tables."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.models import Base


class MetaStrategyRun(Base):
    """Records each meta strategy analysis run and its output signal."""

    __tablename__ = "meta_strategy_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    instrument: Mapped[str] = mapped_column(String(50), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    regime_type: Mapped[str] = mapped_column(String(30), nullable=False)
    regime_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    selected_strategy: Mapped[str] = mapped_column(String(100), nullable=False)
    routing_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    strategy_weights: Mapped[str] = mapped_column(Text, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    signal_timestamp: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_meta_runs_instrument_tf", "instrument", "timeframe"),
        Index("ix_meta_runs_regime", "regime_type"),
        Index("ix_meta_runs_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<MetaStrategyRun {self.instrument} {self.timeframe} "
            f"regime={self.regime_type} strategy={self.selected_strategy}>"
        )


class StrategyRegimePerformance(Base):
    """Performance record for a strategy operating in a specific market regime."""

    __tablename__ = "strategy_regime_performance"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    strategy_name: Mapped[str] = mapped_column(String(100), nullable=False)
    regime_type: Mapped[str] = mapped_column(String(30), nullable=False)
    sharpe: Mapped[float] = mapped_column(Float, nullable=False)
    cagr: Mapped[float] = mapped_column(Float, nullable=False)
    max_drawdown: Mapped[float] = mapped_column(Float, nullable=False)
    win_rate: Mapped[float] = mapped_column(Float, nullable=False)
    expectancy: Mapped[float] = mapped_column(Float, nullable=False)
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    composite_score: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_srp_strategy_regime", "strategy_name", "regime_type"),
        Index("ix_srp_recorded_at", "recorded_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<StrategyRegimePerformance {self.strategy_name} {self.regime_type} "
            f"sharpe={self.sharpe:.2f} cagr={self.cagr:.1f}>"
        )


class StrategyWeightHistory(Base):
    """Historical snapshot of strategy weights for a given regime."""

    __tablename__ = "strategy_weight_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    regime_type: Mapped[str] = mapped_column(String(30), nullable=False)
    strategy_name: Mapped[str] = mapped_column(String(100), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_swh_regime_strategy", "regime_type", "strategy_name"),
        Index("ix_swh_recorded_at", "recorded_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<StrategyWeightHistory {self.strategy_name} {self.regime_type} "
            f"weight={self.weight:.4f}>"
        )


class LearningStateSnapshot(Base):
    """JSON snapshot of the adaptive learning engine state."""

    __tablename__ = "learning_state_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_lss_version", "version"),
        Index("ix_lss_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<LearningStateSnapshot v{self.version} at {self.created_at}>"

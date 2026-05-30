from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.models import Base


class BacktestRun(Base):
    """One row per backtest execution — summary of performance metrics."""

    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_name: Mapped[str] = mapped_column(String(200), nullable=False)
    strategy_name: Mapped[str] = mapped_column(String(100), nullable=False)
    instrument: Mapped[str] = mapped_column(String(50), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(20), nullable=False)
    start_date: Mapped[datetime] = mapped_column(nullable=False)
    end_date: Mapped[datetime] = mapped_column(nullable=False)
    starting_capital: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    ending_capital: Mapped[Optional[float]] = mapped_column(Numeric(18, 2), nullable=True)
    total_return_pct: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    max_drawdown_pct: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    win_rate_pct: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    sharpe_ratio: Mapped[Optional[float]] = mapped_column(Numeric(10, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    trades: Mapped[list["BacktestTrade"]] = relationship("BacktestTrade", back_populates="run", cascade="all, delete-orphan")
    snapshots: Mapped[list["PortfolioSnapshot"]] = relationship("PortfolioSnapshot", back_populates="run", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_backtest_runs_run_name", "run_name"),
        Index("ix_backtest_runs_created_at", "created_at"),
    )


class BacktestTrade(Base):
    """One row per completed round-trip trade within a backtest run."""

    __tablename__ = "backtest_trades"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("backtest_runs.id", ondelete="CASCADE"), nullable=False)
    instrument: Mapped[str] = mapped_column(String(50), nullable=False)
    entry_time: Mapped[datetime] = mapped_column(nullable=False)
    exit_time: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    entry_price: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    exit_price: Mapped[Optional[float]] = mapped_column(Numeric(18, 4), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    gross_pnl: Mapped[Optional[float]] = mapped_column(Numeric(18, 2), nullable=True)
    net_pnl: Mapped[Optional[float]] = mapped_column(Numeric(18, 2), nullable=True)
    commission: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    slippage: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    holding_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    run: Mapped["BacktestRun"] = relationship("BacktestRun", back_populates="trades")

    __table_args__ = (
        Index("ix_backtest_trades_run_id", "run_id"),
        Index("ix_backtest_trades_run_entry", "run_id", "entry_time"),
    )


class PortfolioSnapshot(Base):
    """Point-in-time portfolio state snapshot for equity curve reconstruction."""

    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("backtest_runs.id", ondelete="CASCADE"), nullable=False)
    snapshot_time: Mapped[datetime] = mapped_column(nullable=False)
    cash: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    equity: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    unrealized_pnl: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    drawdown_pct: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    run: Mapped["BacktestRun"] = relationship("BacktestRun", back_populates="snapshots")

    __table_args__ = (
        Index("ix_portfolio_snapshots_run_time", "run_id", "snapshot_time"),
    )


def create_backtest_tables() -> None:
    from database.connection import get_engine
    from utils.logger import get_logger
    from config import settings

    log = get_logger(__name__, settings.log_dir, settings.log_level)
    Base.metadata.create_all(get_engine())
    log.info("Backtest tables ensured.")

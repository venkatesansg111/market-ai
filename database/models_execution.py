"""ORM models for Phase 7 Execution Engine tables."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Float, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.models import Base


class ExecutionOrder(Base):
    """Persisted order record — final state snapshot."""

    __tablename__ = "execution_orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    order_type: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    filled_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    strategy_name: Mapped[str] = mapped_column(String(100), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(36), nullable=False)
    average_fill_price: Mapped[Optional[float]] = mapped_column(Numeric(20, 6), nullable=True)
    limit_price: Mapped[Optional[float]] = mapped_column(Numeric(20, 6), nullable=True)
    stop_price: Mapped[Optional[float]] = mapped_column(Numeric(20, 6), nullable=True)
    broker_order_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    reject_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    filled_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    rejected_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    __table_args__ = (
        Index("ix_exec_orders_symbol", "symbol"),
        Index("ix_exec_orders_status", "status"),
        Index("ix_exec_orders_strategy", "strategy_name"),
        Index("ix_exec_orders_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<ExecutionOrder {self.symbol} {self.side} {self.quantity} "
            f"status={self.status}>"
        )


class ExecutionFill(Base):
    """Individual fill events linked to an order."""

    __tablename__ = "execution_fills"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fill_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    order_id: Mapped[str] = mapped_column(String(36), nullable=False)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    commission: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    fill_timestamp: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_exec_fills_order_id", "order_id"),
        Index("ix_exec_fills_symbol", "symbol"),
        Index("ix_exec_fills_timestamp", "fill_timestamp"),
    )

    def __repr__(self) -> str:
        return f"<ExecutionFill {self.symbol} qty={self.quantity} @ {self.price}>"


class ExecutionPosition(Base):
    """Current position snapshots persisted after each fill."""

    __tablename__ = "execution_positions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    average_price: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    last_updated: Mapped[datetime] = mapped_column(nullable=False)
    snapshot_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_exec_positions_symbol", "symbol"),
        Index("ix_exec_positions_snapshot_at", "snapshot_at"),
    )

    def __repr__(self) -> str:
        return f"<ExecutionPosition {self.symbol} qty={self.quantity} avg={self.average_price}>"

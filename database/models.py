from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    Float,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class MarketCandle(Base):
    """One OHLCV candle for a given instrument + timeframe."""

    __tablename__ = "market_candles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instrument: Mapped[str] = mapped_column(String(50), nullable=False)
    candle_time: Mapped[datetime] = mapped_column(nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=True)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)

    __table_args__ = (
        # Prevents duplicate candles
        UniqueConstraint(
            "instrument", "candle_time", "timeframe",
            name="uq_market_candles_instrument_time_tf",
        ),
        # Fast lookup by instrument + timeframe + time range
        Index("ix_market_candles_instr_tf_time", "instrument", "timeframe", "candle_time"),
    )

    def __repr__(self) -> str:
        return (
            f"<MarketCandle {self.instrument} {self.timeframe} "
            f"{self.candle_time} O={self.open} H={self.high} "
            f"L={self.low} C={self.close}>"
        )


def create_tables() -> None:
    from database.connection import get_engine
    from utils.logger import get_logger
    from config import settings

    log = get_logger(__name__, settings.log_dir, settings.log_level)
    Base.metadata.create_all(get_engine())
    log.info("Database tables ensured.")

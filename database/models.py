from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Float,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
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
        UniqueConstraint(
            "instrument", "candle_time", "timeframe",
            name="uq_market_candles_instrument_time_tf",
        ),
        Index("ix_market_candles_instr_tf_time", "instrument", "timeframe", "candle_time"),
    )

    def __repr__(self) -> str:
        return (
            f"<MarketCandle {self.instrument} {self.timeframe} "
            f"{self.candle_time} O={self.open} H={self.high} "
            f"L={self.low} C={self.close}>"
        )


class MarketTick(Base):
    """Raw tick-level price data — persisted for audit and replay."""

    __tablename__ = "market_ticks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instrument: Mapped[str] = mapped_column(String(50), nullable=False)
    tick_time: Mapped[datetime] = mapped_column(nullable=False)
    price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    __table_args__ = (
        Index("ix_market_ticks_instr_time", "instrument", "tick_time"),
    )


class MarketRealtimeStatus(Base):
    """One row per (instrument, timeframe) — tracks pipeline processing watermarks."""

    __tablename__ = "market_realtime_status"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instrument: Mapped[str] = mapped_column(String(50), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    last_tick_time: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_candle_time: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_indicator_time: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_signal_time: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "instrument", "timeframe",
            name="uq_realtime_status_instr_tf",
        ),
    )


class MarketIndicator(Base):
    """Computed technical indicators for each (instrument, timeframe, candle_time)."""

    __tablename__ = "market_indicators"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instrument: Mapped[str] = mapped_column(String(50), nullable=False)
    candle_time: Mapped[datetime] = mapped_column(nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    ema20: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    ema50: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    ema200: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    rsi14: Mapped[Optional[float]] = mapped_column(Numeric(8, 4), nullable=True)
    vwap: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    macd: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    macd_signal: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    # ── Phase 4B advanced indicators ─────────────────────────────────────
    atr_14: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    adx_14: Mapped[Optional[float]] = mapped_column(Numeric(8, 4), nullable=True)
    plus_di: Mapped[Optional[float]] = mapped_column(Numeric(8, 4), nullable=True)
    minus_di: Mapped[Optional[float]] = mapped_column(Numeric(8, 4), nullable=True)
    bb_middle: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    bb_upper: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    bb_lower: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    bb_width: Mapped[Optional[float]] = mapped_column(Numeric(10, 8), nullable=True)
    supertrend: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    supertrend_direction: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    obv: Mapped[Optional[float]] = mapped_column(Numeric(18, 2), nullable=True)
    stoch_rsi_k: Mapped[Optional[float]] = mapped_column(Numeric(8, 4), nullable=True)
    stoch_rsi_d: Mapped[Optional[float]] = mapped_column(Numeric(8, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "instrument", "candle_time", "timeframe",
            name="uq_market_indicators_instr_time_tf",
        ),
        Index("ix_market_indicators_instr_tf_time", "instrument", "timeframe", "candle_time"),
    )


class TradeSignal(Base):
    """Trade signals generated by the signal engine for each (instrument, timeframe)."""

    __tablename__ = "trade_signals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instrument: Mapped[str] = mapped_column(String(50), nullable=False)
    signal_time: Mapped[datetime] = mapped_column(nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "instrument", "signal_time", "timeframe",
            name="uq_trade_signals_instr_time_tf",
        ),
        Index("ix_trade_signals_instr_time", "instrument", "signal_time"),
    )


def create_tables() -> None:
    from database.connection import get_engine
    from sqlalchemy import text
    from utils.logger import get_logger
    from config import settings

    log = get_logger(__name__, settings.log_dir, settings.log_level)
    engine = get_engine()
    Base.metadata.create_all(engine)
    _migrate_market_indicators(engine, log)
    log.info("Database tables ensured.")


# ---------------------------------------------------------------------------
# Schema migration — adds Phase 4B columns to market_indicators.
# Uses ADD COLUMN IF NOT EXISTS so it is safe to run on every startup.
# ---------------------------------------------------------------------------

_PHASE_4B_COLUMNS: list[tuple[str, str]] = [
    ("atr_14",               "NUMERIC(18,6)"),
    ("adx_14",               "NUMERIC(8,4)"),
    ("plus_di",              "NUMERIC(8,4)"),
    ("minus_di",             "NUMERIC(8,4)"),
    ("bb_middle",            "NUMERIC(18,6)"),
    ("bb_upper",             "NUMERIC(18,6)"),
    ("bb_lower",             "NUMERIC(18,6)"),
    ("bb_width",             "NUMERIC(10,8)"),
    ("supertrend",           "NUMERIC(18,6)"),
    ("supertrend_direction", "INTEGER"),
    ("obv",                  "NUMERIC(18,2)"),
    ("stoch_rsi_k",          "NUMERIC(8,4)"),
    ("stoch_rsi_d",          "NUMERIC(8,4)"),
]


def _migrate_market_indicators(engine, log) -> None:
    """Add Phase 4B columns to market_indicators if they don't already exist.

    ADD COLUMN IF NOT EXISTS is idempotent — safe to run on every startup.
    """
    with engine.begin() as conn:
        for col_name, col_type in _PHASE_4B_COLUMNS:
            stmt = text(
                f"ALTER TABLE market_indicators "
                f"ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
            )
            conn.execute(stmt)
    log.info("market_indicators Phase 4B columns ensured.")

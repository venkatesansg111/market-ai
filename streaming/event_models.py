"""Phase 9 — Streaming event types for the event-driven trading engine."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import ClassVar, Optional


# ──────────────────────────────────────────────────────────────────────
# Base
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class StreamEvent:
    """Base class for all streaming events."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)


# ──────────────────────────────────────────────────────────────────────
# Market data
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TickEvent(StreamEvent):
    """Raw price tick from the market feed."""
    symbol: str = ""
    price: Decimal = field(default_factory=lambda: Decimal("0"))
    volume: int = 0
    bid: Optional[Decimal] = None
    ask: Optional[Decimal] = None


@dataclass(frozen=True)
class CandleEvent(StreamEvent):
    """OHLCV candle — emitted when a time bucket closes."""
    symbol: str = ""
    timeframe: str = ""           # "1m", "5m", "15m", "1h"
    open: Decimal = field(default_factory=lambda: Decimal("0"))
    high: Decimal = field(default_factory=lambda: Decimal("0"))
    low: Decimal = field(default_factory=lambda: Decimal("0"))
    close: Decimal = field(default_factory=lambda: Decimal("0"))
    volume: int = 0
    is_closed: bool = True        # False = live / in-progress candle
    candle_open_time: Optional[datetime] = None   # bucket start time


# ──────────────────────────────────────────────────────────────────────
# Derived data
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class IndicatorEvent(StreamEvent):
    """Technical indicator values computed from a closed candle."""
    symbol: str = ""
    timeframe: str = ""
    close: float = 0.0
    high: float = 0.0
    low: float = 0.0
    volume: int = 0
    ema_fast: Optional[float] = None      # e.g. EMA(9)
    ema_slow: Optional[float] = None      # e.g. EMA(21)
    ema_200: Optional[float] = None       # EMA(200)
    rsi: Optional[float] = None           # RSI(14)
    vwap: Optional[float] = None          # session VWAP
    volatility: Optional[float] = None   # rolling return std-dev
    atr: Optional[float] = None           # ATR(14)
    is_warm: bool = False                  # True when all requested indicators ready


@dataclass(frozen=True)
class SignalEvent(StreamEvent):
    """Trading signal emitted by a strategy."""
    symbol: str = ""
    strategy_name: str = ""
    action: str = "FLAT"            # "BUY" | "SELL" | "FLAT"
    confidence: float = 0.0         # 0–1
    timeframe: str = ""
    current_price: Decimal = field(default_factory=lambda: Decimal("0"))
    atr: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    regime: str = ""
    regime_strength: float = 0.5
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))


# ──────────────────────────────────────────────────────────────────────
# Risk / Execution
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RiskEvent(StreamEvent):
    """Risk gate decision for a signal."""
    symbol: str = ""
    strategy_name: str = ""
    decision: str = ""              # "APPROVED" | "REDUCED" | "BLOCKED"
    approved_quantity: int = 0
    original_quantity: int = 0
    reason: str = ""


@dataclass(frozen=True)
class OrderEvent(StreamEvent):
    """Order submitted to the execution engine."""
    order_id: str = ""
    symbol: str = ""
    action: str = ""                # "BUY" | "SELL"
    quantity: int = 0
    order_type: str = "MARKET"
    strategy_name: str = ""


@dataclass(frozen=True)
class FillEvent(StreamEvent):
    """Execution fill — broker confirmed trade."""
    order_id: str = ""
    symbol: str = ""
    quantity: int = 0
    price: Decimal = field(default_factory=lambda: Decimal("0"))
    strategy_name: str = ""
    action: str = ""                # "BUY" | "SELL"
    commission: Decimal = field(default_factory=lambda: Decimal("0"))


@dataclass(frozen=True)
class PortfolioEvent(StreamEvent):
    """Portfolio state snapshot after a fill."""
    equity: Decimal = field(default_factory=lambda: Decimal("0"))
    cash: Decimal = field(default_factory=lambda: Decimal("0"))
    unrealized_pnl: Decimal = field(default_factory=lambda: Decimal("0"))
    realized_pnl: Decimal = field(default_factory=lambda: Decimal("0"))
    daily_pnl: Decimal = field(default_factory=lambda: Decimal("0"))
    current_drawdown_pct: float = 0.0


# ──────────────────────────────────────────────────────────────────────
# System control
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SystemEvent(StreamEvent):
    """Control / diagnostic events."""
    kind: str = ""     # "start" | "stop" | "health_check" | "error"
    message: str = ""
    component: str = ""

"""Phase 7 — Execution Engine data models."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional


class OrderStatus(str, Enum):
    NEW = "new"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderEventType(str, Enum):
    CREATED = "created"
    SUBMITTED = "submitted"
    FILL = "fill"
    PARTIAL_FILL = "partial_fill"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


# Valid state transitions: {from_status: set of allowed to_status}
VALID_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.NEW: {
        OrderStatus.SUBMITTED,
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED,
    },
    OrderStatus.SUBMITTED: {
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED,
    },
    OrderStatus.PARTIALLY_FILLED: {
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.FILLED: set(),
    OrderStatus.CANCELLED: set(),
    OrderStatus.REJECTED: set(),
}


@dataclass(frozen=True)
class Fill:
    """A single fill event for an order."""

    fill_id: str
    order_id: str
    quantity: int
    price: Decimal
    timestamp: datetime
    commission: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError(f"Fill quantity must be > 0, got {self.quantity}")
        if self.price <= Decimal("0"):
            raise ValueError(f"Fill price must be > 0, got {self.price}")


@dataclass(frozen=True)
class Order:
    """Immutable order snapshot. Updated via dataclasses.replace()."""

    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    status: OrderStatus
    created_at: datetime
    strategy_name: str
    timeframe: str
    reference_id: str

    filled_quantity: int = 0
    average_fill_price: Optional[Decimal] = None
    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    reject_reason: Optional[str] = None
    broker_order_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def remaining_quantity(self) -> int:
        return self.quantity - self.filled_quantity

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
        )


@dataclass(frozen=True)
class OrderEvent:
    """Immutable record of an order state transition."""

    event_id: str
    order_id: str
    event_type: OrderEventType
    timestamp: datetime
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Position:
    """Current position for a symbol."""

    symbol: str
    quantity: int          # negative = short
    average_price: Decimal
    realized_pnl: Decimal = Decimal("0")
    last_updated: datetime = field(default_factory=datetime.utcnow)

    @property
    def market_value(self) -> Decimal:
        return Decimal(str(self.quantity)) * self.average_price

    @property
    def is_flat(self) -> bool:
        return self.quantity == 0


@dataclass(frozen=True)
class ExecutionRequest:
    """Bridge from MetaSignal / strategy signal to broker order parameters."""

    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    current_price: Decimal
    strategy_name: str
    timeframe: str
    confidence: float
    reference_id: str

    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionResult:
    """Result of processing an ExecutionRequest through the engine."""

    order_id: str
    symbol: str
    status: OrderStatus
    fills: list[Fill]
    message: str = ""

    @property
    def total_filled_quantity(self) -> int:
        return sum(f.quantity for f in self.fills)

    @property
    def average_fill_price(self) -> Optional[Decimal]:
        if not self.fills:
            return None
        total_qty = sum(f.quantity for f in self.fills)
        if total_qty == 0:
            return None
        total_value = sum(f.price * Decimal(str(f.quantity)) for f in self.fills)
        return total_value / Decimal(str(total_qty))


@dataclass(frozen=True)
class BrokerResponse:
    """Response from a broker adapter after order submission."""

    success: bool
    broker_order_id: Optional[str]
    fills: list[Fill]
    status: OrderStatus
    message: str = ""


@dataclass(frozen=True)
class BrokerPosition:
    """Position as reported by the broker."""

    symbol: str
    quantity: int
    average_price: Decimal


@dataclass(frozen=True)
class AccountInfo:
    """Broker account snapshot."""

    account_id: str
    cash_balance: Decimal
    portfolio_value: Decimal
    buying_power: Decimal
    currency: str = "INR"


@dataclass
class ReconciliationResult:
    """Result of reconciling local positions against broker positions."""

    matched: list[str]       # symbols in sync
    mismatched: list[str]    # symbols with qty/price differences
    only_local: list[str]    # symbols only in local state
    only_broker: list[str]   # symbols only at broker

    @property
    def is_clean(self) -> bool:
        return not self.mismatched and not self.only_local and not self.only_broker

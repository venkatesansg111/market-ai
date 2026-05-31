"""Phase 7 — Thread-safe Order Management System."""
from __future__ import annotations

import threading
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Callable, Optional

import dataclasses

from execution.execution_models import (
    Fill,
    Order,
    OrderEvent,
    OrderEventType,
    OrderSide,
    OrderStatus,
    OrderType,
    VALID_TRANSITIONS,
)


class InvalidTransitionError(Exception):
    """Raised when an illegal order state transition is attempted."""


class OrderNotFoundError(Exception):
    """Raised when an order_id is not found in the OMS."""


class OrderManager:
    """Thread-safe OMS.

    Orders are stored as immutable snapshots; every mutation returns a new
    Order object via dataclasses.replace() and appends an OrderEvent.
    """

    def __init__(self, on_event: Optional[Callable[[OrderEvent], None]] = None) -> None:
        self._lock = threading.RLock()
        self._orders: dict[str, Order] = {}
        self._events: dict[str, list[OrderEvent]] = {}  # order_id → events
        self._on_event = on_event  # optional callback for event bus

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: int,
        strategy_name: str,
        timeframe: str,
        reference_id: str,
        limit_price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        metadata: Optional[dict] = None,
        order_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> Order:
        """Create a new order in NEW status and return it."""
        if quantity <= 0:
            raise ValueError(f"quantity must be > 0, got {quantity}")

        oid = order_id or str(uuid.uuid4())
        ts = timestamp or datetime.utcnow()

        order = Order(
            order_id=oid,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            status=OrderStatus.NEW,
            created_at=ts,
            strategy_name=strategy_name,
            timeframe=timeframe,
            reference_id=reference_id,
            limit_price=limit_price,
            stop_price=stop_price,
            metadata=metadata or {},
        )

        with self._lock:
            self._orders[oid] = order
            self._events[oid] = []
            self._emit(OrderEvent(
                event_id=str(uuid.uuid4()),
                order_id=oid,
                event_type=OrderEventType.CREATED,
                timestamp=ts,
            ))

        return order

    def submit_order(self, order_id: str, broker_order_id: Optional[str] = None,
                     timestamp: Optional[datetime] = None) -> Order:
        """Transition order from NEW → SUBMITTED."""
        return self._transition(
            order_id,
            OrderStatus.SUBMITTED,
            OrderEventType.SUBMITTED,
            timestamp=timestamp,
            extra={"broker_order_id": broker_order_id} if broker_order_id else {},
            update_fields={"submitted_at": timestamp or datetime.utcnow(),
                           "broker_order_id": broker_order_id},
        )

    def apply_fill(self, order_id: str, fill: Fill) -> Order:
        """Apply a fill to an order, transitioning to PARTIALLY_FILLED or FILLED."""
        with self._lock:
            order = self._get_order(order_id)
            self._assert_transition(order, OrderStatus.PARTIALLY_FILLED)

            new_filled = order.filled_quantity + fill.quantity
            if new_filled > order.quantity:
                raise ValueError(
                    f"Fill quantity {fill.quantity} would exceed order quantity "
                    f"{order.quantity} (already filled {order.filled_quantity})"
                )

            new_status = (
                OrderStatus.FILLED
                if new_filled == order.quantity
                else OrderStatus.PARTIALLY_FILLED
            )

            # Compute updated average fill price
            prev_total = (order.average_fill_price or Decimal("0")) * Decimal(str(order.filled_quantity))
            fill_total = fill.price * Decimal(str(fill.quantity))
            new_avg = (prev_total + fill_total) / Decimal(str(new_filled))

            update_fields: dict = {
                "filled_quantity": new_filled,
                "average_fill_price": new_avg,
                "status": new_status,
            }
            if new_status == OrderStatus.FILLED:
                update_fields["filled_at"] = fill.timestamp

            updated = dataclasses.replace(order, **update_fields)
            self._orders[order_id] = updated

            evt_type = (
                OrderEventType.FILL
                if new_status == OrderStatus.FILLED
                else OrderEventType.PARTIAL_FILL
            )
            self._emit(OrderEvent(
                event_id=str(uuid.uuid4()),
                order_id=order_id,
                event_type=evt_type,
                timestamp=fill.timestamp,
                data={
                    "fill_id": fill.fill_id,
                    "quantity": fill.quantity,
                    "price": str(fill.price),
                    "commission": str(fill.commission),
                },
            ))

            return updated

    def cancel_order(self, order_id: str, timestamp: Optional[datetime] = None) -> Order:
        """Transition order to CANCELLED."""
        ts = timestamp or datetime.utcnow()
        return self._transition(
            order_id,
            OrderStatus.CANCELLED,
            OrderEventType.CANCELLED,
            timestamp=ts,
            update_fields={"cancelled_at": ts},
        )

    def reject_order(self, order_id: str, reason: str = "",
                     timestamp: Optional[datetime] = None) -> Order:
        """Transition order to REJECTED."""
        ts = timestamp or datetime.utcnow()
        return self._transition(
            order_id,
            OrderStatus.REJECTED,
            OrderEventType.REJECTED,
            timestamp=ts,
            extra={"reason": reason},
            update_fields={"rejected_at": ts, "reject_reason": reason},
        )

    def get_order(self, order_id: str) -> Order:
        with self._lock:
            return self._get_order(order_id)

    def get_events(self, order_id: str) -> list[OrderEvent]:
        with self._lock:
            if order_id not in self._events:
                raise OrderNotFoundError(order_id)
            return list(self._events[order_id])

    def list_orders(
        self,
        symbol: Optional[str] = None,
        status: Optional[OrderStatus] = None,
        strategy_name: Optional[str] = None,
    ) -> list[Order]:
        with self._lock:
            orders = list(self._orders.values())
        if symbol is not None:
            orders = [o for o in orders if o.symbol == symbol]
        if status is not None:
            orders = [o for o in orders if o.status == status]
        if strategy_name is not None:
            orders = [o for o in orders if o.strategy_name == strategy_name]
        return orders

    def open_orders(self, symbol: Optional[str] = None) -> list[Order]:
        open_statuses = {OrderStatus.NEW, OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED}
        with self._lock:
            orders = [o for o in self._orders.values() if o.status in open_statuses]
        if symbol is not None:
            orders = [o for o in orders if o.symbol == symbol]
        return orders

    def order_count(self) -> int:
        with self._lock:
            return len(self._orders)

    # ──────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────

    def _get_order(self, order_id: str) -> Order:
        """Must be called under lock."""
        if order_id not in self._orders:
            raise OrderNotFoundError(order_id)
        return self._orders[order_id]

    def _assert_transition(self, order: Order, to_status: OrderStatus) -> None:
        """Raise if the transition is not in VALID_TRANSITIONS."""
        allowed = VALID_TRANSITIONS.get(order.status, set())
        if to_status not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition order {order.order_id} from "
                f"{order.status.value} to {to_status.value}"
            )

    def _transition(
        self,
        order_id: str,
        to_status: OrderStatus,
        event_type: OrderEventType,
        timestamp: Optional[datetime] = None,
        extra: Optional[dict] = None,
        update_fields: Optional[dict] = None,
    ) -> Order:
        ts = timestamp or datetime.utcnow()
        with self._lock:
            order = self._get_order(order_id)
            self._assert_transition(order, to_status)

            fields = {"status": to_status}
            if update_fields:
                fields.update(update_fields)
            updated = dataclasses.replace(order, **fields)
            self._orders[order_id] = updated

            self._emit(OrderEvent(
                event_id=str(uuid.uuid4()),
                order_id=order_id,
                event_type=event_type,
                timestamp=ts,
                data=extra or {},
            ))

            return updated

    def _emit(self, event: OrderEvent) -> None:
        """Append event and call callback. Must be called under lock."""
        self._events[event.order_id].append(event)
        if self._on_event:
            try:
                self._on_event(event)
            except Exception:
                pass

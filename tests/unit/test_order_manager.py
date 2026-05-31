"""Unit tests for OrderManager — state transitions, event log, thread safety."""
from __future__ import annotations

import threading
import uuid
from datetime import datetime
from decimal import Decimal

import pytest

from execution.execution_models import (
    Fill,
    OrderEventType,
    OrderSide,
    OrderStatus,
    OrderType,
)
from execution.order_manager import InvalidTransitionError, OrderManager, OrderNotFoundError


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _oms() -> OrderManager:
    return OrderManager()


def _make_order(oms: OrderManager, qty: int = 100, symbol: str = "NIFTY 50") -> str:
    order = oms.create_order(
        symbol=symbol,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=qty,
        strategy_name="ema",
        timeframe="5min",
        reference_id=str(uuid.uuid4()),
    )
    return order.order_id


def _fill(order_id: str, qty: int = 100, price: str = "19000") -> Fill:
    return Fill(
        fill_id=str(uuid.uuid4()),
        order_id=order_id,
        quantity=qty,
        price=Decimal(price),
        timestamp=datetime(2024, 1, 1),
    )


# ──────────────────────────────────────────────────────────────────────
# create_order
# ──────────────────────────────────────────────────────────────────────

class TestCreateOrder:
    def test_returns_order_in_new_status(self):
        oms = _oms()
        oid = _make_order(oms)
        assert oms.get_order(oid).status == OrderStatus.NEW

    def test_order_stored_in_oms(self):
        oms = _oms()
        oid = _make_order(oms)
        assert oms.get_order(oid).order_id == oid

    def test_symbol_set(self):
        oms = _oms()
        oid = _make_order(oms, symbol="NIFTY BANK")
        assert oms.get_order(oid).symbol == "NIFTY BANK"

    def test_quantity_set(self):
        oms = _oms()
        oid = _make_order(oms, qty=50)
        assert oms.get_order(oid).quantity == 50

    def test_zero_quantity_raises(self):
        oms = _oms()
        with pytest.raises(ValueError):
            oms.create_order("X", OrderSide.BUY, OrderType.MARKET, 0,
                             "ema", "5min", "ref1")

    def test_negative_quantity_raises(self):
        oms = _oms()
        with pytest.raises(ValueError):
            oms.create_order("X", OrderSide.BUY, OrderType.MARKET, -5,
                             "ema", "5min", "ref1")

    def test_created_event_emitted(self):
        oms = _oms()
        oid = _make_order(oms)
        events = oms.get_events(oid)
        assert events[0].event_type == OrderEventType.CREATED

    def test_custom_order_id_used(self):
        oms = _oms()
        custom_id = "my-custom-id"
        order = oms.create_order("X", OrderSide.BUY, OrderType.MARKET, 10,
                                 "ema", "5min", "ref", order_id=custom_id)
        assert order.order_id == custom_id


# ──────────────────────────────────────────────────────────────────────
# submit_order
# ──────────────────────────────────────────────────────────────────────

class TestSubmitOrder:
    def test_transitions_to_submitted(self):
        oms = _oms()
        oid = _make_order(oms)
        order = oms.submit_order(oid)
        assert order.status == OrderStatus.SUBMITTED

    def test_submitted_event_emitted(self):
        oms = _oms()
        oid = _make_order(oms)
        oms.submit_order(oid)
        types = [e.event_type for e in oms.get_events(oid)]
        assert OrderEventType.SUBMITTED in types

    def test_unknown_order_raises(self):
        oms = _oms()
        with pytest.raises(OrderNotFoundError):
            oms.submit_order("nonexistent")

    def test_cannot_submit_already_submitted(self):
        oms = _oms()
        oid = _make_order(oms)
        oms.submit_order(oid)
        with pytest.raises(InvalidTransitionError):
            oms.submit_order(oid)


# ──────────────────────────────────────────────────────────────────────
# apply_fill
# ──────────────────────────────────────────────────────────────────────

class TestApplyFill:
    def test_full_fill_transitions_to_filled(self):
        oms = _oms()
        oid = _make_order(oms, qty=100)
        oms.submit_order(oid)
        oms.apply_fill(oid, _fill(oid, qty=100))
        assert oms.get_order(oid).status == OrderStatus.FILLED

    def test_partial_fill_transitions_to_partially_filled(self):
        oms = _oms()
        oid = _make_order(oms, qty=100)
        oms.submit_order(oid)
        oms.apply_fill(oid, _fill(oid, qty=50))
        assert oms.get_order(oid).status == OrderStatus.PARTIALLY_FILLED

    def test_partial_then_full_fill(self):
        oms = _oms()
        oid = _make_order(oms, qty=100)
        oms.submit_order(oid)
        oms.apply_fill(oid, _fill(oid, qty=60))
        oms.apply_fill(oid, _fill(oid, qty=40))
        assert oms.get_order(oid).status == OrderStatus.FILLED

    def test_filled_quantity_tracked(self):
        oms = _oms()
        oid = _make_order(oms, qty=100)
        oms.submit_order(oid)
        oms.apply_fill(oid, _fill(oid, qty=40))
        assert oms.get_order(oid).filled_quantity == 40

    def test_average_price_computed(self):
        oms = _oms()
        oid = _make_order(oms, qty=100)
        oms.submit_order(oid)
        oms.apply_fill(oid, _fill(oid, qty=50, price="200"))
        oms.apply_fill(oid, _fill(oid, qty=50, price="400"))
        avg = oms.get_order(oid).average_fill_price
        assert avg == pytest.approx(Decimal("300"), rel=Decimal("0.001"))

    def test_overfill_raises(self):
        oms = _oms()
        oid = _make_order(oms, qty=50)
        oms.submit_order(oid)
        with pytest.raises(ValueError):
            oms.apply_fill(oid, _fill(oid, qty=100))

    def test_fill_event_recorded(self):
        oms = _oms()
        oid = _make_order(oms, qty=10)
        oms.submit_order(oid)
        oms.apply_fill(oid, _fill(oid, qty=10))
        types = [e.event_type for e in oms.get_events(oid)]
        assert OrderEventType.FILL in types

    def test_partial_fill_event_recorded(self):
        oms = _oms()
        oid = _make_order(oms, qty=100)
        oms.submit_order(oid)
        oms.apply_fill(oid, _fill(oid, qty=30))
        types = [e.event_type for e in oms.get_events(oid)]
        assert OrderEventType.PARTIAL_FILL in types


# ──────────────────────────────────────────────────────────────────────
# cancel_order / reject_order
# ──────────────────────────────────────────────────────────────────────

class TestCancelReject:
    def test_cancel_new_order(self):
        oms = _oms()
        oid = _make_order(oms)
        order = oms.cancel_order(oid)
        assert order.status == OrderStatus.CANCELLED

    def test_cancel_submitted_order(self):
        oms = _oms()
        oid = _make_order(oms)
        oms.submit_order(oid)
        order = oms.cancel_order(oid)
        assert order.status == OrderStatus.CANCELLED

    def test_cancel_partially_filled_order(self):
        oms = _oms()
        oid = _make_order(oms, qty=100)
        oms.submit_order(oid)
        oms.apply_fill(oid, _fill(oid, qty=40))
        order = oms.cancel_order(oid)
        assert order.status == OrderStatus.CANCELLED

    def test_cannot_cancel_filled_order(self):
        oms = _oms()
        oid = _make_order(oms, qty=10)
        oms.submit_order(oid)
        oms.apply_fill(oid, _fill(oid, qty=10))
        with pytest.raises(InvalidTransitionError):
            oms.cancel_order(oid)

    def test_reject_new_order(self):
        oms = _oms()
        oid = _make_order(oms)
        order = oms.reject_order(oid, reason="risk limit")
        assert order.status == OrderStatus.REJECTED
        assert order.reject_reason == "risk limit"

    def test_reject_submitted_order(self):
        oms = _oms()
        oid = _make_order(oms)
        oms.submit_order(oid)
        order = oms.reject_order(oid, reason="broker refused")
        assert order.status == OrderStatus.REJECTED

    def test_cannot_reject_filled_order(self):
        oms = _oms()
        oid = _make_order(oms, qty=10)
        oms.submit_order(oid)
        oms.apply_fill(oid, _fill(oid, qty=10))
        with pytest.raises(InvalidTransitionError):
            oms.reject_order(oid)


# ──────────────────────────────────────────────────────────────────────
# list_orders / open_orders / order_count
# ──────────────────────────────────────────────────────────────────────

class TestQuery:
    def test_list_orders_by_symbol(self):
        oms = _oms()
        _make_order(oms, symbol="NIFTY 50")
        _make_order(oms, symbol="NIFTY BANK")
        assert len(oms.list_orders(symbol="NIFTY 50")) == 1

    def test_list_orders_by_status(self):
        oms = _oms()
        oid = _make_order(oms)
        oms.submit_order(oid)
        assert len(oms.list_orders(status=OrderStatus.SUBMITTED)) == 1
        assert len(oms.list_orders(status=OrderStatus.NEW)) == 0

    def test_open_orders_excludes_terminal(self):
        oms = _oms()
        oid1 = _make_order(oms, qty=10)
        oid2 = _make_order(oms)
        oms.submit_order(oid1)
        oms.apply_fill(oid1, _fill(oid1, qty=10))
        oms.cancel_order(oid2)
        assert len(oms.open_orders()) == 0

    def test_order_count(self):
        oms = _oms()
        _make_order(oms)
        _make_order(oms)
        assert oms.order_count() == 2


# ──────────────────────────────────────────────────────────────────────
# event callback
# ──────────────────────────────────────────────────────────────────────

class TestEventCallback:
    def test_callback_called_on_create(self):
        received = []
        oms = OrderManager(on_event=received.append)
        _make_order(oms)
        assert len(received) == 1
        assert received[0].event_type == OrderEventType.CREATED

    def test_callback_called_on_fill(self):
        received = []
        oms = OrderManager(on_event=received.append)
        oid = _make_order(oms, qty=10)
        oms.submit_order(oid)
        oms.apply_fill(oid, _fill(oid, qty=10))
        types = [e.event_type for e in received]
        assert OrderEventType.FILL in types


# ──────────────────────────────────────────────────────────────────────
# Thread safety
# ──────────────────────────────────────────────────────────────────────

class TestThreadSafety:
    def test_concurrent_order_creation(self):
        oms = _oms()
        errors = []

        def create_many():
            try:
                for _ in range(50):
                    _make_order(oms)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=create_many) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert oms.order_count() == 200

    def test_concurrent_fill_on_different_orders(self):
        oms = _oms()
        oids = []
        for _ in range(20):
            oid = _make_order(oms, qty=1)
            oms.submit_order(oid)
            oids.append(oid)

        errors = []

        def fill_order(oid):
            try:
                oms.apply_fill(oid, _fill(oid, qty=1))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=fill_order, args=(oid,)) for oid in oids]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        filled = [o for o in oms.list_orders() if o.status == OrderStatus.FILLED]
        assert len(filled) == 20

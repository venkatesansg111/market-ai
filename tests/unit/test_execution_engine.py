"""Unit tests for ExecutionEngine — signal→order→fill→position."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import pytest

from execution.execution_engine import ExecutionEngine, meta_signal_to_request
from execution.execution_models import (
    ExecutionRequest,
    OrderSide,
    OrderStatus,
    OrderType,
)
from execution.mock_broker import MockBrokerAdapter
from execution.order_manager import OrderManager
from execution.position_manager import PositionManager
from execution.slippage_model import ZeroSlippageModel
from meta.meta_models import MarketRegime, MetaSignal, RegimeType, RoutingMode


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _req(
    symbol: str = "NIFTY 50",
    side: OrderSide = OrderSide.BUY,
    qty: int = 10,
    price: str = "19000",
    order_type: OrderType = OrderType.MARKET,
) -> ExecutionRequest:
    return ExecutionRequest(
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=qty,
        current_price=Decimal(price),
        strategy_name="ema",
        timeframe="5min",
        confidence=0.8,
        reference_id=str(uuid.uuid4()),
    )


def _engine(
    fill_price: str = "19000",
    reject: bool = False,
) -> ExecutionEngine:
    broker = MockBrokerAdapter(fill_price=Decimal(fill_price))
    broker.reject_next = reject
    return ExecutionEngine(
        broker=broker,
        order_manager=OrderManager(),
        position_manager=PositionManager(),
        slippage_model=ZeroSlippageModel(),
    )


def _signal(instrument: str = "NIFTY 50") -> MetaSignal:
    return MetaSignal(
        instrument=instrument,
        timeframe="5min",
        selected_strategy="ema",
        regime_type=RegimeType.TRENDING_UP,
        confidence=0.80,
        strategy_weights={"ema": 1.0},
        routing_mode=RoutingMode.SINGLE_BEST,
        reasoning="test",
        timestamp=datetime(2024, 1, 1),
    )


# ──────────────────────────────────────────────────────────────────────
# execute()
# ──────────────────────────────────────────────────────────────────────

class TestExecute:
    def test_returns_execution_result(self):
        engine = _engine()
        result = engine.execute(_req())
        assert result is not None

    def test_filled_status_on_success(self):
        engine = _engine()
        result = engine.execute(_req())
        assert result.status == OrderStatus.FILLED

    def test_order_created_in_oms(self):
        engine = _engine()
        result = engine.execute(_req())
        order = engine.order_manager.get_order(result.order_id)
        assert order is not None

    def test_order_ends_as_filled_in_oms(self):
        engine = _engine()
        result = engine.execute(_req())
        order = engine.order_manager.get_order(result.order_id)
        assert order.status == OrderStatus.FILLED

    def test_fill_in_result(self):
        engine = _engine()
        result = engine.execute(_req(qty=5))
        assert len(result.fills) == 1
        assert result.fills[0].quantity == 5

    def test_fill_price_from_broker(self):
        engine = _engine(fill_price="20000")
        result = engine.execute(_req())
        assert result.average_fill_price == Decimal("20000")

    def test_rejected_order_returns_rejected_status(self):
        engine = _engine(reject=True)
        result = engine.execute(_req())
        assert result.status == OrderStatus.REJECTED

    def test_rejected_order_no_fills(self):
        engine = _engine(reject=True)
        result = engine.execute(_req())
        assert result.fills == []

    def test_position_updated_after_fill(self):
        engine = _engine(fill_price="19000")
        engine.execute(_req(qty=10))
        pos = engine.position_manager.get_position("NIFTY 50")
        assert pos is not None
        assert pos.quantity == 10

    def test_sell_reduces_position(self):
        engine = _engine(fill_price="19000")
        engine.execute(_req(side=OrderSide.BUY, qty=10))
        engine.execute(_req(side=OrderSide.SELL, qty=5))
        pos = engine.position_manager.get_position("NIFTY 50")
        assert pos.quantity == 5

    def test_total_filled_quantity_matches(self):
        engine = _engine()
        result = engine.execute(_req(qty=20))
        assert result.total_filled_quantity == 20

    def test_symbol_in_result(self):
        engine = _engine()
        result = engine.execute(_req(symbol="NIFTY BANK"))
        assert result.symbol == "NIFTY BANK"

    def test_multiple_executions_tracked(self):
        engine = _engine()
        engine.execute(_req())
        engine.execute(_req())
        assert engine.order_manager.order_count() == 2


# ──────────────────────────────────────────────────────────────────────
# execute_from_signal()
# ──────────────────────────────────────────────────────────────────────

class TestExecuteFromSignal:
    def test_returns_execution_result(self):
        engine = _engine()
        result = engine.execute_from_signal(
            _signal(), quantity=5, current_price=Decimal("19000")
        )
        assert result is not None

    def test_uses_signal_instrument(self):
        engine = _engine()
        result = engine.execute_from_signal(
            _signal("NIFTY BANK"), quantity=5, current_price=Decimal("44000")
        )
        assert result.symbol == "NIFTY BANK"

    def test_strategy_name_set_from_signal(self):
        engine = _engine()
        engine.execute_from_signal(_signal(), quantity=5, current_price=Decimal("19000"))
        orders = engine.order_manager.list_orders()
        assert orders[0].strategy_name == "ema"

    def test_filled_after_signal_execution(self):
        engine = _engine()
        result = engine.execute_from_signal(_signal(), quantity=1, current_price=Decimal("100"))
        assert result.status == OrderStatus.FILLED


# ──────────────────────────────────────────────────────────────────────
# meta_signal_to_request()
# ──────────────────────────────────────────────────────────────────────

class TestMetaSignalToRequest:
    def test_symbol_from_signal_instrument(self):
        sig = _signal("NIFTY 50")
        req = meta_signal_to_request(sig, 10, Decimal("19000"))
        assert req.symbol == "NIFTY 50"

    def test_strategy_name_from_signal(self):
        sig = _signal()
        req = meta_signal_to_request(sig, 10, Decimal("19000"))
        assert req.strategy_name == "ema"

    def test_reference_id_is_run_id(self):
        sig = _signal()
        req = meta_signal_to_request(sig, 10, Decimal("19000"))
        assert req.reference_id == sig.run_id

    def test_timeframe_from_signal(self):
        sig = _signal()
        req = meta_signal_to_request(sig, 10, Decimal("19000"))
        assert req.timeframe == "5min"

    def test_confidence_from_signal(self):
        sig = _signal()
        req = meta_signal_to_request(sig, 10, Decimal("19000"))
        assert req.confidence == pytest.approx(0.80)

    def test_default_side_is_buy(self):
        req = meta_signal_to_request(_signal(), 10, Decimal("100"))
        assert req.side == OrderSide.BUY

    def test_default_order_type_is_market(self):
        req = meta_signal_to_request(_signal(), 10, Decimal("100"))
        assert req.order_type == OrderType.MARKET

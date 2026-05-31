"""Unit tests for MockBrokerAdapter and SlippageModel."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import pytest

from execution.execution_models import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
)
from execution.mock_broker import MockBrokerAdapter
from execution.slippage_model import (
    FixedBpsSlippageModel,
    PercentageSlippageModel,
    ZeroSlippageModel,
)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _order(
    symbol: str = "NIFTY 50",
    side: OrderSide = OrderSide.BUY,
    qty: int = 10,
    limit_price: str | None = None,
) -> Order:
    return Order(
        order_id=str(uuid.uuid4()),
        symbol=symbol,
        side=side,
        order_type=OrderType.MARKET,
        quantity=qty,
        status=OrderStatus.SUBMITTED,
        created_at=datetime(2024, 1, 1),
        strategy_name="ema",
        timeframe="5min",
        reference_id=str(uuid.uuid4()),
        limit_price=Decimal(limit_price) if limit_price else None,
    )


# ──────────────────────────────────────────────────────────────────────
# MockBrokerAdapter
# ──────────────────────────────────────────────────────────────────────

class TestMockBrokerAdapter:
    def test_submit_returns_success(self):
        broker = MockBrokerAdapter(fill_price=Decimal("100"))
        resp = broker.submit_order(_order())
        assert resp.success

    def test_submit_fills_full_quantity(self):
        broker = MockBrokerAdapter(fill_price=Decimal("200"))
        resp = broker.submit_order(_order(qty=7))
        assert resp.fills[0].quantity == 7

    def test_fill_price_exact(self):
        broker = MockBrokerAdapter(fill_price=Decimal("19000"))
        resp = broker.submit_order(_order())
        assert resp.fills[0].price == Decimal("19000")

    def test_status_filled(self):
        broker = MockBrokerAdapter(fill_price=Decimal("100"))
        resp = broker.submit_order(_order())
        assert resp.status == OrderStatus.FILLED

    def test_reject_next_triggers_rejection(self):
        broker = MockBrokerAdapter(fill_price=Decimal("100"))
        broker.reject_next = True
        resp = broker.submit_order(_order())
        assert not resp.success
        assert resp.status == OrderStatus.REJECTED
        assert resp.fills == []

    def test_reject_next_resets_after_one_rejection(self):
        broker = MockBrokerAdapter(fill_price=Decimal("100"))
        broker.reject_next = True
        broker.submit_order(_order())  # consume the rejection
        resp = broker.submit_order(_order())
        assert resp.success

    def test_submitted_orders_tracked(self):
        broker = MockBrokerAdapter(fill_price=Decimal("100"))
        broker.submit_order(_order())
        broker.submit_order(_order())
        assert len(broker.submitted_orders) == 2

    def test_cancel_returns_true(self):
        broker = MockBrokerAdapter()
        assert broker.cancel_order("any-id") is True

    def test_cancelled_ids_tracked(self):
        broker = MockBrokerAdapter()
        broker.cancel_order("id-1")
        broker.cancel_order("id-2")
        assert "id-1" in broker.cancelled_ids
        assert "id-2" in broker.cancelled_ids

    def test_get_positions_returns_empty(self):
        broker = MockBrokerAdapter()
        assert broker.get_positions() == []

    def test_get_account_info_returns_initial_cash(self):
        broker = MockBrokerAdapter(initial_cash=Decimal("500000"))
        acct = broker.get_account_info()
        assert acct.cash_balance == Decimal("500000")

    def test_is_connected_true(self):
        broker = MockBrokerAdapter()
        assert broker.is_connected()

    def test_reset_clears_submitted(self):
        broker = MockBrokerAdapter(fill_price=Decimal("100"))
        broker.submit_order(_order())
        broker.reset()
        assert broker.submitted_orders == []

    def test_slippage_model_applied_to_limit_price(self):
        broker = MockBrokerAdapter(slippage_model=FixedBpsSlippageModel(slip_bps=10, half_spread_bps=0))
        order = _order(limit_price="1000")
        resp = broker.submit_order(order)
        # buy: price * (1 + 10/10000) = 1001.00
        assert resp.fills[0].price == Decimal("1001.00")


# ──────────────────────────────────────────────────────────────────────
# ZeroSlippageModel
# ──────────────────────────────────────────────────────────────────────

class TestZeroSlippage:
    def test_buy_unchanged(self):
        m = ZeroSlippageModel()
        assert m.apply_buy(Decimal("100")) == Decimal("100")

    def test_sell_unchanged(self):
        m = ZeroSlippageModel()
        assert m.apply_sell(Decimal("100")) == Decimal("100")

    def test_apply_buy_via_helper(self):
        m = ZeroSlippageModel()
        assert m.apply(Decimal("200"), is_buy=True) == Decimal("200")

    def test_apply_sell_via_helper(self):
        m = ZeroSlippageModel()
        assert m.apply(Decimal("200"), is_buy=False) == Decimal("200")


# ──────────────────────────────────────────────────────────────────────
# FixedBpsSlippageModel
# ──────────────────────────────────────────────────────────────────────

class TestFixedBpsSlippage:
    def test_buy_price_higher_than_input(self):
        m = FixedBpsSlippageModel(slip_bps=5.0, half_spread_bps=2.0)
        result = m.apply_buy(Decimal("10000"))
        assert result > Decimal("10000")

    def test_sell_price_lower_than_input(self):
        m = FixedBpsSlippageModel(slip_bps=5.0, half_spread_bps=2.0)
        result = m.apply_sell(Decimal("10000"))
        assert result < Decimal("10000")

    def test_buy_5bps_2bps_spread(self):
        m = FixedBpsSlippageModel(slip_bps=5.0, half_spread_bps=2.0)
        # factor = 1 + 7/10000 = 1.0007
        expected = (Decimal("10000") * Decimal("1.0007")).quantize(Decimal("0.01"))
        assert m.apply_buy(Decimal("10000")) == expected

    def test_sell_5bps_2bps_spread(self):
        m = FixedBpsSlippageModel(slip_bps=5.0, half_spread_bps=2.0)
        expected = (Decimal("10000") * Decimal("0.9993")).quantize(Decimal("0.01"))
        assert m.apply_sell(Decimal("10000")) == expected

    def test_result_quantized_to_cents(self):
        m = FixedBpsSlippageModel()
        result = m.apply_buy(Decimal("19000.5"))
        assert result == result.quantize(Decimal("0.01"))

    def test_zero_slip_zero_spread_equals_price(self):
        m = FixedBpsSlippageModel(slip_bps=0.0, half_spread_bps=0.0)
        assert m.apply_buy(Decimal("100")) == Decimal("100.00")
        assert m.apply_sell(Decimal("100")) == Decimal("100.00")


# ──────────────────────────────────────────────────────────────────────
# PercentageSlippageModel
# ──────────────────────────────────────────────────────────────────────

class TestPercentageSlippage:
    def test_buy_increases_price(self):
        m = PercentageSlippageModel(pct=0.1)
        assert m.apply_buy(Decimal("1000")) > Decimal("1000")

    def test_sell_decreases_price(self):
        m = PercentageSlippageModel(pct=0.1)
        assert m.apply_sell(Decimal("1000")) < Decimal("1000")

    def test_buy_exact_value(self):
        m = PercentageSlippageModel(pct=1.0)
        # 1000 * 1.01 = 1010.00
        assert m.apply_buy(Decimal("1000")) == Decimal("1010.00")

    def test_sell_exact_value(self):
        m = PercentageSlippageModel(pct=1.0)
        assert m.apply_sell(Decimal("1000")) == Decimal("990.00")

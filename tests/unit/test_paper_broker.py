"""Unit tests for PaperBrokerAdapter — fills, order types, determinism."""
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
from execution.paper_broker import PaperBrokerAdapter
from execution.slippage_model import ZeroSlippageModel


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _order(
    symbol: str = "NIFTY 50",
    side: OrderSide = OrderSide.BUY,
    order_type: OrderType = OrderType.MARKET,
    qty: int = 10,
    limit_price: str | None = None,
    stop_price: str | None = None,
) -> Order:
    return Order(
        order_id=str(uuid.uuid4()),
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=qty,
        status=OrderStatus.SUBMITTED,
        created_at=datetime(2024, 1, 1),
        strategy_name="ema",
        timeframe="5min",
        reference_id=str(uuid.uuid4()),
        limit_price=Decimal(limit_price) if limit_price else None,
        stop_price=Decimal(stop_price) if stop_price else None,
    )


def _broker(
    price: str = "19000",
    fill_prob: float = 1.0,
    partial_prob: float = 0.0,
) -> PaperBrokerAdapter:
    return PaperBrokerAdapter(
        current_price_map={"NIFTY 50": Decimal(price)},
        slippage_model=ZeroSlippageModel(),
        fill_probability=fill_prob,
        partial_fill_probability=partial_prob,
    )


# ──────────────────────────────────────────────────────────────────────
# MARKET orders
# ──────────────────────────────────────────────────────────────────────

class TestMarketOrders:
    def test_market_buy_fills(self):
        broker = _broker()
        resp = broker.submit_order(_order(order_type=OrderType.MARKET))
        assert resp.success
        assert len(resp.fills) == 1

    def test_market_buy_filled_status(self):
        broker = _broker()
        resp = broker.submit_order(_order(order_type=OrderType.MARKET))
        assert resp.status == OrderStatus.FILLED

    def test_market_buy_full_quantity(self):
        broker = _broker()
        resp = broker.submit_order(_order(qty=25))
        assert resp.fills[0].quantity == 25

    def test_market_sell_fills(self):
        broker = _broker()
        resp = broker.submit_order(_order(side=OrderSide.SELL, order_type=OrderType.MARKET))
        assert len(resp.fills) == 1

    def test_no_price_returns_no_fill(self):
        broker = PaperBrokerAdapter(
            current_price_map={},
            slippage_model=ZeroSlippageModel(),
        )
        resp = broker.submit_order(_order())
        assert resp.fills == []


# ──────────────────────────────────────────────────────────────────────
# LIMIT orders
# ──────────────────────────────────────────────────────────────────────

class TestLimitOrders:
    def test_limit_buy_fills_when_limit_above_price(self):
        broker = _broker(price="19000")
        order = _order(side=OrderSide.BUY, order_type=OrderType.LIMIT, limit_price="19500")
        resp = broker.submit_order(order)
        assert len(resp.fills) == 1

    def test_limit_buy_no_fill_when_limit_below_price(self):
        broker = _broker(price="19000")
        order = _order(side=OrderSide.BUY, order_type=OrderType.LIMIT, limit_price="18500")
        resp = broker.submit_order(order)
        assert resp.fills == []

    def test_limit_sell_fills_when_limit_below_price(self):
        broker = _broker(price="19000")
        order = _order(side=OrderSide.SELL, order_type=OrderType.LIMIT, limit_price="18500")
        resp = broker.submit_order(order)
        assert len(resp.fills) == 1

    def test_limit_sell_no_fill_when_limit_above_price(self):
        broker = _broker(price="19000")
        order = _order(side=OrderSide.SELL, order_type=OrderType.LIMIT, limit_price="19500")
        resp = broker.submit_order(order)
        assert resp.fills == []


# ──────────────────────────────────────────────────────────────────────
# STOP orders
# ──────────────────────────────────────────────────────────────────────

class TestStopOrders:
    def test_stop_buy_fills_when_stop_at_or_below_price(self):
        broker = _broker(price="19000")
        order = _order(side=OrderSide.BUY, order_type=OrderType.STOP, stop_price="18900")
        resp = broker.submit_order(order)
        assert len(resp.fills) == 1

    def test_stop_buy_no_fill_when_stop_above_price(self):
        broker = _broker(price="19000")
        order = _order(side=OrderSide.BUY, order_type=OrderType.STOP, stop_price="19500")
        resp = broker.submit_order(order)
        assert resp.fills == []

    def test_stop_sell_fills_when_stop_at_or_above_price(self):
        broker = _broker(price="19000")
        order = _order(side=OrderSide.SELL, order_type=OrderType.STOP, stop_price="19100")
        resp = broker.submit_order(order)
        assert len(resp.fills) == 1

    def test_stop_sell_no_fill_when_stop_below_price(self):
        broker = _broker(price="19000")
        order = _order(side=OrderSide.SELL, order_type=OrderType.STOP, stop_price="18500")
        resp = broker.submit_order(order)
        assert resp.fills == []


# ──────────────────────────────────────────────────────────────────────
# Deterministic fill probability
# ──────────────────────────────────────────────────────────────────────

class TestFillProbability:
    def test_fill_prob_1_always_fills(self):
        broker = _broker(fill_prob=1.0)
        for _ in range(10):
            resp = broker.submit_order(_order())
            assert len(resp.fills) == 1

    def test_fill_prob_0_never_fills(self):
        broker = _broker(fill_prob=0.0)
        for _ in range(10):
            resp = broker.submit_order(_order())
            assert resp.fills == []

    def test_partial_prob_1_always_partial(self):
        broker = _broker(partial_prob=1.0)
        resp = broker.submit_order(_order(qty=10))
        assert resp.fills[0].quantity == 5  # qty // 2

    def test_partial_prob_1_qty_1_gives_at_least_1(self):
        broker = _broker(partial_prob=1.0)
        resp = broker.submit_order(_order(qty=1))
        assert resp.fills[0].quantity >= 1

    def test_partial_prob_0_always_full_fill(self):
        broker = _broker(partial_prob=0.0)
        resp = broker.submit_order(_order(qty=10))
        assert resp.fills[0].quantity == 10

    def test_partial_fills_show_partially_filled_status(self):
        broker = _broker(partial_prob=1.0)
        resp = broker.submit_order(_order(qty=10))
        assert resp.status == OrderStatus.PARTIALLY_FILLED


# ──────────────────────────────────────────────────────────────────────
# Account / positions
# ──────────────────────────────────────────────────────────────────────

class TestAccountAndPositions:
    def test_cash_reduced_after_buy(self):
        broker = _broker(price="100")
        initial_cash = broker.get_account_info().cash_balance
        broker.submit_order(_order(qty=10))
        acct = broker.get_account_info()
        assert acct.cash_balance < initial_cash

    def test_position_created_after_buy(self):
        broker = _broker()
        broker.submit_order(_order(qty=5))
        positions = broker.get_positions()
        assert len(positions) == 1
        assert positions[0].quantity == 5

    def test_is_connected_true(self):
        broker = _broker()
        assert broker.is_connected()

    def test_cancel_returns_true(self):
        broker = _broker()
        assert broker.cancel_order("any-id") is True

    def test_price_update_affects_next_fill(self):
        broker = _broker(price="19000")
        broker.update_price("NIFTY 50", Decimal("20000"))
        resp = broker.submit_order(_order(qty=1))
        assert resp.fills[0].price == Decimal("20000")

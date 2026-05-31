"""Unit tests for PositionManager — fill arithmetic, P&L, reconciliation."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import pytest

from execution.execution_models import (
    BrokerPosition,
    Fill,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)
from execution.position_manager import PositionManager


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

_TS = datetime(2024, 1, 1)


def _order(side: OrderSide = OrderSide.BUY, symbol: str = "NIFTY 50") -> Order:
    return Order(
        order_id=str(uuid.uuid4()),
        symbol=symbol,
        side=side,
        order_type=OrderType.MARKET,
        quantity=100,
        status=OrderStatus.FILLED,
        created_at=_TS,
        strategy_name="ema",
        timeframe="5min",
        reference_id=str(uuid.uuid4()),
    )


def _fill(order_id: str, qty: int, price: str) -> Fill:
    return Fill(
        fill_id=str(uuid.uuid4()),
        order_id=order_id,
        quantity=qty,
        price=Decimal(price),
        timestamp=_TS,
    )


def _pm() -> PositionManager:
    return PositionManager()


# ──────────────────────────────────────────────────────────────────────
# Opening a position
# ──────────────────────────────────────────────────────────────────────

class TestOpenPosition:
    def test_new_buy_creates_long_position(self):
        pm = _pm()
        buy = _order(OrderSide.BUY)
        pm.apply_fill(buy, _fill(buy.order_id, 10, "200"))
        pos = pm.get_position("NIFTY 50")
        assert pos.quantity == 10

    def test_new_sell_creates_short_position(self):
        pm = _pm()
        sell = _order(OrderSide.SELL)
        pm.apply_fill(sell, _fill(sell.order_id, 10, "200"))
        pos = pm.get_position("NIFTY 50")
        assert pos.quantity == -10

    def test_average_price_set_correctly(self):
        pm = _pm()
        buy = _order(OrderSide.BUY)
        pm.apply_fill(buy, _fill(buy.order_id, 10, "19000"))
        pos = pm.get_position("NIFTY 50")
        assert pos.average_price == Decimal("19000")

    def test_returns_position_object(self):
        pm = _pm()
        buy = _order(OrderSide.BUY)
        result = pm.apply_fill(buy, _fill(buy.order_id, 5, "100"))
        assert isinstance(result, Position)


# ──────────────────────────────────────────────────────────────────────
# Adding to an existing position
# ──────────────────────────────────────────────────────────────────────

class TestAddToPosition:
    def test_adding_buy_increases_quantity(self):
        pm = _pm()
        buy = _order(OrderSide.BUY)
        pm.apply_fill(buy, _fill(buy.order_id, 10, "100"))
        pm.apply_fill(buy, _fill(buy.order_id, 5, "110"))
        pos = pm.get_position("NIFTY 50")
        assert pos.quantity == 15

    def test_weighted_average_price(self):
        pm = _pm()
        buy = _order(OrderSide.BUY)
        pm.apply_fill(buy, _fill(buy.order_id, 10, "100"))
        pm.apply_fill(buy, _fill(buy.order_id, 10, "200"))
        pos = pm.get_position("NIFTY 50")
        assert pos.average_price == pytest.approx(Decimal("150"))


# ──────────────────────────────────────────────────────────────────────
# Closing / reducing a position
# ──────────────────────────────────────────────────────────────────────

class TestReducePosition:
    def test_sell_reduces_long_position(self):
        pm = _pm()
        buy = _order(OrderSide.BUY)
        sell = _order(OrderSide.SELL)
        pm.apply_fill(buy, _fill(buy.order_id, 10, "100"))
        pm.apply_fill(sell, _fill(sell.order_id, 4, "120"))
        pos = pm.get_position("NIFTY 50")
        assert pos.quantity == 6

    def test_realized_pnl_on_close(self):
        pm = _pm()
        buy = _order(OrderSide.BUY)
        sell = _order(OrderSide.SELL)
        pm.apply_fill(buy, _fill(buy.order_id, 10, "100"))
        pm.apply_fill(sell, _fill(sell.order_id, 10, "120"))
        pos = pm.get_position("NIFTY 50")
        assert pos.realized_pnl == pytest.approx(Decimal("200"))  # 10 * (120-100)

    def test_full_close_leaves_flat_position(self):
        pm = _pm()
        buy = _order(OrderSide.BUY)
        sell = _order(OrderSide.SELL)
        pm.apply_fill(buy, _fill(buy.order_id, 10, "100"))
        pm.apply_fill(sell, _fill(sell.order_id, 10, "100"))
        pos = pm.get_position("NIFTY 50")
        assert pos.is_flat

    def test_position_reversal(self):
        pm = _pm()
        buy = _order(OrderSide.BUY)
        sell = _order(OrderSide.SELL)
        pm.apply_fill(buy, _fill(buy.order_id, 5, "100"))
        pm.apply_fill(sell, _fill(sell.order_id, 10, "120"))
        pos = pm.get_position("NIFTY 50")
        assert pos.quantity == -5


# ──────────────────────────────────────────────────────────────────────
# Multiple symbols
# ──────────────────────────────────────────────────────────────────────

class TestMultipleSymbols:
    def test_separate_positions_per_symbol(self):
        pm = _pm()
        buy_nifty = _order(OrderSide.BUY, symbol="NIFTY 50")
        buy_bank = _order(OrderSide.BUY, symbol="NIFTY BANK")
        pm.apply_fill(buy_nifty, _fill(buy_nifty.order_id, 10, "19000"))
        pm.apply_fill(buy_bank, _fill(buy_bank.order_id, 5, "44000"))
        assert pm.get_position("NIFTY 50").quantity == 10
        assert pm.get_position("NIFTY BANK").quantity == 5

    def test_all_positions_returns_both(self):
        pm = _pm()
        buy1 = _order(OrderSide.BUY, symbol="NIFTY 50")
        buy2 = _order(OrderSide.BUY, symbol="NIFTY BANK")
        pm.apply_fill(buy1, _fill(buy1.order_id, 1, "100"))
        pm.apply_fill(buy2, _fill(buy2.order_id, 1, "200"))
        assert len(pm.all_positions()) == 2

    def test_open_positions_excludes_flat(self):
        pm = _pm()
        buy = _order(OrderSide.BUY, symbol="NIFTY 50")
        sell = _order(OrderSide.SELL, symbol="NIFTY 50")
        pm.apply_fill(buy, _fill(buy.order_id, 10, "100"))
        pm.apply_fill(sell, _fill(sell.order_id, 10, "110"))
        assert pm.open_positions() == []


# ──────────────────────────────────────────────────────────────────────
# total_realized_pnl / reset
# ──────────────────────────────────────────────────────────────────────

class TestTotalsAndReset:
    def test_total_realized_pnl_sums_all(self):
        pm = _pm()
        buy1 = _order(OrderSide.BUY, symbol="NIFTY 50")
        sell1 = _order(OrderSide.SELL, symbol="NIFTY 50")
        buy2 = _order(OrderSide.BUY, symbol="NIFTY BANK")
        sell2 = _order(OrderSide.SELL, symbol="NIFTY BANK")
        pm.apply_fill(buy1, _fill(buy1.order_id, 10, "100"))
        pm.apply_fill(sell1, _fill(sell1.order_id, 10, "110"))  # +100
        pm.apply_fill(buy2, _fill(buy2.order_id, 5, "200"))
        pm.apply_fill(sell2, _fill(sell2.order_id, 5, "220"))   # +100
        assert pm.total_realized_pnl() == pytest.approx(Decimal("200"))

    def test_reset_clears_all_positions(self):
        pm = _pm()
        buy = _order(OrderSide.BUY)
        pm.apply_fill(buy, _fill(buy.order_id, 10, "100"))
        pm.reset()
        assert pm.all_positions() == []


# ──────────────────────────────────────────────────────────────────────
# reconcile()
# ──────────────────────────────────────────────────────────────────────

class TestReconcile:
    def test_matched_when_in_sync(self):
        pm = _pm()
        buy = _order(OrderSide.BUY)
        pm.apply_fill(buy, _fill(buy.order_id, 10, "100"))
        broker_pos = [BrokerPosition("NIFTY 50", 10, Decimal("100"))]
        result = pm.reconcile(broker_pos)
        assert "NIFTY 50" in result.matched
        assert result.is_clean

    def test_mismatch_detected(self):
        pm = _pm()
        buy = _order(OrderSide.BUY)
        pm.apply_fill(buy, _fill(buy.order_id, 10, "100"))
        broker_pos = [BrokerPosition("NIFTY 50", 8, Decimal("100"))]  # qty differs
        result = pm.reconcile(broker_pos)
        assert "NIFTY 50" in result.mismatched
        assert not result.is_clean

    def test_only_local_detected(self):
        pm = _pm()
        buy = _order(OrderSide.BUY)
        pm.apply_fill(buy, _fill(buy.order_id, 5, "100"))
        result = pm.reconcile([])
        assert "NIFTY 50" in result.only_local
        assert not result.is_clean

    def test_only_broker_detected(self):
        pm = _pm()
        broker_pos = [BrokerPosition("NIFTY BANK", 3, Decimal("44000"))]
        result = pm.reconcile(broker_pos)
        assert "NIFTY BANK" in result.only_broker
        assert not result.is_clean

    def test_flat_positions_excluded_from_reconcile(self):
        pm = _pm()
        buy = _order(OrderSide.BUY)
        sell = _order(OrderSide.SELL)
        pm.apply_fill(buy, _fill(buy.order_id, 10, "100"))
        pm.apply_fill(sell, _fill(sell.order_id, 10, "110"))
        result = pm.reconcile([])
        assert result.is_clean

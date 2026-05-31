"""Phase 7 — Paper trading broker with realistic fill simulation."""
from __future__ import annotations

import random
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from execution.broker_adapter import BrokerAdapter
from execution.execution_models import (
    AccountInfo,
    BrokerPosition,
    BrokerResponse,
    Fill,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
)
from execution.slippage_model import FixedBpsSlippageModel, SlippageModel


class PaperBrokerAdapter(BrokerAdapter):
    """Simulated broker for paper trading.

    Determinism contract
    --------------------
    fill_probability=1.0  → always fills (no RNG used)
    fill_probability=0.0  → never fills (returns empty fills)
    partial_fill_probability=0.0 → always fills full quantity (no RNG)
    partial_fill_probability=1.0 → always fills exactly quantity // 2
    0 < x < 1             → RNG used; seed the rng parameter for reproducibility

    Order type logic
    ----------------
    MARKET  → always eligible, fills at slippage-adjusted current_price
    LIMIT   → fills only if price condition met (buy: limit >= current, sell: limit <= current)
    STOP    → fills only if price condition met (buy: stop <= current, sell: stop >= current)
    STOP_LIMIT → stop condition triggers, then limit condition applies
    """

    def __init__(
        self,
        current_price_map: Optional[dict[str, Decimal]] = None,
        slippage_model: Optional[SlippageModel] = None,
        fill_probability: float = 1.0,
        partial_fill_probability: float = 0.0,
        initial_cash: Decimal = Decimal("1000000"),
        rng: Optional[random.Random] = None,
        timestamp: Optional[datetime] = None,
    ) -> None:
        self._prices = current_price_map or {}
        self._slippage = slippage_model or FixedBpsSlippageModel()
        self._fill_prob = fill_probability
        self._partial_prob = partial_fill_probability
        self._cash = initial_cash
        self._rng = rng or random.Random(42)
        self._timestamp = timestamp
        self._positions: dict[str, BrokerPosition] = {}
        self._submitted: list[Order] = []
        self._connected: bool = True

    # ──────────────────────────────────────────────────────────────────
    # BrokerAdapter interface
    # ──────────────────────────────────────────────────────────────────

    def submit_order(self, order: Order) -> BrokerResponse:
        self._submitted.append(order)
        ts = self._timestamp or datetime.utcnow()
        broker_oid = str(uuid.uuid4())

        current_price = self._prices.get(order.symbol, Decimal("0"))
        is_buy = order.side == OrderSide.BUY

        # ── eligibility check ────────────────────────────────────────
        if not self._is_eligible(order, current_price):
            return BrokerResponse(
                success=True,
                broker_order_id=broker_oid,
                fills=[],
                status=OrderStatus.SUBMITTED,
                message="Order submitted; price condition not met",
            )

        # ── fill probability check ───────────────────────────────────
        if not self._should_fill():
            return BrokerResponse(
                success=True,
                broker_order_id=broker_oid,
                fills=[],
                status=OrderStatus.SUBMITTED,
                message="Order submitted; fill skipped by probability",
            )

        # ── compute fill price ───────────────────────────────────────
        fill_price = self._slippage.apply(current_price, is_buy)

        # ── partial fill? ─────────────────────────────────────────────
        fill_qty = self._compute_fill_quantity(order.quantity)

        fill = Fill(
            fill_id=str(uuid.uuid4()),
            order_id=order.order_id,
            quantity=fill_qty,
            price=fill_price,
            timestamp=ts,
        )

        fill_status = (
            OrderStatus.FILLED if fill_qty == order.quantity else OrderStatus.PARTIALLY_FILLED
        )

        # ── update internal cash/positions ──────────────────────────
        self._apply_fill_to_account(order, fill)

        return BrokerResponse(
            success=True,
            broker_order_id=broker_oid,
            fills=[fill],
            status=fill_status,
            message=f"Paper fill: {fill_qty} @ {fill_price}",
        )

    def cancel_order(self, broker_order_id: str) -> bool:
        return True

    def get_positions(self) -> list[BrokerPosition]:
        return list(self._positions.values())

    def get_account_info(self) -> AccountInfo:
        portfolio_val = self._cash + sum(
            p.average_price * Decimal(str(p.quantity))
            for p in self._positions.values()
        )
        return AccountInfo(
            account_id="paper-account",
            cash_balance=self._cash,
            portfolio_value=portfolio_val,
            buying_power=self._cash,
        )

    def is_connected(self) -> bool:
        return self._connected

    # ──────────────────────────────────────────────────────────────────
    # Price updates
    # ──────────────────────────────────────────────────────────────────

    def update_price(self, symbol: str, price: Decimal) -> None:
        self._prices[symbol] = price

    # ──────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────

    def _is_eligible(self, order: Order, current_price: Decimal) -> bool:
        if current_price <= Decimal("0"):
            return False
        if order.order_type == OrderType.MARKET:
            return True
        if order.order_type == OrderType.LIMIT:
            lp = order.limit_price or Decimal("0")
            return (order.side == OrderSide.BUY and lp >= current_price) or \
                   (order.side == OrderSide.SELL and lp <= current_price)
        if order.order_type == OrderType.STOP:
            sp = order.stop_price or Decimal("0")
            return (order.side == OrderSide.BUY and sp <= current_price) or \
                   (order.side == OrderSide.SELL and sp >= current_price)
        if order.order_type == OrderType.STOP_LIMIT:
            sp = order.stop_price or Decimal("0")
            lp = order.limit_price or Decimal("0")
            stop_triggered = (order.side == OrderSide.BUY and sp <= current_price) or \
                             (order.side == OrderSide.SELL and sp >= current_price)
            limit_ok = (order.side == OrderSide.BUY and lp >= current_price) or \
                       (order.side == OrderSide.SELL and lp <= current_price)
            return stop_triggered and limit_ok
        return False

    def _should_fill(self) -> bool:
        if self._fill_prob >= 1.0:
            return True
        if self._fill_prob <= 0.0:
            return False
        return self._rng.random() < self._fill_prob

    def _compute_fill_quantity(self, quantity: int) -> int:
        if self._partial_prob <= 0.0:
            return quantity
        if self._partial_prob >= 1.0:
            return max(1, quantity // 2)
        if self._rng.random() < self._partial_prob:
            return max(1, quantity // 2)
        return quantity

    def _apply_fill_to_account(self, order: Order, fill: Fill) -> None:
        symbol = order.symbol
        cost = fill.price * Decimal(str(fill.quantity))

        if order.side == OrderSide.BUY:
            self._cash -= cost
            if symbol in self._positions:
                pos = self._positions[symbol]
                new_qty = pos.quantity + fill.quantity
                new_avg = (pos.average_price * Decimal(str(pos.quantity)) + cost) / Decimal(str(new_qty))
                self._positions[symbol] = BrokerPosition(symbol=symbol, quantity=new_qty, average_price=new_avg)
            else:
                self._positions[symbol] = BrokerPosition(symbol=symbol, quantity=fill.quantity, average_price=fill.price)
        else:
            self._cash += cost
            if symbol in self._positions:
                pos = self._positions[symbol]
                new_qty = pos.quantity - fill.quantity
                if new_qty <= 0:
                    del self._positions[symbol]
                else:
                    self._positions[symbol] = BrokerPosition(symbol=symbol, quantity=new_qty, average_price=pos.average_price)

    @property
    def submitted_orders(self) -> list[Order]:
        return list(self._submitted)

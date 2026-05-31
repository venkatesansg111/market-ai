"""Phase 7 — Deterministic mock broker for unit testing."""
from __future__ import annotations

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
    OrderStatus,
    OrderSide,
)
from execution.slippage_model import SlippageModel, ZeroSlippageModel


class MockBrokerAdapter(BrokerAdapter):
    """Fully deterministic broker for unit tests.

    - Always fills at `fill_price` if supplied, else uses slippage model.
    - Stores submitted orders for assertion in tests.
    - Rejection is controlled by `reject_next` flag.
    """

    def __init__(
        self,
        fill_price: Optional[Decimal] = None,
        slippage_model: Optional[SlippageModel] = None,
        initial_cash: Decimal = Decimal("1000000"),
        timestamp: Optional[datetime] = None,
    ) -> None:
        self._fill_price = fill_price
        self._slippage = slippage_model or ZeroSlippageModel()
        self._cash = initial_cash
        self._timestamp = timestamp
        self._submitted_orders: list[Order] = []
        self._cancelled_ids: list[str] = []
        self.reject_next: bool = False
        self._connected: bool = True

    # ──────────────────────────────────────────────────────────────────
    # BrokerAdapter interface
    # ──────────────────────────────────────────────────────────────────

    def submit_order(self, order: Order) -> BrokerResponse:
        self._submitted_orders.append(order)

        if self.reject_next:
            self.reject_next = False
            return BrokerResponse(
                success=False,
                broker_order_id=None,
                fills=[],
                status=OrderStatus.REJECTED,
                message="Mock rejection",
            )

        broker_oid = str(uuid.uuid4())
        ts = self._timestamp or datetime.utcnow()
        is_buy = order.side == OrderSide.BUY

        if self._fill_price is not None:
            price = self._fill_price
        else:
            raw = order.limit_price or order.stop_price or Decimal("0")
            price = self._slippage.apply(raw, is_buy) if raw > Decimal("0") else Decimal("100")

        fill = Fill(
            fill_id=str(uuid.uuid4()),
            order_id=order.order_id,
            quantity=order.quantity,
            price=price,
            timestamp=ts,
        )

        return BrokerResponse(
            success=True,
            broker_order_id=broker_oid,
            fills=[fill],
            status=OrderStatus.FILLED,
            message="Mock fill",
        )

    def cancel_order(self, broker_order_id: str) -> bool:
        self._cancelled_ids.append(broker_order_id)
        return True

    def get_positions(self) -> list[BrokerPosition]:
        return []

    def get_account_info(self) -> AccountInfo:
        return AccountInfo(
            account_id="mock-account",
            cash_balance=self._cash,
            portfolio_value=self._cash,
            buying_power=self._cash,
        )

    def is_connected(self) -> bool:
        return self._connected

    # ──────────────────────────────────────────────────────────────────
    # Test helpers
    # ──────────────────────────────────────────────────────────────────

    @property
    def submitted_orders(self) -> list[Order]:
        return list(self._submitted_orders)

    @property
    def cancelled_ids(self) -> list[str]:
        return list(self._cancelled_ids)

    def reset(self) -> None:
        self._submitted_orders.clear()
        self._cancelled_ids.clear()
        self.reject_next = False

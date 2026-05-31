"""Phase 7 — Execution Engine: signal → order → fill → position."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from execution.broker_adapter import BrokerAdapter
from execution.execution_models import (
    ExecutionRequest,
    ExecutionResult,
    Fill,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
)
from execution.mock_broker import MockBrokerAdapter
from execution.order_manager import OrderManager
from execution.position_manager import PositionManager
from execution.slippage_model import FixedBpsSlippageModel, SlippageModel
from meta.meta_models import MetaSignal, RoutingMode


def meta_signal_to_request(
    signal: MetaSignal,
    quantity: int,
    current_price: Decimal,
    side: OrderSide = OrderSide.BUY,
    order_type: OrderType = OrderType.MARKET,
) -> ExecutionRequest:
    """Convert a MetaSignal into an ExecutionRequest for the execution engine."""
    return ExecutionRequest(
        symbol=signal.instrument,
        side=side,
        order_type=order_type,
        quantity=quantity,
        current_price=current_price,
        strategy_name=signal.selected_strategy,
        timeframe=signal.timeframe,
        confidence=signal.confidence,
        reference_id=signal.run_id,
    )


class ExecutionEngine:
    """Orchestrates the full signal→order→fill→position lifecycle.

    Dependencies are injectable for unit-test isolation.
    """

    def __init__(
        self,
        broker: Optional[BrokerAdapter] = None,
        order_manager: Optional[OrderManager] = None,
        position_manager: Optional[PositionManager] = None,
        slippage_model: Optional[SlippageModel] = None,
    ) -> None:
        self._broker = broker or MockBrokerAdapter()
        self._oms = order_manager or OrderManager()
        self._positions = position_manager or PositionManager()
        self._slippage = slippage_model or FixedBpsSlippageModel()

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def execute(
        self,
        request: ExecutionRequest,
        timestamp: Optional[datetime] = None,
    ) -> ExecutionResult:
        """Process an ExecutionRequest end-to-end.

        1. Create order in OMS (NEW)
        2. Submit to broker (NEW → SUBMITTED)
        3. Apply fills from broker response
        4. Update positions for each fill
        5. Return ExecutionResult
        """
        ts = timestamp or datetime.utcnow()

        # 1. Create order
        order = self._oms.create_order(
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            quantity=request.quantity,
            strategy_name=request.strategy_name,
            timeframe=request.timeframe,
            reference_id=request.reference_id,
            limit_price=request.limit_price,
            stop_price=request.stop_price,
            metadata=dict(request.metadata),
            timestamp=ts,
        )

        # 2. Submit to broker
        order = self._oms.submit_order(order.order_id, timestamp=ts)

        broker_resp = self._broker.submit_order(order)

        if not broker_resp.success:
            order = self._oms.reject_order(
                order.order_id,
                reason=broker_resp.message,
                timestamp=ts,
            )
            return ExecutionResult(
                order_id=order.order_id,
                symbol=order.symbol,
                status=OrderStatus.REJECTED,
                fills=[],
                message=broker_resp.message,
            )

        # 3 & 4. Apply fills
        fills: list[Fill] = []
        current_order = order
        for fill in broker_resp.fills:
            current_order = self._oms.apply_fill(current_order.order_id, fill)
            self._positions.apply_fill(current_order, fill)
            fills.append(fill)

        # If broker returned SUBMITTED (no fills yet), just leave order as submitted
        final_status = current_order.status

        return ExecutionResult(
            order_id=current_order.order_id,
            symbol=current_order.symbol,
            status=final_status,
            fills=fills,
            message=broker_resp.message,
        )

    def execute_from_signal(
        self,
        signal: MetaSignal,
        quantity: int,
        current_price: Decimal,
        side: OrderSide = OrderSide.BUY,
        order_type: OrderType = OrderType.MARKET,
        timestamp: Optional[datetime] = None,
    ) -> ExecutionResult:
        """Convenience wrapper: MetaSignal → ExecutionRequest → execute()."""
        req = meta_signal_to_request(signal, quantity, current_price, side, order_type)
        return self.execute(req, timestamp=timestamp)

    # ──────────────────────────────────────────────────────────────────
    # Accessors
    # ──────────────────────────────────────────────────────────────────

    @property
    def order_manager(self) -> OrderManager:
        return self._oms

    @property
    def position_manager(self) -> PositionManager:
        return self._positions

    @property
    def broker(self) -> BrokerAdapter:
        return self._broker

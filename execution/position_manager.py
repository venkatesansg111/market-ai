"""Phase 7 — Position tracking and reconciliation."""
from __future__ import annotations

import dataclasses
from datetime import datetime
from decimal import Decimal
from typing import Optional

from execution.execution_models import (
    BrokerPosition,
    Fill,
    Order,
    OrderSide,
    Position,
    ReconciliationResult,
)


class PositionManager:
    """Track positions based on fills and reconcile against broker state."""

    def __init__(self) -> None:
        self._positions: dict[str, Position] = {}

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def apply_fill(self, order: Order, fill: Fill) -> Position:
        """Update position for order.symbol based on the fill and return new snapshot."""
        symbol = order.symbol
        is_buy = order.side == OrderSide.BUY
        fill_qty = fill.quantity if is_buy else -fill.quantity
        fill_value = fill.price * Decimal(str(fill.quantity))

        if symbol not in self._positions:
            self._positions[symbol] = Position(
                symbol=symbol,
                quantity=fill_qty,
                average_price=fill.price,
                realized_pnl=Decimal("0"),
                last_updated=fill.timestamp,
            )
            return self._positions[symbol]

        pos = self._positions[symbol]
        current_qty = pos.quantity
        new_qty = current_qty + fill_qty
        realized = pos.realized_pnl

        if current_qty == 0:
            new_avg = fill.price
        elif (current_qty > 0) == (fill_qty > 0):
            # Adding to existing position — update weighted average
            old_value = pos.average_price * Decimal(str(abs(current_qty)))
            new_avg = (old_value + fill_value) / Decimal(str(abs(new_qty))) if new_qty != 0 else fill.price
        else:
            # Reducing or reversing position — realize P&L on closed portion
            closed_qty = min(abs(current_qty), abs(fill_qty))
            if current_qty > 0:
                realized += (fill.price - pos.average_price) * Decimal(str(closed_qty))
            else:
                realized += (pos.average_price - fill.price) * Decimal(str(closed_qty))

            if abs(fill_qty) > abs(current_qty):
                # Position reversal — new side opens
                new_avg = fill.price
            else:
                new_avg = pos.average_price

        updated = Position(
            symbol=symbol,
            quantity=new_qty,
            average_price=new_avg if new_qty != 0 else Decimal("0"),
            realized_pnl=realized,
            last_updated=fill.timestamp,
        )
        self._positions[symbol] = updated
        return updated

    def get_position(self, symbol: str) -> Optional[Position]:
        return self._positions.get(symbol)

    def all_positions(self) -> list[Position]:
        return list(self._positions.values())

    def open_positions(self) -> list[Position]:
        return [p for p in self._positions.values() if not p.is_flat]

    def total_realized_pnl(self) -> Decimal:
        return sum((p.realized_pnl for p in self._positions.values()), Decimal("0"))

    def reconcile(self, broker_positions: list[BrokerPosition]) -> ReconciliationResult:
        """Compare local positions against broker snapshot."""
        local_symbols = {s for s, p in self._positions.items() if not p.is_flat}
        broker_map = {bp.symbol: bp for bp in broker_positions}
        broker_symbols = set(broker_map.keys())

        matched: list[str] = []
        mismatched: list[str] = []

        for sym in local_symbols & broker_symbols:
            local = self._positions[sym]
            broker = broker_map[sym]
            if local.quantity == broker.quantity:
                matched.append(sym)
            else:
                mismatched.append(sym)

        only_local = sorted(local_symbols - broker_symbols)
        only_broker = sorted(broker_symbols - local_symbols)

        return ReconciliationResult(
            matched=sorted(matched),
            mismatched=sorted(mismatched),
            only_local=only_local,
            only_broker=only_broker,
        )

    def reset(self) -> None:
        self._positions.clear()

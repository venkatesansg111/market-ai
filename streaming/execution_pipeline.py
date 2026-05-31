"""Phase 9 — Execution pipeline: SignalEvent → Risk → Order → Fill → Portfolio."""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from execution.execution_engine import ExecutionEngine
from execution.execution_models import ExecutionRequest, OrderSide, OrderType
from risk.portfolio_state import PortfolioStateEngine
from risk.risk_gate import RiskGate
from risk.risk_models import RiskParams, SignalInput, SizingMethod
from streaming.event_bus import EventBus
from streaming.event_models import (
    FillEvent,
    OrderEvent,
    PortfolioEvent,
    RiskEvent,
    SignalEvent,
)

logger = logging.getLogger(__name__)


class ExecutionPipeline:
    """
    Wires Phase 8 (Risk) + Phase 7 (Execution) into the streaming event bus.

    Flow per SignalEvent:
        1. Skip FLAT signals
        2. Convert to SignalInput → RiskGate.evaluate() → RiskDecision
        3. Emit RiskEvent
        4. If BLOCKED: return
        5. Build ExecutionRequest with approved quantity
        6. ExecutionEngine.execute() → ExecutionResult
        7. Emit OrderEvent + FillEvent(s)
        8. Update PortfolioStateEngine
        9. Emit PortfolioEvent

    All components are injected (fully testable via MockBrokerAdapter).
    """

    def __init__(
        self,
        event_bus: EventBus,
        execution_engine: ExecutionEngine,
        risk_gate: RiskGate,
        portfolio_state: PortfolioStateEngine,
        params: RiskParams,
    ) -> None:
        self._bus = event_bus
        self._engine = execution_engine
        self._risk_gate = risk_gate
        self._portfolio = portfolio_state
        self._params = params

        self._processed: int = 0
        self._filled: int = 0
        self._blocked: int = 0

        event_bus.subscribe(SignalEvent, self.on_signal)

    # ──────────────────────────────────────────────────────────────────
    # Signal handler
    # ──────────────────────────────────────────────────────────────────

    def on_signal(self, event: SignalEvent) -> None:
        self._processed += 1

        if event.action.upper() == "FLAT":
            logger.debug("ExecutionPipeline: FLAT signal for %s — skipped", event.symbol)
            return

        # ── 1. Risk evaluation ─────────────────────────────────────────
        signal_input = SignalInput(
            symbol=event.symbol,
            strategy_name=event.strategy_name,
            action=event.action,
            confidence=event.confidence,
            timeframe=event.timeframe,
            current_price=event.current_price,
            atr=event.atr,
            stop_price=event.stop_price,
            regime_strength=event.regime_strength,
            run_id=event.run_id,
        )

        decision = self._risk_gate.evaluate(signal_input)

        risk_ev = RiskEvent(
            symbol=event.symbol,
            strategy_name=event.strategy_name,
            decision=decision.decision.value.upper(),
            approved_quantity=decision.approved_quantity,
            original_quantity=decision.original_quantity,
            reason=decision.reason,
            timestamp=event.timestamp,
        )
        self._bus.publish(risk_ev)

        if not decision.is_approved or decision.approved_quantity == 0:
            self._blocked += 1
            logger.info(
                "ExecutionPipeline: %s BLOCKED — %s", event.symbol, decision.reason
            )
            return

        # ── 2. Build execution request ─────────────────────────────────
        side = OrderSide.BUY if event.action.upper() == "BUY" else OrderSide.SELL
        request = ExecutionRequest(
            symbol=event.symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=decision.approved_quantity,
            current_price=event.current_price,
            strategy_name=event.strategy_name,
            timeframe=event.timeframe,
            confidence=event.confidence,
            reference_id=event.run_id,
        )

        # ── 3. Execute ─────────────────────────────────────────────────
        try:
            result = self._engine.execute(request, timestamp=event.timestamp)
        except Exception as exc:
            logger.error(
                "ExecutionPipeline: execution failed for %s: %s", event.symbol, exc,
                exc_info=True,
            )
            return

        # ── 4. Emit order event ────────────────────────────────────────
        order_ev = OrderEvent(
            order_id=result.order_id,
            symbol=event.symbol,
            action=event.action.upper(),
            quantity=decision.approved_quantity,
            strategy_name=event.strategy_name,
            timestamp=event.timestamp,
        )
        self._bus.publish(order_ev)

        if not result.fills:
            logger.debug("ExecutionPipeline: no fills for %s order %s", event.symbol, result.order_id)
            return

        # ── 5. Emit fills + update portfolio ──────────────────────────
        for fill in result.fills:
            fill_ev = FillEvent(
                order_id=result.order_id,
                symbol=event.symbol,
                quantity=fill.quantity,
                price=fill.price,
                strategy_name=event.strategy_name,
                action=event.action.upper(),
                commission=fill.commission,
                timestamp=event.timestamp,
            )
            self._bus.publish(fill_ev)

            # Update Phase 8 portfolio state
            signed_qty = fill.quantity if event.action.upper() == "BUY" else -fill.quantity
            self._portfolio.record_fill(
                symbol=event.symbol,
                quantity=signed_qty,
                fill_price=fill.price,
                strategy_name=event.strategy_name,
                commission=fill.commission,
            )
            self._portfolio.update_price(event.symbol, fill.price)

        # ── 6. Emit portfolio snapshot ─────────────────────────────────
        metrics = self._portfolio.risk_metrics()
        port_ev = PortfolioEvent(
            equity=metrics.equity,
            cash=metrics.cash,
            unrealized_pnl=self._portfolio.unrealized_pnl,
            realized_pnl=self._portfolio.realized_pnl_total,
            daily_pnl=metrics.daily_pnl,
            current_drawdown_pct=metrics.current_drawdown_pct,
            timestamp=event.timestamp,
        )
        self._bus.publish(port_ev)
        self._filled += 1

        logger.debug(
            "ExecutionPipeline: filled %s qty=%d @ %s — equity=%s",
            event.symbol, result.total_filled_quantity,
            result.average_fill_price, metrics.equity,
        )

    # ──────────────────────────────────────────────────────────────────
    # Metrics
    # ──────────────────────────────────────────────────────────────────

    @property
    def processed(self) -> int:
        return self._processed

    @property
    def filled(self) -> int:
        return self._filled

    @property
    def blocked(self) -> int:
        return self._blocked

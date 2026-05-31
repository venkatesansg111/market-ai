"""Phase 8 — Risk Decision Gate: final filter before Execution Engine."""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from risk.portfolio_state import PortfolioStateEngine
from risk.risk_controls import RiskControlsEngine
from risk.risk_models import (
    PortfolioOrder,
    RiskDecision,
    RiskDecisionType,
    RiskParams,
    SignalInput,
    SizingResult,
)
from risk.position_sizer import calculate_position_size

logger = logging.getLogger(__name__)


class RiskGate:
    """
    Single entry point that combines sizing + all risk controls.

    Usage:
        gate = RiskGate(params, state)
        decision = gate.evaluate(signal)
        if decision.is_approved:
            engine.execute(...)
    """

    def __init__(
        self,
        params: RiskParams,
        state: PortfolioStateEngine,
        controls_engine: RiskControlsEngine | None = None,
    ) -> None:
        self._params = params
        self._state = state
        self._controls = controls_engine or RiskControlsEngine(params)

    # ──────────────────────────────────────────────────────────────────
    # Main evaluate — from raw signal
    # ──────────────────────────────────────────────────────────────────

    def evaluate(self, signal: SignalInput) -> RiskDecision:
        """
        Size the position then run all risk controls.

        Returns a RiskDecision indicating approved / reduced / blocked.
        """
        # 1. Compute position size
        sizing = calculate_position_size(signal, self._state, self._params)
        raw_qty = sizing.adjusted_quantity

        if raw_qty == 0:
            return RiskDecision(
                symbol=signal.symbol,
                strategy_name=signal.strategy_name,
                decision=RiskDecisionType.BLOCKED,
                approved_quantity=0,
                original_quantity=0,
                reason="sizer returned zero quantity",
            )

        # 2. Run all controls
        approved, final_qty, reason = self._controls.evaluate(signal, raw_qty, self._state)

        if not approved:
            logger.info("RiskGate BLOCKED %s: %s", signal.symbol, reason)
            return RiskDecision(
                symbol=signal.symbol,
                strategy_name=signal.strategy_name,
                decision=RiskDecisionType.BLOCKED,
                approved_quantity=0,
                original_quantity=raw_qty,
                reason=reason,
            )

        decision_type = (
            RiskDecisionType.REDUCED if final_qty < raw_qty else RiskDecisionType.APPROVED
        )

        logger.info(
            "RiskGate %s %s: qty=%d (from %d) %s",
            decision_type.value.upper(), signal.symbol, final_qty, raw_qty, reason,
        )
        return RiskDecision(
            symbol=signal.symbol,
            strategy_name=signal.strategy_name,
            decision=decision_type,
            approved_quantity=final_qty,
            original_quantity=raw_qty,
            reason=reason,
        )

    # ──────────────────────────────────────────────────────────────────
    # Evaluate a pre-sized PortfolioOrder (from PortfolioConstructor)
    # ──────────────────────────────────────────────────────────────────

    def evaluate_order(self, order: PortfolioOrder) -> RiskDecision:
        """
        Validate a PortfolioOrder that already has a quantity assigned.
        Skips sizing; only applies risk controls.
        """
        signal = SignalInput(
            symbol=order.symbol,
            strategy_name=order.strategy_name,
            action=order.action,
            confidence=order.confidence,
            timeframe=order.timeframe,
            current_price=order.current_price,
            stop_price=order.stop_price,
            run_id=order.run_id,
        )

        approved, final_qty, reason = self._controls.evaluate(signal, order.quantity, self._state)

        if not approved:
            logger.info("RiskGate BLOCKED order %s: %s", order.symbol, reason)
            return RiskDecision(
                symbol=order.symbol,
                strategy_name=order.strategy_name,
                decision=RiskDecisionType.BLOCKED,
                approved_quantity=0,
                original_quantity=order.quantity,
                reason=reason,
            )

        decision_type = (
            RiskDecisionType.REDUCED if final_qty < order.quantity else RiskDecisionType.APPROVED
        )
        return RiskDecision(
            symbol=order.symbol,
            strategy_name=order.strategy_name,
            decision=decision_type,
            approved_quantity=final_qty,
            original_quantity=order.quantity,
            reason=reason,
        )

    # ──────────────────────────────────────────────────────────────────
    # Emergency halt (manual override)
    # ──────────────────────────────────────────────────────────────────

    def is_trading_halted(self) -> bool:
        """True if drawdown or daily loss conditions alone would block all trades."""
        metrics = self._state.risk_metrics()
        if metrics.current_drawdown_pct >= self._params.max_drawdown_pct:
            return True
        if metrics.daily_pnl_pct <= -self._params.daily_loss_limit_pct:
            return True
        return False


def risk_gate(
    order: PortfolioOrder,
    state: PortfolioStateEngine,
    params: RiskParams,
) -> RiskDecision:
    """
    Module-level convenience function matching the spec signature.

    Returns a RiskDecision; caller checks decision.is_approved.
    """
    gate = RiskGate(params, state)
    return gate.evaluate_order(order)

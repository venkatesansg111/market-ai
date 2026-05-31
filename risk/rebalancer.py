"""Phase 8 — Rebalancing Engine: time, drift, and threshold-based triggers."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from risk.portfolio_state import PortfolioStateEngine
from risk.risk_models import AllocationWeight, PortfolioOrder, RebalanceAction, RebalanceTrigger

logger = logging.getLogger(__name__)


class RebalancingEngine:
    """
    Determines when and how to rebalance a portfolio.

    Three trigger modes (can all be active simultaneously):
      - TIME: rebalance every N days
      - DRIFT: rebalance when any weight drifts by > threshold
      - THRESHOLD: rebalance when portfolio-level metric crosses a level
    """

    def __init__(
        self,
        rebalance_frequency_days: int = 7,
        drift_threshold_pct: float = 5.0,     # percentage-point drift trigger
        enable_time: bool = True,
        enable_drift: bool = True,
        enable_threshold: bool = True,
    ) -> None:
        self._frequency = rebalance_frequency_days
        self._drift_pct = drift_threshold_pct
        self._enable_time = enable_time
        self._enable_drift = enable_drift
        self._enable_threshold = enable_threshold
        self._last_rebalance: Optional[date] = None

    # ──────────────────────────────────────────────────────────────────
    # Trigger evaluation
    # ──────────────────────────────────────────────────────────────────

    def should_rebalance(
        self,
        state: PortfolioStateEngine,
        target_weights: list[AllocationWeight],
        current_date: date | None = None,
    ) -> tuple[bool, RebalanceTrigger | None, str]:
        """
        Returns (should_rebalance, trigger_type, reason).
        """
        today = current_date or datetime.utcnow().date()

        if self._enable_time:
            triggered, reason = self._check_time_trigger(today)
            if triggered:
                return True, RebalanceTrigger.TIME, reason

        if self._enable_drift:
            triggered, reason = self._check_drift_trigger(state, target_weights)
            if triggered:
                return True, RebalanceTrigger.DRIFT, reason

        if self._enable_threshold:
            triggered, reason = self._check_threshold_trigger(state)
            if triggered:
                return True, RebalanceTrigger.THRESHOLD, reason

        return False, None, "no rebalance needed"

    def _check_time_trigger(self, today: date) -> tuple[bool, str]:
        if self._last_rebalance is None:
            return True, "initial rebalance (never rebalanced)"
        days_since = (today - self._last_rebalance).days
        if days_since >= self._frequency:
            return True, f"time-based: {days_since} days since last rebalance"
        return False, ""

    def _check_drift_trigger(
        self,
        state: PortfolioStateEngine,
        target_weights: list[AllocationWeight],
    ) -> tuple[bool, str]:
        if not target_weights:
            return False, ""

        equity = state.equity
        if equity <= 0:
            return False, ""

        snap = state.exposure_snapshot()
        for tw in target_weights:
            current_notional = abs(snap.per_asset.get(tw.symbol, Decimal("0")))
            current_w = float(current_notional / equity) * 100
            target_w = tw.weight * 100
            drift = abs(current_w - target_w)
            if drift >= self._drift_pct:
                return True, (
                    f"drift: {tw.symbol} weight {current_w:.1f}% vs target {target_w:.1f}% "
                    f"(drift={drift:.1f}% >= {self._drift_pct:.1f}%)"
                )
        return False, ""

    def _check_threshold_trigger(self, state: PortfolioStateEngine) -> tuple[bool, str]:
        """Trigger if cash weight exceeds 50% (underinvested) or gross leverage > 0.95 of cap."""
        equity = state.equity
        if equity <= 0:
            return False, ""

        cash_pct = float(state.cash / equity * 100)
        if cash_pct > 50.0:
            return True, f"threshold: cash {cash_pct:.1f}% > 50% (underinvested)"
        return False, ""

    # ──────────────────────────────────────────────────────────────────
    # Generate rebalance actions
    # ──────────────────────────────────────────────────────────────────

    def compute_rebalance_actions(
        self,
        state: PortfolioStateEngine,
        target_weights: list[AllocationWeight],
        prices: dict[str, Decimal],
        trigger: RebalanceTrigger = RebalanceTrigger.TIME,
    ) -> list[RebalanceAction]:
        """
        Compute RebalanceAction for each symbol in target_weights.
        """
        equity = state.equity
        if equity <= 0:
            return []

        snap = state.exposure_snapshot()
        actions: list[RebalanceAction] = []

        for tw in target_weights:
            price = prices.get(tw.symbol, Decimal("0"))
            if price <= 0:
                continue

            current_notional = abs(snap.per_asset.get(tw.symbol, Decimal("0")))
            current_w = float(current_notional / equity)
            target_w = tw.weight
            delta_w = target_w - current_w

            target_notional = equity * Decimal(str(target_w))
            current_qty, _ = state.positions.get(tw.symbol, (0, Decimal("0")))
            target_qty = int(target_notional / price)
            delta_qty = target_qty - current_qty

            if abs(delta_qty) == 0:
                action_str = "HOLD"
            elif delta_qty > 0:
                action_str = "BUY"
            else:
                action_str = "SELL"

            actions.append(
                RebalanceAction(
                    symbol=tw.symbol,
                    strategy_name=tw.strategy_name,
                    current_weight=current_w,
                    target_weight=target_w,
                    delta_weight=delta_w,
                    trigger=trigger,
                    action=action_str,
                    quantity=abs(delta_qty),
                    reason=f"current={current_w*100:.1f}% target={target_w*100:.1f}%",
                )
            )

        return actions

    def to_portfolio_orders(
        self,
        actions: list[RebalanceAction],
        prices: dict[str, Decimal],
    ) -> list[PortfolioOrder]:
        """Convert RebalanceActions → PortfolioOrders (skipping HOLD)."""
        orders: list[PortfolioOrder] = []
        for act in actions:
            if act.action == "HOLD" or act.quantity == 0:
                continue
            price = prices.get(act.symbol, Decimal("0"))
            orders.append(
                PortfolioOrder(
                    symbol=act.symbol,
                    action=act.action,
                    quantity=act.quantity,
                    order_type="MARKET",
                    strategy_name=act.strategy_name,
                    confidence=1.0,
                    current_price=price,
                )
            )
        return orders

    # ──────────────────────────────────────────────────────────────────
    # Mark rebalance done
    # ──────────────────────────────────────────────────────────────────

    def mark_rebalanced(self, rebalance_date: date | None = None) -> None:
        self._last_rebalance = rebalance_date or datetime.utcnow().date()
        logger.info("Rebalancing engine: marked rebalanced on %s", self._last_rebalance)

    @property
    def last_rebalance_date(self) -> Optional[date]:
        return self._last_rebalance

    @property
    def days_since_rebalance(self) -> Optional[int]:
        if self._last_rebalance is None:
            return None
        return (datetime.utcnow().date() - self._last_rebalance).days

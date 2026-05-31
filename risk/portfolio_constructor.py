"""Phase 8 — Portfolio Construction Engine."""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from risk.allocation_models import AllocationModel, EqualWeightModel, get_allocation_model
from risk.portfolio_state import PortfolioStateEngine
from risk.risk_models import (
    AllocationModelType,
    AllocationWeight,
    PortfolioOrder,
    RiskParams,
    SignalInput,
)

logger = logging.getLogger(__name__)


class PortfolioConstructor:
    """
    Aggregates signals from multiple strategies and allocates capital.

    Pipeline:
    1. Receive list[SignalInput] from Phase 6 / RiskEngine
    2. Apply allocation model to determine weights
    3. Convert weights + equity into quantities
    4. Return list[PortfolioOrder] ready for the risk gate
    """

    def __init__(
        self,
        allocation_model: AllocationModel | None = None,
        model_type: AllocationModelType = AllocationModelType.EQUAL_WEIGHT,
    ) -> None:
        self._model = allocation_model or get_allocation_model(model_type)

    # ──────────────────────────────────────────────────────────────────
    # Core entry point
    # ──────────────────────────────────────────────────────────────────

    def build_portfolio(
        self,
        signals: list[SignalInput],
        state: PortfolioStateEngine,
        params: RiskParams,
        volatilities: dict[str, float] | None = None,
        strategy_scores: dict[str, float] | None = None,
    ) -> list[PortfolioOrder]:
        """
        Convert a list of signals into portfolio orders with capital allocation.
        """
        if not signals:
            return []

        # Only process BUY/SELL signals; skip FLAT
        active = [s for s in signals if s.action.upper() in ("BUY", "SELL")]
        if not active:
            return []

        symbols = [s.symbol for s in active]
        strategy_names = [s.strategy_name for s in active]
        vols = volatilities or {}

        weights = self._model.allocate(
            symbols=symbols,
            strategy_names=strategy_names,
            volatilities=vols,
            strategy_scores=strategy_scores,
        )

        # Validate weights sum ≈ 1.0
        weight_sum = sum(w.weight for w in weights)
        if abs(weight_sum - 1.0) > 0.01 and weight_sum > 0:
            weights = [
                AllocationWeight(
                    symbol=w.symbol,
                    strategy_name=w.strategy_name,
                    weight=w.weight / weight_sum,
                    model=w.model,
                    volatility=w.volatility,
                )
                for w in weights
            ]

        equity = state.equity
        orders: list[PortfolioOrder] = []
        weight_map = {w.symbol: w for w in weights}

        for signal in active:
            weight = weight_map.get(signal.symbol)
            if weight is None:
                continue

            allocated_capital = equity * Decimal(str(weight.weight))
            qty = self._capital_to_qty(allocated_capital, signal.current_price, params)

            if qty == 0:
                logger.debug("build_portfolio: %s qty=0 skipped", signal.symbol)
                continue

            orders.append(
                PortfolioOrder(
                    symbol=signal.symbol,
                    action=signal.action.upper(),
                    quantity=qty,
                    order_type="MARKET",
                    strategy_name=signal.strategy_name,
                    confidence=signal.confidence,
                    current_price=signal.current_price,
                    stop_price=signal.stop_price,
                    timeframe=signal.timeframe,
                    run_id=signal.run_id,
                )
            )
            logger.debug(
                "build_portfolio: %s qty=%d weight=%.4f alloc=%s",
                signal.symbol, qty, weight.weight, allocated_capital,
            )

        return orders

    # ──────────────────────────────────────────────────────────────────
    # Single-signal convenience wrapper
    # ──────────────────────────────────────────────────────────────────

    def build_single(
        self,
        signal: SignalInput,
        state: PortfolioStateEngine,
        params: RiskParams,
        capital_fraction: float = 1.0,  # fraction of equity to allocate
    ) -> PortfolioOrder | None:
        """Build a single order using a direct fraction of equity."""
        equity = state.equity
        allocated = equity * Decimal(str(min(1.0, max(0.0, capital_fraction))))
        qty = self._capital_to_qty(allocated, signal.current_price, params)
        if qty == 0:
            return None
        return PortfolioOrder(
            symbol=signal.symbol,
            action=signal.action.upper(),
            quantity=qty,
            order_type="MARKET",
            strategy_name=signal.strategy_name,
            confidence=signal.confidence,
            current_price=signal.current_price,
            stop_price=signal.stop_price,
            timeframe=signal.timeframe,
            run_id=signal.run_id,
        )

    # ──────────────────────────────────────────────────────────────────
    # Rebalance orders from current → target weights
    # ──────────────────────────────────────────────────────────────────

    def compute_rebalance_orders(
        self,
        target_weights: list[AllocationWeight],
        state: PortfolioStateEngine,
        params: RiskParams,
        prices: dict[str, Decimal],
    ) -> list[PortfolioOrder]:
        """
        Given target weights, compute buy/sell orders to move from current
        portfolio composition to the target.
        """
        equity = state.equity
        orders: list[PortfolioOrder] = []

        for tw in target_weights:
            sym = tw.symbol
            price = prices.get(sym, Decimal("0"))
            if price <= 0:
                continue

            target_notional = equity * Decimal(str(tw.weight))
            target_qty = int(target_notional / price)

            current_qty, _ = state.positions.get(sym, (0, Decimal("0")))
            delta = target_qty - current_qty

            if delta == 0:
                continue

            action = "BUY" if delta > 0 else "SELL"
            orders.append(
                PortfolioOrder(
                    symbol=sym,
                    action=action,
                    quantity=abs(delta),
                    order_type="MARKET",
                    strategy_name=tw.strategy_name,
                    confidence=1.0,
                    current_price=price,
                )
            )

        return orders

    # ──────────────────────────────────────────────────────────────────
    # Helper
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _capital_to_qty(capital: Decimal, price: Decimal, params: RiskParams) -> int:
        if price <= 0:
            return 0
        return max(0, int(capital / price))

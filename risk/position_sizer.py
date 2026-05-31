"""Phase 8 — Position Sizing Engine."""
from __future__ import annotations

import logging
import math
from abc import ABC, abstractmethod
from decimal import Decimal

from risk.portfolio_state import PortfolioStateEngine
from risk.risk_models import RiskParams, SignalInput, SizingMethod, SizingResult

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")
_ONE = Decimal("1")


class PositionSizer(ABC):
    """Abstract base for all sizing strategies."""

    @abstractmethod
    def calculate(
        self,
        signal: SignalInput,
        state: PortfolioStateEngine,
        params: RiskParams,
    ) -> SizingResult:
        ...

    # ── shared helper ──────────────────────────────────────────────────
    def _cap_to_max_position(
        self,
        raw_qty: int,
        signal: SignalInput,
        state: PortfolioStateEngine,
        params: RiskParams,
    ) -> int:
        """Reduce qty so the resulting notional ≤ max_position_pct of equity."""
        eq = state.equity
        if eq <= 0 or signal.current_price <= 0:
            return 0
        max_notional = eq * Decimal(str(params.max_position_pct / 100))
        max_qty = int(max_notional / signal.current_price)
        return min(raw_qty, max_qty)


# ──────────────────────────────────────────────────────────────────────
# 1. Fixed Fractional
# ──────────────────────────────────────────────────────────────────────

class FixedFractionalSizer(PositionSizer):
    """
    Risk a fixed fraction of equity per trade.

    qty = (equity * risk_pct) / (price * stop_distance_pct)

    If no stop_price is given, stop_distance defaults to 2 × ATR or 2% of price.
    """

    def calculate(
        self,
        signal: SignalInput,
        state: PortfolioStateEngine,
        params: RiskParams,
    ) -> SizingResult:
        equity = state.equity
        price = signal.current_price

        if equity <= 0 or price <= 0:
            return _zero_result(signal, SizingMethod.FIXED_FRACTIONAL, "zero equity or price")

        risk_amount = equity * Decimal(str(params.risk_per_trade_pct / 100))

        if signal.stop_price and signal.stop_price > 0:
            stop_dist = abs(price - signal.stop_price)
        elif signal.atr and signal.atr > 0:
            stop_dist = signal.atr * Decimal("2")
        else:
            stop_dist = price * Decimal("0.02")

        if stop_dist <= 0:
            stop_dist = price * Decimal("0.02")

        raw_qty = max(0, int(risk_amount / stop_dist))
        adj_qty = self._cap_to_max_position(raw_qty, signal, state, params)

        notional = price * adj_qty
        eq_fraction = float(notional / equity) if equity > 0 else 0.0

        return SizingResult(
            symbol=signal.symbol,
            strategy_name=signal.strategy_name,
            raw_quantity=raw_qty,
            adjusted_quantity=adj_qty,
            method=SizingMethod.FIXED_FRACTIONAL,
            notional_value=notional,
            equity_fraction=eq_fraction,
            reasoning=f"risk={risk_amount:.2f} stop_dist={stop_dist:.4f}",
        )


# ──────────────────────────────────────────────────────────────────────
# 2. Volatility-Based Sizing
# ──────────────────────────────────────────────────────────────────────

class VolatilityBasedSizer(PositionSizer):
    """
    Position size inversely proportional to ATR (volatility).

    target_volatility_contribution = equity * risk_pct
    qty = target_vol_contribution / atr
    """

    def calculate(
        self,
        signal: SignalInput,
        state: PortfolioStateEngine,
        params: RiskParams,
    ) -> SizingResult:
        equity = state.equity
        price = signal.current_price

        if equity <= 0 or price <= 0:
            return _zero_result(signal, SizingMethod.VOLATILITY_BASED, "zero equity or price")

        atr = signal.atr if signal.atr and signal.atr > 0 else price * Decimal("0.02")
        target_risk = equity * Decimal(str(params.risk_per_trade_pct / 100))
        raw_qty = max(0, int(target_risk / atr))
        adj_qty = self._cap_to_max_position(raw_qty, signal, state, params)

        notional = price * adj_qty
        eq_fraction = float(notional / equity) if equity > 0 else 0.0

        return SizingResult(
            symbol=signal.symbol,
            strategy_name=signal.strategy_name,
            raw_quantity=raw_qty,
            adjusted_quantity=adj_qty,
            method=SizingMethod.VOLATILITY_BASED,
            notional_value=notional,
            equity_fraction=eq_fraction,
            reasoning=f"atr={atr:.4f} target_risk={target_risk:.2f}",
        )


# ──────────────────────────────────────────────────────────────────────
# 3. Kelly Criterion (fractional)
# ──────────────────────────────────────────────────────────────────────

class KellySizer(PositionSizer):
    """
    Fractional Kelly sizing.

    full_kelly = (win_prob - loss_prob / odds)
    kelly_fraction applied as aggressiveness dampener.

    When win_prob is not supplied, confidence is used as proxy.
    """

    def calculate(
        self,
        signal: SignalInput,
        state: PortfolioStateEngine,
        params: RiskParams,
        win_prob: float | None = None,
        odds: float = 2.0,
    ) -> SizingResult:
        equity = state.equity
        price = signal.current_price

        if equity <= 0 or price <= 0:
            return _zero_result(signal, SizingMethod.KELLY, "zero equity or price")

        p = win_prob if win_prob is not None else signal.confidence
        p = max(0.01, min(0.99, p))
        q = 1.0 - p
        b = max(0.01, odds)

        full_kelly = (p - q / b)
        full_kelly = max(0.0, full_kelly)

        fractional_kelly = full_kelly * params.kelly_fraction
        kelly_capital = equity * Decimal(str(fractional_kelly))
        raw_qty = max(0, int(kelly_capital / price))
        adj_qty = self._cap_to_max_position(raw_qty, signal, state, params)

        notional = price * adj_qty
        eq_fraction = float(notional / equity) if equity > 0 else 0.0

        return SizingResult(
            symbol=signal.symbol,
            strategy_name=signal.strategy_name,
            raw_quantity=raw_qty,
            adjusted_quantity=adj_qty,
            method=SizingMethod.KELLY,
            notional_value=notional,
            equity_fraction=eq_fraction,
            reasoning=f"full_kelly={full_kelly:.4f} fraction={params.kelly_fraction} p={p:.2f}",
        )


# ──────────────────────────────────────────────────────────────────────
# 4. Confidence-Scaled Sizing
# ──────────────────────────────────────────────────────────────────────

class ConfidenceScaledSizer(PositionSizer):
    """
    Base quantity scaled by confidence × regime_strength.

    base_qty = equity * max_position_pct / price
    final_qty = base_qty * confidence * regime_strength
    """

    def calculate(
        self,
        signal: SignalInput,
        state: PortfolioStateEngine,
        params: RiskParams,
    ) -> SizingResult:
        equity = state.equity
        price = signal.current_price

        if equity <= 0 or price <= 0:
            return _zero_result(signal, SizingMethod.CONFIDENCE_SCALED, "zero equity or price")

        max_notional = equity * Decimal(str(params.max_position_pct / 100))
        base_qty = int(max_notional / price)
        scale = signal.confidence * signal.regime_strength
        scale = max(0.0, min(1.0, scale))
        raw_qty = max(0, int(base_qty * scale))
        adj_qty = self._cap_to_max_position(raw_qty, signal, state, params)

        notional = price * adj_qty
        eq_fraction = float(notional / equity) if equity > 0 else 0.0

        return SizingResult(
            symbol=signal.symbol,
            strategy_name=signal.strategy_name,
            raw_quantity=raw_qty,
            adjusted_quantity=adj_qty,
            method=SizingMethod.CONFIDENCE_SCALED,
            notional_value=notional,
            equity_fraction=eq_fraction,
            reasoning=f"confidence={signal.confidence:.2f} regime_strength={signal.regime_strength:.2f} scale={scale:.4f}",
        )


# ──────────────────────────────────────────────────────────────────────
# Factory / dispatcher
# ──────────────────────────────────────────────────────────────────────

def calculate_position_size(
    signal: SignalInput,
    state: PortfolioStateEngine,
    params: RiskParams,
) -> SizingResult:
    """Route to the correct sizer based on params.sizing_method."""
    sizer: PositionSizer
    if params.sizing_method == SizingMethod.FIXED_FRACTIONAL:
        sizer = FixedFractionalSizer()
    elif params.sizing_method == SizingMethod.VOLATILITY_BASED:
        sizer = VolatilityBasedSizer()
    elif params.sizing_method == SizingMethod.KELLY:
        sizer = KellySizer()
    elif params.sizing_method == SizingMethod.CONFIDENCE_SCALED:
        sizer = ConfidenceScaledSizer()
    else:
        sizer = FixedFractionalSizer()

    result = sizer.calculate(signal, state, params)
    logger.debug(
        "sizing %s method=%s qty=%d  %s",
        signal.symbol, params.sizing_method, result.adjusted_quantity, result.reasoning,
    )
    return result


# ──────────────────────────────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────────────────────────────

def _zero_result(signal: SignalInput, method: SizingMethod, reason: str) -> SizingResult:
    return SizingResult(
        symbol=signal.symbol,
        strategy_name=signal.strategy_name,
        raw_quantity=0,
        adjusted_quantity=0,
        method=method,
        notional_value=Decimal("0"),
        equity_fraction=0.0,
        reasoning=reason,
    )

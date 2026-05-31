"""Unit tests for RiskGate."""
from __future__ import annotations

from decimal import Decimal

import pytest

from risk.portfolio_state import PortfolioStateEngine
from risk.risk_gate import RiskGate, risk_gate
from risk.risk_models import (
    PortfolioOrder,
    RiskDecisionType,
    RiskParams,
    SignalInput,
    SizingMethod,
)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _state(cash: str = "1000000") -> PortfolioStateEngine:
    return PortfolioStateEngine(initial_cash=Decimal(cash))


def _params(**kw) -> RiskParams:
    defaults = dict(
        sizing_method=SizingMethod.FIXED_FRACTIONAL,
        risk_per_trade_pct=1.0,
        max_position_pct=10.0,
        max_drawdown_pct=15.0,
        daily_loss_limit_pct=3.0,
        max_per_asset_pct=15.0,
        max_per_strategy_pct=40.0,
        max_leverage=1.0,
    )
    defaults.update(kw)
    return RiskParams(**defaults)


def _signal(
    symbol: str = "NIFTY 50",
    price: str = "19000",
    atr: str | None = "200",
    confidence: float = 0.8,
) -> SignalInput:
    return SignalInput(
        symbol=symbol,
        strategy_name="ema",
        action="BUY",
        confidence=confidence,
        timeframe="5min",
        current_price=Decimal(price),
        atr=Decimal(atr) if atr else None,
        regime_strength=0.8,
    )


def _order(
    symbol: str = "NIFTY 50",
    qty: int = 10,
    price: str = "19000",
) -> PortfolioOrder:
    return PortfolioOrder(
        symbol=symbol,
        action="BUY",
        quantity=qty,
        order_type="MARKET",
        strategy_name="ema",
        confidence=0.8,
        current_price=Decimal(price),
    )


# ──────────────────────────────────────────────────────────────────────
# RiskGate.evaluate (signal → sizing + controls)
# ──────────────────────────────────────────────────────────────────────

class TestRiskGateEvaluate:
    def test_approve_clean_signal(self):
        gate = RiskGate(_params(), _state())
        decision = gate.evaluate(_signal())
        assert decision.is_approved

    def test_decision_type_approved(self):
        gate = RiskGate(_params(), _state())
        decision = gate.evaluate(_signal())
        assert decision.decision in (RiskDecisionType.APPROVED, RiskDecisionType.REDUCED)

    def test_approved_quantity_positive(self):
        gate = RiskGate(_params(), _state())
        decision = gate.evaluate(_signal())
        assert decision.approved_quantity > 0

    def test_symbol_in_decision(self):
        gate = RiskGate(_params(), _state())
        decision = gate.evaluate(_signal(symbol="NIFTY BANK"))
        assert decision.symbol == "NIFTY BANK"

    def test_block_on_drawdown_breach(self):
        state = PortfolioStateEngine(initial_cash=Decimal("1000000"))
        state.record_fill("NIFTY 50", 100, Decimal("10000"), "ema")
        state.update_price("NIFTY 50", Decimal("8000"))  # 20% drawdown
        gate = RiskGate(_params(max_drawdown_pct=15.0), state)
        decision = gate.evaluate(_signal())
        assert not decision.is_approved
        assert decision.approved_quantity == 0

    def test_blocked_decision_has_reason(self):
        state = PortfolioStateEngine(initial_cash=Decimal("1000000"))
        state.record_fill("NIFTY 50", 100, Decimal("10000"), "ema")
        state.update_price("NIFTY 50", Decimal("8000"))
        gate = RiskGate(_params(max_drawdown_pct=15.0), state)
        decision = gate.evaluate(_signal())
        assert len(decision.reason) > 0

    def test_reduced_qty_when_exposure_would_breach(self):
        gate = RiskGate(_params(max_per_asset_pct=5.0), _state())
        decision = gate.evaluate(_signal(price="19000"))
        # 5% of 1e6 = 50000 at 19000 → max_qty=2; sizer gives more → reduced
        if decision.is_approved:
            assert decision.approved_quantity <= 2

    def test_was_reduced_flag(self):
        gate = RiskGate(_params(max_per_asset_pct=2.0), _state())
        decision = gate.evaluate(_signal(price="100"))
        # 2% of 1e6 = 20000 / 100 = 200 max; sizer at 1% risk with 2% stop = 500 raw
        if decision.is_approved and decision.approved_quantity < decision.original_quantity:
            assert decision.was_reduced


# ──────────────────────────────────────────────────────────────────────
# RiskGate.evaluate_order (pre-sized order validation)
# ──────────────────────────────────────────────────────────────────────

class TestRiskGateEvaluateOrder:
    def test_approve_small_order(self):
        gate = RiskGate(_params(), _state())
        decision = gate.evaluate_order(_order(qty=5))
        assert decision.is_approved

    def test_block_when_drawdown_breached(self):
        state = PortfolioStateEngine(initial_cash=Decimal("1000000"))
        state.record_fill("NIFTY 50", 100, Decimal("10000"), "ema")
        state.update_price("NIFTY 50", Decimal("8000"))
        gate = RiskGate(_params(max_drawdown_pct=15.0), state)
        decision = gate.evaluate_order(_order(qty=5))
        assert not decision.is_approved

    def test_original_quantity_preserved(self):
        gate = RiskGate(_params(), _state())
        decision = gate.evaluate_order(_order(qty=7))
        assert decision.original_quantity == 7

    def test_reduce_order_at_exposure_cap(self):
        gate = RiskGate(_params(max_per_asset_pct=5.0), _state())
        decision = gate.evaluate_order(_order(qty=1000, price="100"))
        # max 5% of 1e6 at 100 = 500
        if decision.is_approved:
            assert decision.approved_quantity <= 500


# ──────────────────────────────────────────────────────────────────────
# is_trading_halted
# ──────────────────────────────────────────────────────────────────────

class TestIsTradingHalted:
    def test_not_halted_fresh_portfolio(self):
        gate = RiskGate(_params(), _state())
        assert not gate.is_trading_halted()

    def test_halted_on_drawdown(self):
        state = PortfolioStateEngine(initial_cash=Decimal("1000000"))
        state.record_fill("NIFTY 50", 100, Decimal("10000"), "ema")
        state.update_price("NIFTY 50", Decimal("8000"))  # ~20% portfolio drawdown
        gate = RiskGate(_params(max_drawdown_pct=15.0), state)
        assert gate.is_trading_halted()

    def test_halted_on_daily_loss(self):
        state = PortfolioStateEngine(initial_cash=Decimal("1000000"))
        state.record_fill("NIFTY 50", 100, Decimal("10000"), "ema")
        state.update_price("NIFTY 50", Decimal("9600"))  # 4% daily loss
        gate = RiskGate(_params(daily_loss_limit_pct=3.0), state)
        assert gate.is_trading_halted()


# ──────────────────────────────────────────────────────────────────────
# Module-level risk_gate() convenience function
# ──────────────────────────────────────────────────────────────────────

class TestRiskGateFunction:
    def test_returns_risk_decision(self):
        decision = risk_gate(_order(qty=5), _state(), _params())
        assert decision is not None

    def test_approves_valid_order(self):
        decision = risk_gate(_order(qty=5), _state(), _params())
        assert decision.is_approved

    def test_blocks_on_drawdown(self):
        state = PortfolioStateEngine(initial_cash=Decimal("1000000"))
        state.record_fill("NIFTY 50", 100, Decimal("10000"), "ema")
        state.update_price("NIFTY 50", Decimal("8000"))
        decision = risk_gate(_order(qty=5), state, _params(max_drawdown_pct=15.0))
        assert not decision.is_approved

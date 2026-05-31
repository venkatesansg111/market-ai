"""Unit tests for Position Sizing Engine."""
from __future__ import annotations

from decimal import Decimal

import pytest

from risk.portfolio_state import PortfolioStateEngine
from risk.position_sizer import (
    ConfidenceScaledSizer,
    FixedFractionalSizer,
    KellySizer,
    VolatilityBasedSizer,
    calculate_position_size,
)
from risk.risk_models import RiskParams, SignalInput, SizingMethod


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
        kelly_fraction=0.25,
    )
    defaults.update(kw)
    return RiskParams(**defaults)


def _signal(
    symbol: str = "NIFTY 50",
    price: str = "19000",
    confidence: float = 0.8,
    atr: str | None = None,
    stop_price: str | None = None,
    regime_strength: float = 0.7,
) -> SignalInput:
    return SignalInput(
        symbol=symbol,
        strategy_name="ema",
        action="BUY",
        confidence=confidence,
        timeframe="5min",
        current_price=Decimal(price),
        atr=Decimal(atr) if atr else None,
        stop_price=Decimal(stop_price) if stop_price else None,
        regime_strength=regime_strength,
    )


# ──────────────────────────────────────────────────────────────────────
# FixedFractionalSizer
# ──────────────────────────────────────────────────────────────────────

class TestFixedFractionalSizer:
    def test_returns_nonzero_quantity(self):
        s = FixedFractionalSizer()
        result = s.calculate(_signal(stop_price="18800"), _state(), _params())
        assert result.adjusted_quantity > 0

    def test_uses_stop_price_for_distance(self):
        # equity=1e6, risk=1%, stop_dist=200 → qty = 10000/200 = 50
        s = FixedFractionalSizer()
        result = s.calculate(_signal(price="19000", stop_price="18800"), _state(), _params(risk_per_trade_pct=1.0))
        assert result.raw_quantity == 50

    def test_uses_atr_when_no_stop(self):
        # equity=1e6, risk=1%=10000, atr=100, stop=2*atr=200 → qty=50
        s = FixedFractionalSizer()
        result = s.calculate(_signal(price="19000", atr="100"), _state(), _params())
        assert result.raw_quantity == 50

    def test_defaults_to_2pct_price_when_no_atr_no_stop(self):
        # stop_dist=19000*0.02=380 → qty=10000/380 = 26
        s = FixedFractionalSizer()
        result = s.calculate(_signal(price="19000"), _state(), _params())
        assert result.raw_quantity == 26

    def test_qty_capped_by_max_position_pct(self):
        # max_position=10% of 1e6=100000, price=19000 → max_qty=5
        s = FixedFractionalSizer()
        result = s.calculate(_signal(price="19000", stop_price="18000"), _state(), _params(max_position_pct=10.0))
        assert result.adjusted_quantity <= 5

    def test_adjusted_lte_raw(self):
        s = FixedFractionalSizer()
        result = s.calculate(_signal(stop_price="1"), _state(), _params())
        assert result.adjusted_quantity <= result.raw_quantity

    def test_zero_equity_returns_zero(self):
        state = _state("0")
        s = FixedFractionalSizer()
        result = s.calculate(_signal(), state, _params())
        assert result.adjusted_quantity == 0

    def test_result_method_is_fixed_fractional(self):
        s = FixedFractionalSizer()
        result = s.calculate(_signal(), _state(), _params())
        assert result.method == SizingMethod.FIXED_FRACTIONAL

    def test_notional_value_matches_qty_times_price(self):
        s = FixedFractionalSizer()
        sig = _signal(price="19000", stop_price="18800")
        result = s.calculate(sig, _state(), _params())
        assert result.notional_value == Decimal("19000") * result.adjusted_quantity

    def test_equity_fraction_is_float(self):
        s = FixedFractionalSizer()
        result = s.calculate(_signal(), _state(), _params())
        assert isinstance(result.equity_fraction, float)


# ──────────────────────────────────────────────────────────────────────
# VolatilityBasedSizer
# ──────────────────────────────────────────────────────────────────────

class TestVolatilityBasedSizer:
    def test_returns_nonzero_quantity(self):
        s = VolatilityBasedSizer()
        result = s.calculate(_signal(price="19000", atr="100"), _state(), _params())
        assert result.adjusted_quantity > 0

    def test_higher_atr_gives_lower_qty(self):
        s = VolatilityBasedSizer()
        # Compare raw_quantity — before the max_position cap clips both to the same value
        low_atr = s.calculate(_signal(price="19000", atr="50"), _state(), _params())
        high_atr = s.calculate(_signal(price="19000", atr="200"), _state(), _params())
        assert low_atr.raw_quantity > high_atr.raw_quantity

    def test_method_is_volatility_based(self):
        s = VolatilityBasedSizer()
        result = s.calculate(_signal(atr="100"), _state(), _params())
        assert result.method == SizingMethod.VOLATILITY_BASED

    def test_falls_back_to_2pct_when_no_atr(self):
        s = VolatilityBasedSizer()
        result = s.calculate(_signal(price="10000"), _state(), _params())
        # fallback atr = 10000 * 0.02 = 200; qty = 10000/200 = 50
        assert result.raw_quantity == 50

    def test_capped_by_max_position(self):
        s = VolatilityBasedSizer()
        result = s.calculate(_signal(price="19000", atr="1"), _state(), _params(max_position_pct=5.0))
        max_qty = int(Decimal("1000000") * Decimal("0.05") / Decimal("19000"))
        assert result.adjusted_quantity <= max_qty


# ──────────────────────────────────────────────────────────────────────
# KellySizer
# ──────────────────────────────────────────────────────────────────────

class TestKellySizer:
    def test_returns_nonzero_quantity(self):
        s = KellySizer()
        result = s.calculate(_signal(), _state(), _params())
        assert result.adjusted_quantity > 0

    def test_method_is_kelly(self):
        s = KellySizer()
        result = s.calculate(_signal(), _state(), _params())
        assert result.method == SizingMethod.KELLY

    def test_higher_confidence_gives_larger_qty(self):
        s = KellySizer()
        low = s.calculate(_signal(confidence=0.4), _state(), _params())
        high = s.calculate(_signal(confidence=0.9), _state(), _params())
        assert high.adjusted_quantity >= low.adjusted_quantity

    def test_zero_win_prob_gives_zero(self):
        s = KellySizer()
        result = s.calculate(_signal(confidence=0.0), _state(), _params())
        assert result.adjusted_quantity == 0

    def test_kelly_fraction_scales_quantity(self):
        s = KellySizer()
        full = s.calculate(_signal(confidence=0.7), _state(), _params(kelly_fraction=1.0))
        quarter = s.calculate(_signal(confidence=0.7), _state(), _params(kelly_fraction=0.25))
        assert full.raw_quantity >= quarter.raw_quantity

    def test_explicit_win_prob_overrides_confidence(self):
        s = KellySizer()
        using_confidence = s.calculate(_signal(confidence=0.6), _state(), _params())
        using_win_prob = s.calculate(_signal(confidence=0.9), _state(), _params(), win_prob=0.6)
        assert using_confidence.raw_quantity == using_win_prob.raw_quantity


# ──────────────────────────────────────────────────────────────────────
# ConfidenceScaledSizer
# ──────────────────────────────────────────────────────────────────────

class TestConfidenceScaledSizer:
    def test_method_is_confidence_scaled(self):
        s = ConfidenceScaledSizer()
        result = s.calculate(_signal(), _state(), _params())
        assert result.method == SizingMethod.CONFIDENCE_SCALED

    def test_full_confidence_regime_one_gives_max_qty(self):
        s = ConfidenceScaledSizer()
        result = s.calculate(_signal(confidence=1.0, regime_strength=1.0), _state(), _params(max_position_pct=10.0))
        expected_max = int(Decimal("1000000") * Decimal("0.10") / Decimal("19000"))
        assert result.adjusted_quantity == expected_max

    def test_zero_confidence_gives_zero(self):
        s = ConfidenceScaledSizer()
        result = s.calculate(_signal(confidence=0.0), _state(), _params())
        assert result.adjusted_quantity == 0

    def test_confidence_regime_scale(self):
        s = ConfidenceScaledSizer()
        high = s.calculate(_signal(confidence=1.0, regime_strength=1.0), _state(), _params())
        low = s.calculate(_signal(confidence=0.5, regime_strength=0.5), _state(), _params())
        assert high.adjusted_quantity > low.adjusted_quantity


# ──────────────────────────────────────────────────────────────────────
# calculate_position_size factory
# ──────────────────────────────────────────────────────────────────────

class TestCalculatePositionSizeFactory:
    def test_dispatches_fixed_fractional(self):
        result = calculate_position_size(_signal(), _state(), _params(sizing_method=SizingMethod.FIXED_FRACTIONAL))
        assert result.method == SizingMethod.FIXED_FRACTIONAL

    def test_dispatches_volatility_based(self):
        result = calculate_position_size(_signal(atr="100"), _state(), _params(sizing_method=SizingMethod.VOLATILITY_BASED))
        assert result.method == SizingMethod.VOLATILITY_BASED

    def test_dispatches_kelly(self):
        result = calculate_position_size(_signal(), _state(), _params(sizing_method=SizingMethod.KELLY))
        assert result.method == SizingMethod.KELLY

    def test_dispatches_confidence_scaled(self):
        result = calculate_position_size(_signal(), _state(), _params(sizing_method=SizingMethod.CONFIDENCE_SCALED))
        assert result.method == SizingMethod.CONFIDENCE_SCALED

    def test_symbol_in_result(self):
        result = calculate_position_size(_signal(symbol="NIFTY BANK"), _state(), _params())
        assert result.symbol == "NIFTY BANK"

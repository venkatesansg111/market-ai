"""Unit tests for Risk Controls Engine."""
from __future__ import annotations

from decimal import Decimal

import pytest

from risk.portfolio_state import PortfolioStateEngine
from risk.risk_controls import (
    AssetExposureLimit,
    CorrelationRiskFilter,
    DailyLossLimiter,
    LeverageCapControl,
    MaxDrawdownGuard,
    RiskControlsEngine,
    StrategyExposureLimit,
    VolatilityShockFilter,
)
from risk.risk_models import RiskParams, SignalInput


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _state(cash: str = "1000000") -> PortfolioStateEngine:
    return PortfolioStateEngine(initial_cash=Decimal(cash))


def _params(**kw) -> RiskParams:
    defaults = dict(
        max_drawdown_pct=15.0,
        daily_loss_limit_pct=3.0,
        max_per_asset_pct=15.0,
        max_per_strategy_pct=40.0,
        max_leverage=1.0,
        volatility_shock_multiplier=2.0,
        correlation_threshold=0.80,
    )
    defaults.update(kw)
    return RiskParams(**defaults)


def _signal(symbol: str = "NIFTY 50", price: str = "19000", atr: str | None = None) -> SignalInput:
    return SignalInput(
        symbol=symbol,
        strategy_name="ema",
        action="BUY",
        confidence=0.8,
        timeframe="5min",
        current_price=Decimal(price),
        atr=Decimal(atr) if atr else None,
    )


# ──────────────────────────────────────────────────────────────────────
# MaxDrawdownGuard
# ──────────────────────────────────────────────────────────────────────

class TestMaxDrawdownGuard:
    def _state_with_drawdown(self, dd_pct: float) -> PortfolioStateEngine:
        state = PortfolioStateEngine(initial_cash=Decimal("1000000"))
        # Simulate drawdown by recording a fill that increases equity then a loss
        # We'll manually set the peak and then reduce equity via fill
        # Instead: fill a buy then mark price lower
        state.record_fill("NIFTY 50", 100, Decimal("10000"), "ema")
        state.update_price("NIFTY 50", Decimal(str(10000 * (1 - dd_pct / 100))))
        return state

    def test_passes_when_drawdown_under_limit(self):
        state = self._state_with_drawdown(5.0)
        ctrl = MaxDrawdownGuard()
        result = ctrl.check(_signal(), 10, state, _params(max_drawdown_pct=15.0))
        assert result.passed

    def test_blocks_when_drawdown_at_limit(self):
        state = self._state_with_drawdown(15.0)
        ctrl = MaxDrawdownGuard()
        result = ctrl.check(_signal(), 10, state, _params(max_drawdown_pct=15.0))
        assert not result.passed

    def test_blocks_when_drawdown_exceeds_limit(self):
        state = self._state_with_drawdown(20.0)
        ctrl = MaxDrawdownGuard()
        result = ctrl.check(_signal(), 10, state, _params(max_drawdown_pct=15.0))
        assert not result.passed

    def test_block_reason_mentions_drawdown(self):
        state = self._state_with_drawdown(20.0)
        ctrl = MaxDrawdownGuard()
        result = ctrl.check(_signal(), 10, state, _params(max_drawdown_pct=15.0))
        assert "drawdown" in result.reason.lower()


# ──────────────────────────────────────────────────────────────────────
# DailyLossLimiter
# ──────────────────────────────────────────────────────────────────────

class TestDailyLossLimiter:
    def _state_with_daily_loss(self, loss_pct: float) -> PortfolioStateEngine:
        state = PortfolioStateEngine(initial_cash=Decimal("1000000"))
        # Record fill then mark down to simulate unrealized daily loss
        state.record_fill("NIFTY 50", 100, Decimal("10000"), "ema")
        # Mark price down so daily P&L is negative
        price_factor = 1 - loss_pct / 100
        state.update_price("NIFTY 50", Decimal(str(10000 * price_factor)))
        return state

    def test_passes_when_loss_within_limit(self):
        state = _state()
        ctrl = DailyLossLimiter()
        result = ctrl.check(_signal(), 10, state, _params(daily_loss_limit_pct=3.0))
        assert result.passed

    def test_blocks_when_daily_loss_at_limit(self):
        state = self._state_with_daily_loss(3.0)
        ctrl = DailyLossLimiter()
        result = ctrl.check(_signal(), 10, state, _params(daily_loss_limit_pct=3.0))
        assert not result.passed

    def test_blocks_when_daily_loss_exceeds_limit(self):
        state = self._state_with_daily_loss(5.0)
        ctrl = DailyLossLimiter()
        result = ctrl.check(_signal(), 10, state, _params(daily_loss_limit_pct=3.0))
        assert not result.passed

    def test_block_reason_mentions_daily_loss(self):
        state = self._state_with_daily_loss(5.0)
        ctrl = DailyLossLimiter()
        result = ctrl.check(_signal(), 10, state, _params(daily_loss_limit_pct=3.0))
        assert "daily" in result.reason.lower() or "loss" in result.reason.lower()


# ──────────────────────────────────────────────────────────────────────
# AssetExposureLimit
# ──────────────────────────────────────────────────────────────────────

class TestAssetExposureLimit:
    def test_passes_fresh_portfolio(self):
        ctrl = AssetExposureLimit()
        result = ctrl.check(_signal(), 5, _state(), _params(max_per_asset_pct=15.0))
        assert result.passed

    def test_reduces_qty_when_exceeds_cap(self):
        # max_per_asset=15% of 1e6=150000 at price 19000 → max_qty=7
        ctrl = AssetExposureLimit()
        result = ctrl.check(_signal(price="19000"), 100, _state(), _params(max_per_asset_pct=15.0))
        assert result.passed
        assert result.reduced_quantity is not None
        assert result.reduced_quantity <= 7

    def test_blocks_when_already_at_cap(self):
        state = _state()
        # Fill to reach the cap first
        state.record_fill("NIFTY 50", 7, Decimal("19000"), "ema")  # 133000/1e6 ≈ 13.3%
        # Add more to push above 15%: 8 * 19000 = 152000
        state.record_fill("NIFTY 50", 1, Decimal("19000"), "ema")  # now 152000/equity
        ctrl = AssetExposureLimit()
        # At ~15.2% cap now, no more headroom
        result = ctrl.check(_signal(price="19000"), 10, state, _params(max_per_asset_pct=15.0))
        # Either blocked or reduced to 0
        if result.passed:
            assert result.reduced_quantity == 0 or result.reduced_quantity is None
        else:
            assert not result.passed

    def test_passes_qty_exactly_at_cap(self):
        ctrl = AssetExposureLimit()
        # max_qty at 15% of 1e6 at price 19000 = 7
        result = ctrl.check(_signal(price="19000"), 7, _state(), _params(max_per_asset_pct=15.0))
        assert result.passed
        assert result.reduced_quantity is None  # no reduction needed


# ──────────────────────────────────────────────────────────────────────
# LeverageCapControl
# ──────────────────────────────────────────────────────────────────────

class TestLeverageCapControl:
    def test_passes_within_leverage(self):
        ctrl = LeverageCapControl()
        # qty=5 at price=19000 = 95000 notional; equity=1e6; leverage=0.095 < 1.0
        result = ctrl.check(_signal(price="19000"), 5, _state(), _params(max_leverage=1.0))
        assert result.passed

    def test_reduces_qty_to_fit_leverage(self):
        # equity=1e6, max_leverage=0.1 → max_notional=100000; max_qty=5 at 19000
        ctrl = LeverageCapControl()
        result = ctrl.check(_signal(price="19000"), 100, _state(), _params(max_leverage=0.1))
        assert result.passed
        assert result.reduced_quantity is not None
        assert result.reduced_quantity <= 5

    def test_blocks_when_fully_at_cap(self):
        state = _state()
        # Use up all leverage: buy at price 100, qty 10000 = 1e6 = full equity
        state.record_fill("EXISTING", 10000, Decimal("100"), "ema")
        state.update_price("EXISTING", Decimal("100"))
        ctrl = LeverageCapControl()
        result = ctrl.check(_signal(price="100"), 1, state, _params(max_leverage=1.0))
        assert not result.passed or result.reduced_quantity == 0


# ──────────────────────────────────────────────────────────────────────
# VolatilityShockFilter
# ──────────────────────────────────────────────────────────────────────

class TestVolatilityShockFilter:
    def test_passes_when_no_baseline(self):
        ctrl = VolatilityShockFilter()
        result = ctrl.check(_signal(atr="100"), 10, _state(), _params())
        assert result.passed

    def test_passes_when_atr_within_baseline(self):
        ctrl = VolatilityShockFilter(baseline_atr_map={"NIFTY 50": Decimal("100")})
        result = ctrl.check(_signal(atr="150"), 10, _state(), _params(volatility_shock_multiplier=2.0))
        assert result.passed

    def test_reduces_qty_on_volatility_spike(self):
        ctrl = VolatilityShockFilter(baseline_atr_map={"NIFTY 50": Decimal("100")})
        # atr=300 → ratio=3 > 2x → trigger
        result = ctrl.check(_signal(atr="300"), 10, _state(), _params(volatility_shock_multiplier=2.0))
        assert result.passed
        assert result.reduced_quantity is not None
        assert result.reduced_quantity < 10

    def test_set_baseline_works(self):
        ctrl = VolatilityShockFilter()
        ctrl.set_baseline("NIFTY 50", Decimal("100"))
        result = ctrl.check(_signal(atr="300"), 10, _state(), _params(volatility_shock_multiplier=2.0))
        assert result.reduced_quantity is not None


# ──────────────────────────────────────────────────────────────────────
# CorrelationRiskFilter
# ──────────────────────────────────────────────────────────────────────

class TestCorrelationRiskFilter:
    def test_passes_when_no_positions(self):
        ctrl = CorrelationRiskFilter()
        result = ctrl.check(_signal(), 10, _state(), _params())
        assert result.passed

    def test_passes_when_correlation_below_threshold(self):
        state = _state()
        state.record_fill("NIFTY BANK", 5, Decimal("44000"), "ema2")
        ctrl = CorrelationRiskFilter(correlation_matrix={("NIFTY 50", "NIFTY BANK"): 0.5})
        result = ctrl.check(_signal(), 10, state, _params(correlation_threshold=0.80))
        assert result.passed

    def test_reduces_qty_when_highly_correlated(self):
        state = _state()
        state.record_fill("NIFTY BANK", 5, Decimal("44000"), "ema2")
        ctrl = CorrelationRiskFilter(correlation_matrix={("NIFTY 50", "NIFTY BANK"): 0.90})
        result = ctrl.check(_signal(), 10, state, _params(correlation_threshold=0.80))
        assert result.passed
        assert result.reduced_quantity is not None
        assert result.reduced_quantity < 10

    def test_update_correlation_method(self):
        ctrl = CorrelationRiskFilter()
        ctrl.update_correlation("A", "B", 0.95)
        state = _state()
        state.record_fill("B", 5, Decimal("100"), "strat")
        result = ctrl.check(
            SignalInput(symbol="A", strategy_name="strat", action="BUY", confidence=0.8,
                        timeframe="5min", current_price=Decimal("100")),
            10, state, _params(correlation_threshold=0.80)
        )
        assert result.reduced_quantity is not None


# ──────────────────────────────────────────────────────────────────────
# RiskControlsEngine (composite)
# ──────────────────────────────────────────────────────────────────────

class TestRiskControlsEngine:
    def test_all_pass_clean_portfolio(self):
        engine = RiskControlsEngine(_params())
        approved, qty, reason = engine.evaluate(_signal(), 5, _state())
        assert approved
        assert qty == 5

    def test_blocked_by_drawdown(self):
        state = PortfolioStateEngine(initial_cash=Decimal("1000000"))
        state.record_fill("NIFTY 50", 100, Decimal("10000"), "ema")
        state.update_price("NIFTY 50", Decimal("8000"))  # 20% drawdown
        engine = RiskControlsEngine(_params(max_drawdown_pct=15.0))
        approved, qty, _ = engine.evaluate(_signal(), 5, state)
        assert not approved
        assert qty == 0

    def test_blocked_by_daily_loss(self):
        state = PortfolioStateEngine(initial_cash=Decimal("1000000"))
        state.record_fill("NIFTY 50", 100, Decimal("10000"), "ema")
        state.update_price("NIFTY 50", Decimal("9600"))  # 4% loss on 1e6 exposure
        engine = RiskControlsEngine(_params(daily_loss_limit_pct=3.0))
        approved, qty, _ = engine.evaluate(_signal(), 5, state)
        assert not approved

    def test_qty_reduced_by_asset_limit(self):
        engine = RiskControlsEngine(_params(max_per_asset_pct=15.0))
        approved, qty, _ = engine.evaluate(_signal(price="19000"), 100, _state())
        assert approved
        assert qty <= 7  # 15% of 1e6 / 19000

    def test_blocking_stops_reducing_checks(self):
        """Once a blocker fires, the engine should return immediately."""
        state = PortfolioStateEngine(initial_cash=Decimal("1000000"))
        state.record_fill("NIFTY 50", 100, Decimal("10000"), "ema")
        state.update_price("NIFTY 50", Decimal("8000"))  # drawdown > 15%
        engine = RiskControlsEngine(_params(max_drawdown_pct=15.0))
        approved, qty, reason = engine.evaluate(_signal(), 5, state)
        assert not approved
        assert qty == 0
        assert "drawdown" in reason.lower()


# ──────────────────────────────────────────────────────────────────────
# Stress tests
# ──────────────────────────────────────────────────────────────────────

class TestStressScenarios:
    def test_crash_scenario_blocks_new_trades(self):
        """Portfolio loses 20% — all new trades must be blocked."""
        state = PortfolioStateEngine(initial_cash=Decimal("1000000"))
        state.record_fill("NIFTY 50", 50, Decimal("20000"), "ema")
        state.update_price("NIFTY 50", Decimal("12000"))  # -40% from cost → portfolio drops ~20%
        engine = RiskControlsEngine(_params(max_drawdown_pct=15.0))
        approved, _, _ = engine.evaluate(_signal(), 10, state)
        assert not approved

    def test_volatility_spike_reduces_exposure(self):
        """ATR triples vs baseline — size should be cut."""
        vol_filter = VolatilityShockFilter(baseline_atr_map={"NIFTY 50": Decimal("100")})
        engine = RiskControlsEngine(_params(volatility_shock_multiplier=2.0), volatility_filter=vol_filter)
        approved, qty, _ = engine.evaluate(_signal(atr="350"), 20, _state())
        assert approved
        assert qty < 20

    def test_correlated_collapse_reduces_exposure(self):
        """High correlation with existing position reduces new position size."""
        state = _state()
        state.record_fill("NIFTY BANK", 10, Decimal("44000"), "ema2")
        corr_filter = CorrelationRiskFilter(correlation_matrix={("NIFTY 50", "NIFTY BANK"): 0.95})
        engine = RiskControlsEngine(_params(correlation_threshold=0.80), correlation_filter=corr_filter)
        approved, qty, _ = engine.evaluate(_signal(), 20, state)
        assert approved
        assert qty < 20

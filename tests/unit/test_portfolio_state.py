"""Unit tests for PortfolioStateEngine."""
from __future__ import annotations

from decimal import Decimal
from datetime import date

import pytest

from risk.portfolio_state import PortfolioStateEngine


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _state(cash: str = "1000000") -> PortfolioStateEngine:
    return PortfolioStateEngine(initial_cash=Decimal(cash))


# ──────────────────────────────────────────────────────────────────────
# Initial state
# ──────────────────────────────────────────────────────────────────────

class TestInitialState:
    def test_initial_cash(self):
        state = _state("500000")
        assert state.cash == Decimal("500000")

    def test_initial_equity_equals_cash(self):
        state = _state("1000000")
        assert state.equity == Decimal("1000000")

    def test_no_positions(self):
        state = _state()
        assert state.positions == {}

    def test_drawdown_is_zero(self):
        state = _state()
        assert state.current_drawdown_pct == 0.0

    def test_daily_pnl_is_zero(self):
        state = _state()
        assert state.daily_pnl == Decimal("0")


# ──────────────────────────────────────────────────────────────────────
# record_fill
# ──────────────────────────────────────────────────────────────────────

class TestRecordFill:
    def test_buy_reduces_cash(self):
        state = _state()
        state.record_fill("NIFTY 50", 10, Decimal("19000"), "ema")
        assert state.cash == Decimal("1000000") - Decimal("190000")

    def test_buy_creates_position(self):
        state = _state()
        state.record_fill("NIFTY 50", 10, Decimal("19000"), "ema")
        assert "NIFTY 50" in state.positions
        qty, _ = state.positions["NIFTY 50"]
        assert qty == 10

    def test_sell_increases_cash(self):
        state = _state()
        state.record_fill("NIFTY 50", 10, Decimal("19000"), "ema")
        state.record_fill("NIFTY 50", -10, Decimal("20000"), "ema")
        assert state.cash == Decimal("1000000") - Decimal("190000") + Decimal("200000")

    def test_full_close_removes_position(self):
        state = _state()
        state.record_fill("NIFTY 50", 10, Decimal("19000"), "ema")
        state.record_fill("NIFTY 50", -10, Decimal("19000"), "ema")
        assert "NIFTY 50" not in state.positions

    def test_partial_close_reduces_qty(self):
        state = _state()
        state.record_fill("NIFTY 50", 10, Decimal("100"), "ema")
        state.record_fill("NIFTY 50", -4, Decimal("100"), "ema")
        qty, _ = state.positions["NIFTY 50"]
        assert qty == 6

    def test_realized_pnl_on_close(self):
        state = _state()
        state.record_fill("NIFTY 50", 10, Decimal("100"), "ema")
        state.record_fill("NIFTY 50", -10, Decimal("120"), "ema")
        assert state.realized_pnl_total == Decimal("200")  # 10 * 20

    def test_realized_pnl_partial_close(self):
        state = _state()
        state.record_fill("NIFTY 50", 10, Decimal("100"), "ema")
        state.record_fill("NIFTY 50", -5, Decimal("120"), "ema")
        assert state.realized_pnl_total == Decimal("100")  # 5 * 20

    def test_commission_deducted_on_buy(self):
        state = _state()
        state.record_fill("NIFTY 50", 10, Decimal("100"), "ema", commission=Decimal("10"))
        assert state.cash == Decimal("1000000") - Decimal("1000") - Decimal("10")

    def test_weighted_average_price_on_add(self):
        state = _state()
        state.record_fill("NIFTY 50", 10, Decimal("100"), "ema")
        state.record_fill("NIFTY 50", 10, Decimal("200"), "ema")
        _, avg = state.positions["NIFTY 50"]
        assert avg == Decimal("150")


# ──────────────────────────────────────────────────────────────────────
# Equity and mark-to-market
# ──────────────────────────────────────────────────────────────────────

class TestEquity:
    def test_equity_includes_unrealized(self):
        state = _state()
        state.record_fill("NIFTY 50", 10, Decimal("100"), "ema")
        state.update_price("NIFTY 50", Decimal("110"))
        # cash = 1e6 - 1000 = 999000; position = 10 * 110 = 1100; equity = 1000100
        assert state.equity == Decimal("1000100")

    def test_equity_with_unrealized_loss(self):
        state = _state()
        state.record_fill("NIFTY 50", 10, Decimal("100"), "ema")
        state.update_price("NIFTY 50", Decimal("90"))
        assert state.equity == Decimal("999900")

    def test_unrealized_pnl_positive(self):
        state = _state()
        state.record_fill("NIFTY 50", 10, Decimal("100"), "ema")
        state.update_price("NIFTY 50", Decimal("120"))
        assert state.unrealized_pnl == Decimal("200")

    def test_unrealized_pnl_negative(self):
        state = _state()
        state.record_fill("NIFTY 50", 10, Decimal("100"), "ema")
        state.update_price("NIFTY 50", Decimal("80"))
        assert state.unrealized_pnl == Decimal("-200")

    def test_update_prices_bulk(self):
        state = _state()
        state.record_fill("A", 10, Decimal("100"), "s")
        state.record_fill("B", 10, Decimal("200"), "s")
        state.update_prices({"A": Decimal("110"), "B": Decimal("210")})
        assert state.unrealized_pnl == Decimal("200")  # 10*10 + 10*10


# ──────────────────────────────────────────────────────────────────────
# Drawdown
# ──────────────────────────────────────────────────────────────────────

class TestDrawdown:
    def test_no_drawdown_initially(self):
        assert _state().current_drawdown_pct == 0.0

    def test_drawdown_when_equity_falls(self):
        state = _state()
        state.record_fill("NIFTY 50", 100, Decimal("10000"), "ema")
        state.update_price("NIFTY 50", Decimal("9000"))
        # initial equity 1e6, peak 1e6, now equity = 1e6 - 1000000 + 900000 = 900000
        assert state.current_drawdown_pct > 0

    def test_peak_equity_tracks_high(self):
        state = _state()
        state.record_fill("NIFTY 50", 10, Decimal("100"), "ema")
        state.update_price("NIFTY 50", Decimal("200"))  # equity rises
        peak = state.peak_equity
        state.update_price("NIFTY 50", Decimal("50"))   # equity falls
        assert state.peak_equity == peak  # peak doesn't fall


# ──────────────────────────────────────────────────────────────────────
# Exposure snapshot
# ──────────────────────────────────────────────────────────────────────

class TestExposure:
    def test_per_asset_exposure(self):
        state = _state()
        state.record_fill("NIFTY 50", 10, Decimal("100"), "ema")
        snap = state.exposure_snapshot()
        assert snap.per_asset["NIFTY 50"] == Decimal("1000")

    def test_per_strategy_exposure(self):
        state = _state()
        state.record_fill("NIFTY 50", 10, Decimal("100"), "ema")
        snap = state.exposure_snapshot()
        assert snap.per_strategy["ema"] == Decimal("1000")

    def test_gross_exposure(self):
        state = _state()
        state.record_fill("A", 10, Decimal("100"), "s1")
        state.record_fill("B", 5, Decimal("200"), "s2")
        snap = state.exposure_snapshot()
        assert snap.gross_exposure == Decimal("2000")

    def test_position_pct_of_equity(self):
        state = _state("100000")
        state.record_fill("NIFTY 50", 10, Decimal("1000"), "ema")
        pct = state.position_pct_of_equity("NIFTY 50")
        assert abs(pct - 10.0) < 0.1

    def test_gross_leverage(self):
        state = _state("100000")
        state.record_fill("NIFTY 50", 100, Decimal("1000"), "ema")
        leverage = state.gross_leverage()
        assert leverage == pytest.approx(1.0, abs=0.01)


# ──────────────────────────────────────────────────────────────────────
# Risk metrics
# ──────────────────────────────────────────────────────────────────────

class TestRiskMetrics:
    def test_returns_risk_metrics_object(self):
        from risk.risk_models import RiskMetrics
        state = _state()
        metrics = state.risk_metrics()
        assert isinstance(metrics, RiskMetrics)

    def test_equity_in_metrics(self):
        state = _state("500000")
        metrics = state.risk_metrics()
        assert metrics.equity == Decimal("500000")

    def test_drawdown_in_metrics(self):
        state = _state()
        state.record_fill("NIFTY 50", 100, Decimal("10000"), "ema")
        state.update_price("NIFTY 50", Decimal("8000"))
        metrics = state.risk_metrics()
        assert metrics.current_drawdown_pct > 0


# ──────────────────────────────────────────────────────────────────────
# reset_day
# ──────────────────────────────────────────────────────────────────────

class TestResetDay:
    def test_daily_pnl_resets_to_zero(self):
        state = _state()
        state.record_fill("NIFTY 50", 10, Decimal("100"), "ema")
        state.update_price("NIFTY 50", Decimal("110"))  # has unrealized pnl
        state.reset_day()
        # After reset, daily pnl is measured from current equity
        assert state.daily_pnl == Decimal("0")

    def test_equity_history_appended(self):
        state = _state()
        state.reset_day()
        state.reset_day()
        # History should have initial entry + 2 resets = at least 3
        assert len(state._equity_history) >= 2

"""Unit tests for observability.pnl_attribution — PnLAttribution."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from observability.pnl_attribution import PnLAttribution
from streaming.event_bus import EventBus
from streaming.event_models import FillEvent, PortfolioEvent


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

_TS = datetime(2024, 1, 15, 9, 30, 0)


def _fill(
    symbol: str = "AAPL",
    strategy: str = "momentum",
    action: str = "BUY",
    price: float = 150.0,
    qty: int = 10,
    commission: float = 0.5,
) -> FillEvent:
    return FillEvent(
        order_id="ord-1", symbol=symbol, quantity=qty,
        price=Decimal(str(price)), strategy_name=strategy,
        action=action, commission=Decimal(str(commission)),
        timestamp=_TS,
    )


def _portfolio() -> PortfolioEvent:
    return PortfolioEvent(
        equity=Decimal("100000"), cash=Decimal("98500"),
        unrealized_pnl=Decimal("0"), realized_pnl=Decimal("0"),
        daily_pnl=Decimal("0"), current_drawdown_pct=0.0,
    )


# ──────────────────────────────────────────────────────────────────────
# Basic PnL calculation
# ──────────────────────────────────────────────────────────────────────

class TestPnLCalculation:
    def test_initial_pnl_is_zero(self):
        attr = PnLAttribution()
        assert attr.total_pnl() == Decimal("0")

    def test_trade_count_zero_initially(self):
        attr = PnLAttribution()
        assert attr.trade_count() == 0

    def test_buy_then_sell_increments_trade_count(self):
        bus = EventBus()
        attr = PnLAttribution(bus)
        bus.publish(_fill(action="BUY", price=100.0))
        bus.publish(_fill(action="SELL", price=110.0))
        assert attr.trade_count() == 1

    def test_realized_pnl_positive_on_profitable_sell(self):
        bus = EventBus()
        attr = PnLAttribution(bus)
        bus.publish(_fill(action="BUY", price=100.0, commission=0.0))
        bus.publish(_fill(action="SELL", price=110.0, commission=0.0))
        assert attr.total_pnl() == Decimal("100")  # (110-100)*10

    def test_realized_pnl_negative_on_loss(self):
        bus = EventBus()
        attr = PnLAttribution(bus)
        bus.publish(_fill(action="BUY", price=100.0, commission=0.0))
        bus.publish(_fill(action="SELL", price=90.0, commission=0.0))
        assert attr.total_pnl() == Decimal("-100")

    def test_commission_deducted_from_pnl(self):
        bus = EventBus()
        attr = PnLAttribution(bus)
        bus.publish(_fill(action="BUY", price=100.0, commission=1.0))
        bus.publish(_fill(action="SELL", price=110.0, commission=1.0))
        # (110-100)*10 - 1.0 - 1.0 = 98.0
        assert attr.total_pnl() == Decimal("98")

    def test_buy_only_no_pnl(self):
        bus = EventBus()
        attr = PnLAttribution(bus)
        bus.publish(_fill(action="BUY", price=100.0))
        assert attr.total_pnl() == Decimal("0")
        assert attr.trade_count() == 0


# ──────────────────────────────────────────────────────────────────────
# by_strategy
# ──────────────────────────────────────────────────────────────────────

class TestByStrategy:
    def test_by_strategy_single_strategy(self):
        bus = EventBus()
        attr = PnLAttribution(bus)
        bus.publish(_fill(strategy="mom", action="BUY", price=100.0, commission=0.0))
        bus.publish(_fill(strategy="mom", action="SELL", price=110.0, commission=0.0))
        result = attr.by_strategy()
        assert "mom" in result
        assert result["mom"] == Decimal("100")

    def test_by_strategy_multiple_strategies(self):
        bus = EventBus()
        attr = PnLAttribution(bus)
        bus.publish(_fill(strategy="mom", action="BUY", price=100.0, commission=0.0))
        bus.publish(_fill(strategy="mom", action="SELL", price=110.0, commission=0.0))
        bus.publish(_fill(symbol="GOOG", strategy="mean_rev", action="BUY", price=200.0, commission=0.0))
        bus.publish(_fill(symbol="GOOG", strategy="mean_rev", action="SELL", price=195.0, commission=0.0))
        result = attr.by_strategy()
        assert result["mom"] == Decimal("100")
        assert result["mean_rev"] == Decimal("-50")

    def test_by_strategy_empty_when_no_closes(self):
        bus = EventBus()
        attr = PnLAttribution(bus)
        bus.publish(_fill(action="BUY"))
        assert attr.by_strategy() == {}


# ──────────────────────────────────────────────────────────────────────
# by_asset
# ──────────────────────────────────────────────────────────────────────

class TestByAsset:
    def test_by_asset_single_symbol(self):
        bus = EventBus()
        attr = PnLAttribution(bus)
        bus.publish(_fill(symbol="AAPL", action="BUY", price=100.0, commission=0.0))
        bus.publish(_fill(symbol="AAPL", action="SELL", price=110.0, commission=0.0))
        result = attr.by_asset()
        assert result["AAPL"] == Decimal("100")

    def test_by_asset_multiple_symbols(self):
        bus = EventBus()
        attr = PnLAttribution(bus)
        bus.publish(_fill(symbol="AAPL", action="BUY", price=100.0, commission=0.0))
        bus.publish(_fill(symbol="AAPL", action="SELL", price=105.0, commission=0.0))
        bus.publish(_fill(symbol="GOOG", strategy="s2", action="BUY", price=200.0, commission=0.0))
        bus.publish(_fill(symbol="GOOG", strategy="s2", action="SELL", price=210.0, commission=0.0))
        result = attr.by_asset()
        assert result["AAPL"] == Decimal("50")
        assert result["GOOG"] == Decimal("100")


# ──────────────────────────────────────────────────────────────────────
# by_regime
# ──────────────────────────────────────────────────────────────────────

class TestByRegime:
    def test_by_regime_default_unknown(self):
        bus = EventBus()
        attr = PnLAttribution(bus)
        bus.publish(_fill(action="BUY", price=100.0, commission=0.0))
        bus.publish(_fill(action="SELL", price=110.0, commission=0.0))
        result = attr.by_regime()
        assert "unknown" in result

    def test_by_regime_with_set_regime(self):
        bus = EventBus()
        attr = PnLAttribution(bus)
        attr.set_regime("AAPL", "bullish")
        bus.publish(_fill(action="BUY", price=100.0, commission=0.0))
        bus.publish(_fill(action="SELL", price=110.0, commission=0.0))
        result = attr.by_regime()
        assert "bullish" in result
        assert result["bullish"] == Decimal("100")


# ──────────────────────────────────────────────────────────────────────
# by_day
# ──────────────────────────────────────────────────────────────────────

class TestByDay:
    def test_by_day_groups_correctly(self):
        bus = EventBus()
        attr = PnLAttribution(bus)
        bus.publish(_fill(action="BUY", price=100.0, commission=0.0))
        bus.publish(_fill(action="SELL", price=110.0, commission=0.0))
        result = attr.by_day()
        assert len(result) == 1
        assert list(result.values())[0] == Decimal("100")


# ──────────────────────────────────────────────────────────────────────
# Multiple fills sum correctly
# ──────────────────────────────────────────────────────────────────────

class TestMultipleFills:
    def test_total_pnl_sums_all_closed_trades(self):
        bus = EventBus()
        attr = PnLAttribution(bus)
        # Two separate strategies, each with a round trip
        bus.publish(_fill(strategy="s1", action="BUY", price=100.0, commission=0.0))
        bus.publish(_fill(strategy="s1", action="SELL", price=110.0, commission=0.0))
        bus.publish(_fill(symbol="GOOG", strategy="s2", action="BUY", price=200.0, commission=0.0))
        bus.publish(_fill(symbol="GOOG", strategy="s2", action="SELL", price=220.0, commission=0.0))
        # 100 + 200 = 300
        assert attr.total_pnl() == Decimal("300")
        assert attr.trade_count() == 2

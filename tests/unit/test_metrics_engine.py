"""Unit tests for observability.metrics_engine — MetricsEngine."""
from __future__ import annotations

from decimal import Decimal

import pytest

from observability.metrics_engine import (
    ExecutionMetrics,
    MetricsEngine,
    PerformanceMetrics,
    PortfolioMetrics,
    StrategyMetrics,
)
from streaming.event_bus import EventBus
from streaming.event_models import FillEvent, OrderEvent, PortfolioEvent, SignalEvent


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _portfolio(equity: float = 100000.0, cash: float = 50000.0, dd: float = 0.0) -> PortfolioEvent:
    return PortfolioEvent(
        equity=Decimal(str(equity)),
        cash=Decimal(str(cash)),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        daily_pnl=Decimal("0"),
        current_drawdown_pct=dd,
    )


def _fill(price: float = 150.0, commission: float = 0.5) -> FillEvent:
    return FillEvent(
        order_id="ord-1", symbol="AAPL", quantity=10,
        price=Decimal(str(price)), strategy_name="strat",
        action="BUY", commission=Decimal(str(commission)),
    )


def _order() -> OrderEvent:
    return OrderEvent(
        order_id="ord-1", symbol="AAPL", action="BUY",
        quantity=10, order_type="MARKET", strategy_name="strat",
    )


def _signal(action: str = "BUY", strategy: str = "strat", confidence: float = 0.8) -> SignalEvent:
    return SignalEvent(
        symbol="AAPL", strategy_name=strategy, action=action,
        confidence=confidence, timeframe="1m", current_price=Decimal("150"),
        atr=Decimal("2"), stop_price=Decimal("145"),
        regime="bullish", regime_strength=0.7,
    )


# ──────────────────────────────────────────────────────────────────────
# Portfolio metrics
# ──────────────────────────────────────────────────────────────────────

class TestPortfolioMetrics:
    def test_returns_none_before_any_portfolio_event(self):
        engine = MetricsEngine()
        assert engine.portfolio_metrics() is None

    def test_equity_correct(self):
        bus = EventBus()
        engine = MetricsEngine(bus)
        bus.publish(_portfolio(equity=105000.0, cash=50000.0))
        m = engine.portfolio_metrics()
        assert m.equity == Decimal("105000.0")

    def test_cash_correct(self):
        bus = EventBus()
        engine = MetricsEngine(bus)
        bus.publish(_portfolio(equity=100000.0, cash=40000.0))
        m = engine.portfolio_metrics()
        assert m.cash == Decimal("40000.0")

    def test_exposure_is_equity_minus_cash(self):
        bus = EventBus()
        engine = MetricsEngine(bus)
        bus.publish(_portfolio(equity=100000.0, cash=60000.0))
        m = engine.portfolio_metrics()
        assert m.exposure == Decimal("40000.0")

    def test_leverage_above_one_when_more_equity_than_cash(self):
        bus = EventBus()
        engine = MetricsEngine(bus)
        bus.publish(_portfolio(equity=100000.0, cash=50000.0))
        m = engine.portfolio_metrics()
        assert m.leverage == pytest.approx(2.0)

    def test_drawdown_correct(self):
        bus = EventBus()
        engine = MetricsEngine(bus)
        bus.publish(_portfolio(dd=5.5))
        m = engine.portfolio_metrics()
        assert m.drawdown_pct == pytest.approx(5.5)

    def test_peak_equity_tracks_maximum(self):
        bus = EventBus()
        engine = MetricsEngine(bus)
        bus.publish(_portfolio(equity=100000.0))
        bus.publish(_portfolio(equity=120000.0))
        bus.publish(_portfolio(equity=110000.0))
        m = engine.portfolio_metrics()
        assert m.peak_equity == Decimal("120000.0")


# ──────────────────────────────────────────────────────────────────────
# Performance metrics
# ──────────────────────────────────────────────────────────────────────

class TestPerformanceMetrics:
    def test_empty_returns_zero_win_rate(self):
        engine = MetricsEngine()
        m = engine.performance_metrics()
        assert m.win_rate == 0.0
        assert m.total_trades == 0

    def test_win_rate_all_positive(self):
        bus = EventBus()
        engine = MetricsEngine(bus)
        for eq in [100, 101, 102, 103, 104]:
            bus.publish(_portfolio(equity=float(eq) * 1000))
        m = engine.performance_metrics()
        assert m.win_rate == 1.0

    def test_win_rate_all_negative(self):
        bus = EventBus()
        engine = MetricsEngine(bus)
        for eq in [100, 99, 98, 97]:
            bus.publish(_portfolio(equity=float(eq) * 1000))
        m = engine.performance_metrics()
        assert m.win_rate == 0.0

    def test_profit_factor_positive_when_winning(self):
        bus = EventBus()
        engine = MetricsEngine(bus)
        for eq in [100, 105, 110, 115]:
            bus.publish(_portfolio(equity=float(eq) * 1000))
        m = engine.performance_metrics()
        assert m.profit_factor > 0

    def test_sharpe_none_with_single_point(self):
        bus = EventBus()
        engine = MetricsEngine(bus)
        bus.publish(_portfolio(equity=100000.0))
        m = engine.performance_metrics()
        assert m.sharpe_ratio is None

    def test_sharpe_returns_float_with_sufficient_data(self):
        bus = EventBus()
        engine = MetricsEngine(bus)
        for i in range(30):
            bus.publish(_portfolio(equity=100000.0 + i * 500))
        m = engine.performance_metrics()
        assert m.sharpe_ratio is not None

    def test_winning_losing_count_sum_to_total(self):
        bus = EventBus()
        engine = MetricsEngine(bus)
        for eq in [100, 105, 100, 98, 102]:
            bus.publish(_portfolio(equity=float(eq) * 1000))
        m = engine.performance_metrics()
        assert m.winning_trades + m.losing_trades == m.total_trades


# ──────────────────────────────────────────────────────────────────────
# Execution metrics
# ──────────────────────────────────────────────────────────────────────

class TestExecutionMetrics:
    def test_fill_count_zero_initially(self):
        engine = MetricsEngine()
        m = engine.execution_metrics()
        assert m.fill_count == 0

    def test_fill_count_increments(self):
        bus = EventBus()
        engine = MetricsEngine(bus)
        bus.publish(_fill())
        bus.publish(_fill())
        m = engine.execution_metrics()
        assert m.fill_count == 2

    def test_order_count_increments(self):
        bus = EventBus()
        engine = MetricsEngine(bus)
        bus.publish(_order())
        bus.publish(_order())
        m = engine.execution_metrics()
        assert m.order_count == 2

    def test_fill_rate_one_when_all_filled(self):
        bus = EventBus()
        engine = MetricsEngine(bus)
        for _ in range(3):
            bus.publish(_order())
            bus.publish(_fill())
        m = engine.execution_metrics()
        assert m.fill_rate == pytest.approx(1.0)

    def test_total_commission_sums(self):
        bus = EventBus()
        engine = MetricsEngine(bus)
        bus.publish(_fill(commission=1.0))
        bus.publish(_fill(commission=2.0))
        m = engine.execution_metrics()
        assert m.total_commission == Decimal("3.0")

    def test_avg_fill_price_correct(self):
        bus = EventBus()
        engine = MetricsEngine(bus)
        bus.publish(_fill(price=100.0))
        bus.publish(_fill(price=200.0))
        m = engine.execution_metrics()
        assert m.avg_fill_price == Decimal("150.0")

    def test_avg_fill_price_none_when_no_fills(self):
        engine = MetricsEngine()
        m = engine.execution_metrics()
        assert m.avg_fill_price is None


# ──────────────────────────────────────────────────────────────────────
# Strategy metrics
# ──────────────────────────────────────────────────────────────────────

class TestStrategyMetrics:
    def test_signal_count_zero_initially(self):
        engine = MetricsEngine()
        m = engine.strategy_metrics()
        assert m.signal_count == 0

    def test_signal_count_increments(self):
        bus = EventBus()
        engine = MetricsEngine(bus)
        bus.publish(_signal(action="BUY"))
        bus.publish(_signal(action="FLAT"))
        m = engine.strategy_metrics()
        assert m.signal_count == 2

    def test_flat_count_correct(self):
        bus = EventBus()
        engine = MetricsEngine(bus)
        bus.publish(_signal(action="FLAT"))
        bus.publish(_signal(action="FLAT"))
        bus.publish(_signal(action="BUY"))
        m = engine.strategy_metrics()
        assert m.flat_count == 2

    def test_buy_sell_count(self):
        bus = EventBus()
        engine = MetricsEngine(bus)
        bus.publish(_signal(action="BUY"))
        bus.publish(_signal(action="BUY"))
        bus.publish(_signal(action="SELL"))
        m = engine.strategy_metrics()
        assert m.buy_count == 2
        assert m.sell_count == 1

    def test_avg_confidence_correct(self):
        bus = EventBus()
        engine = MetricsEngine(bus)
        bus.publish(_signal(action="BUY", confidence=0.8))
        bus.publish(_signal(action="SELL", confidence=0.6))
        m = engine.strategy_metrics()
        assert m.avg_confidence == pytest.approx(0.7)

    def test_filter_by_strategy_name(self):
        bus = EventBus()
        engine = MetricsEngine(bus)
        bus.publish(_signal(strategy="mom"))
        bus.publish(_signal(strategy="mean_rev"))
        m = engine.strategy_metrics(strategy_name="mom")
        assert m.signal_count == 1

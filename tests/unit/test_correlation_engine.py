"""Unit tests for observability.correlation_engine — EventCorrelationEngine."""
from __future__ import annotations

from decimal import Decimal

import pytest

from observability.correlation_engine import EventChain, EventCorrelationEngine
from streaming.event_bus import EventBus
from streaming.event_models import (
    CandleEvent, FillEvent, IndicatorEvent, OrderEvent,
    PortfolioEvent, RiskEvent, SignalEvent, TickEvent,
)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _tick(symbol: str = "AAPL") -> TickEvent:
    return TickEvent(symbol=symbol, price=Decimal("150"), volume=100)


def _candle(symbol: str = "AAPL") -> CandleEvent:
    return CandleEvent(
        symbol=symbol, timeframe="1m",
        open=Decimal("150"), high=Decimal("151"), low=Decimal("149"), close=Decimal("150"),
        volume=1000, is_closed=True,
    )


def _indicator(symbol: str = "AAPL") -> IndicatorEvent:
    return IndicatorEvent(
        symbol=symbol, timeframe="1m", close=150.0, high=151.0, low=149.0,
        volume=1000, is_warm=True,
    )


def _signal(symbol: str = "AAPL", strategy: str = "strat", action: str = "BUY") -> SignalEvent:
    return SignalEvent(
        symbol=symbol, strategy_name=strategy, action=action,
        confidence=0.8, timeframe="1m", current_price=Decimal("150"),
        atr=Decimal("2"), stop_price=Decimal("145"),
        regime="bullish", regime_strength=0.7,
    )


def _risk(symbol: str = "AAPL", strategy: str = "strat", decision: str = "APPROVED") -> RiskEvent:
    return RiskEvent(
        symbol=symbol, strategy_name=strategy,
        decision=decision, approved_quantity=10, original_quantity=10, reason="ok",
    )


def _order(symbol: str = "AAPL", strategy: str = "strat") -> OrderEvent:
    return OrderEvent(
        order_id="ord-1", symbol=symbol, action="BUY",
        quantity=10, order_type="MARKET", strategy_name=strategy,
    )


def _fill(symbol: str = "AAPL", strategy: str = "strat") -> FillEvent:
    return FillEvent(
        order_id="ord-1", symbol=symbol, quantity=10,
        price=Decimal("150"), strategy_name=strategy,
        action="BUY", commission=Decimal("0.5"),
    )


def _portfolio() -> PortfolioEvent:
    return PortfolioEvent(
        equity=Decimal("100000"), cash=Decimal("98500"),
        unrealized_pnl=Decimal("0"), realized_pnl=Decimal("0"),
        daily_pnl=Decimal("0"), current_drawdown_pct=0.0,
    )


def _full_chain(bus: EventBus) -> None:
    bus.publish(_tick())
    bus.publish(_candle())
    bus.publish(_indicator())
    bus.publish(_signal())
    bus.publish(_risk())
    bus.publish(_order())
    bus.publish(_fill())
    bus.publish(_portfolio())


# ──────────────────────────────────────────────────────────────────────
# EventChain dataclass
# ──────────────────────────────────────────────────────────────────────

class TestEventChain:
    def test_is_complete_false_with_no_fills(self):
        chain = EventChain(chain_id="c1", symbol="AAPL", strategy_name="s")
        assert chain.is_complete() is False

    def test_is_complete_false_without_portfolio(self):
        chain = EventChain(chain_id="c1", symbol="AAPL", strategy_name="s")
        chain.fills.append(_fill())
        assert chain.is_complete() is False

    def test_is_complete_true_with_fills_and_portfolio(self):
        chain = EventChain(chain_id="c1", symbol="AAPL", strategy_name="s")
        chain.fills.append(_fill())
        chain.portfolio = _portfolio()
        assert chain.is_complete() is True

    def test_steps_empty_chain(self):
        chain = EventChain(chain_id="c1", symbol="AAPL", strategy_name="s")
        assert chain.steps() == []

    def test_steps_returns_ordered_list(self):
        chain = EventChain(
            chain_id="c1", symbol="AAPL", strategy_name="s",
            tick=_tick(), signal=_signal(),
        )
        labels = [s[0] for s in chain.steps()]
        assert labels == ["Tick Received", "Signal Generated"]


# ──────────────────────────────────────────────────────────────────────
# EventCorrelationEngine — chain creation
# ──────────────────────────────────────────────────────────────────────

class TestCorrelationEngineChains:
    def test_no_chains_initially(self):
        engine = EventCorrelationEngine()
        assert engine.chain_count() == 0

    def test_signal_creates_chain(self):
        bus = EventBus()
        engine = EventCorrelationEngine(bus)
        bus.publish(_signal())
        assert engine.chain_count() == 1

    def test_flat_signal_does_not_create_chain(self):
        bus = EventBus()
        engine = EventCorrelationEngine(bus)
        bus.publish(_signal(action="FLAT"))
        assert engine.chain_count() == 0

    def test_two_signals_create_two_chains(self):
        bus = EventBus()
        engine = EventCorrelationEngine(bus)
        bus.publish(_signal(strategy="s1"))
        bus.publish(_signal(symbol="GOOG", strategy="s2"))
        assert engine.chain_count() == 2

    def test_chain_has_signal(self):
        bus = EventBus()
        engine = EventCorrelationEngine(bus)
        bus.publish(_signal())
        chains = engine.get_all_chains()
        assert chains[0].signal is not None

    def test_chain_captures_tick_context(self):
        bus = EventBus()
        engine = EventCorrelationEngine(bus)
        bus.publish(_tick())
        bus.publish(_signal())
        chains = engine.get_all_chains()
        assert chains[0].tick is not None

    def test_chain_captures_closed_candle_context(self):
        bus = EventBus()
        engine = EventCorrelationEngine(bus)
        bus.publish(_candle())
        bus.publish(_signal())
        chains = engine.get_all_chains()
        assert chains[0].candle is not None

    def test_chain_captures_indicator_context(self):
        bus = EventBus()
        engine = EventCorrelationEngine(bus)
        bus.publish(_indicator())
        bus.publish(_signal())
        chains = engine.get_all_chains()
        assert chains[0].indicator is not None

    def test_chain_links_risk_event(self):
        bus = EventBus()
        engine = EventCorrelationEngine(bus)
        bus.publish(_signal())
        bus.publish(_risk())
        chains = engine.get_all_chains()
        assert chains[0].risk is not None

    def test_chain_links_order_event(self):
        bus = EventBus()
        engine = EventCorrelationEngine(bus)
        bus.publish(_signal())
        bus.publish(_order())
        chains = engine.get_all_chains()
        assert chains[0].order is not None

    def test_chain_links_fill_event(self):
        bus = EventBus()
        engine = EventCorrelationEngine(bus)
        bus.publish(_signal())
        bus.publish(_fill())
        chains = engine.get_all_chains()
        assert len(chains[0].fills) == 1


# ──────────────────────────────────────────────────────────────────────
# Completed chains
# ──────────────────────────────────────────────────────────────────────

class TestCompletedChains:
    def test_no_completed_chains_without_portfolio(self):
        bus = EventBus()
        engine = EventCorrelationEngine(bus)
        bus.publish(_signal())
        bus.publish(_fill())
        assert len(engine.get_completed_chains()) == 0

    def test_chain_completed_after_portfolio_event(self):
        bus = EventBus()
        engine = EventCorrelationEngine(bus)
        bus.publish(_signal())
        bus.publish(_fill())
        bus.publish(_portfolio())
        assert len(engine.get_completed_chains()) == 1

    def test_completed_chain_is_complete(self):
        bus = EventBus()
        engine = EventCorrelationEngine(bus)
        _full_chain(bus)
        completed = engine.get_completed_chains()
        assert len(completed) == 1
        assert completed[0].is_complete() is True

    def test_full_chain_steps_in_order(self):
        bus = EventBus()
        engine = EventCorrelationEngine(bus)
        _full_chain(bus)
        steps = engine.get_completed_chains()[0].steps()
        labels = [s[0] for s in steps]
        assert "Signal Generated" in labels
        assert "Risk Evaluated" in labels
        assert "Order Submitted" in labels
        assert "Order Filled" in labels
        assert "Portfolio Updated" in labels


# ──────────────────────────────────────────────────────────────────────
# trace_trade
# ──────────────────────────────────────────────────────────────────────

class TestTraceTrade:
    def test_trace_unknown_id_returns_none(self):
        engine = EventCorrelationEngine()
        assert engine.trace_trade("no-such-chain") is None

    def test_trace_returns_chain_by_id(self):
        bus = EventBus()
        engine = EventCorrelationEngine(bus)
        bus.publish(_signal())
        chain = engine.get_all_chains()[0]
        found = engine.trace_trade(chain.chain_id)
        assert found is chain

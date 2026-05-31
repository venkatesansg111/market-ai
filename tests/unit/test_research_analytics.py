"""Unit tests for observability.research_analytics — ResearchAnalyticsEngine."""
from __future__ import annotations

from decimal import Decimal

import pytest

from observability.research_analytics import ResearchAnalyticsEngine, SignalAnalytics, StrategyAnalytics
from streaming.event_bus import EventBus
from streaming.event_models import FillEvent, SignalEvent


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _signal(
    strategy: str = "mom",
    action: str = "BUY",
    confidence: float = 0.8,
    symbol: str = "AAPL",
) -> SignalEvent:
    return SignalEvent(
        symbol=symbol, strategy_name=strategy, action=action,
        confidence=confidence, timeframe="1m", current_price=Decimal("150"),
        atr=Decimal("2"), stop_price=Decimal("145"),
        regime="bullish", regime_strength=0.7,
    )


def _fill(
    strategy: str = "mom",
    action: str = "BUY",
    price: float = 150.0,
    symbol: str = "AAPL",
    qty: int = 10,
) -> FillEvent:
    return FillEvent(
        order_id="ord-1", symbol=symbol, quantity=qty,
        price=Decimal(str(price)), strategy_name=strategy,
        action=action, commission=Decimal("0"),
    )


# ──────────────────────────────────────────────────────────────────────
# Signal analytics
# ──────────────────────────────────────────────────────────────────────

class TestSignalAnalytics:
    def test_empty_returns_empty_list(self):
        engine = ResearchAnalyticsEngine()
        assert engine.signal_analytics() == []

    def test_signal_count_includes_flat(self):
        bus = EventBus()
        engine = ResearchAnalyticsEngine(bus)
        bus.publish(_signal(action="BUY"))
        bus.publish(_signal(action="FLAT"))
        analytics = engine.signal_analytics()
        assert analytics[0].total_signals == 2

    def test_buy_sell_counts_correct(self):
        bus = EventBus()
        engine = ResearchAnalyticsEngine(bus)
        bus.publish(_signal(action="BUY"))
        bus.publish(_signal(action="BUY"))
        bus.publish(_signal(action="SELL"))
        a = engine.signal_analytics()[0]
        assert a.buy_signals == 2
        assert a.sell_signals == 1

    def test_avg_confidence_correct(self):
        bus = EventBus()
        engine = ResearchAnalyticsEngine(bus)
        bus.publish(_signal(action="BUY", confidence=0.8))
        bus.publish(_signal(action="SELL", confidence=0.6))
        a = engine.signal_analytics()[0]
        assert a.avg_confidence == pytest.approx(0.7)

    def test_high_confidence_count(self):
        bus = EventBus()
        engine = ResearchAnalyticsEngine(bus)
        bus.publish(_signal(action="BUY", confidence=0.9))
        bus.publish(_signal(action="BUY", confidence=0.5))
        bus.publish(_signal(action="BUY", confidence=0.75))
        a = engine.signal_analytics()[0]
        assert a.high_confidence_signals == 2  # 0.9 and 0.75

    def test_filter_by_strategy_name(self):
        bus = EventBus()
        engine = ResearchAnalyticsEngine(bus)
        bus.publish(_signal(strategy="mom", action="BUY"))
        bus.publish(_signal(strategy="mean_rev", action="SELL"))
        analytics = engine.signal_analytics(strategy_name="mom")
        assert len(analytics) == 1
        assert analytics[0].strategy_name == "mom"

    def test_multiple_strategies_separate_analytics(self):
        bus = EventBus()
        engine = ResearchAnalyticsEngine(bus)
        bus.publish(_signal(strategy="s1", action="BUY"))
        bus.publish(_signal(strategy="s2", action="SELL"))
        analytics = engine.signal_analytics()
        names = {a.strategy_name for a in analytics}
        assert names == {"s1", "s2"}

    def test_flat_excluded_from_avg_confidence(self):
        bus = EventBus()
        engine = ResearchAnalyticsEngine(bus)
        bus.publish(_signal(action="FLAT", confidence=0.0))
        bus.publish(_signal(action="BUY", confidence=0.8))
        a = engine.signal_analytics()[0]
        assert a.avg_confidence == pytest.approx(0.8)


# ──────────────────────────────────────────────────────────────────────
# Strategy analytics
# ──────────────────────────────────────────────────────────────────────

class TestStrategyAnalytics:
    def test_empty_returns_empty_list(self):
        engine = ResearchAnalyticsEngine()
        assert engine.strategy_analytics() == []

    def test_total_fills_correct(self):
        bus = EventBus()
        engine = ResearchAnalyticsEngine(bus)
        bus.publish(_fill(action="BUY"))
        bus.publish(_fill(action="SELL"))
        analytics = engine.strategy_analytics()
        assert analytics[0].total_fills == 2

    def test_pnl_computed(self):
        bus = EventBus()
        engine = ResearchAnalyticsEngine(bus)
        bus.publish(_fill(action="BUY", price=100.0))
        bus.publish(_fill(action="SELL", price=110.0))
        a = engine.strategy_analytics()[0]
        assert a.total_pnl == Decimal("100")  # (110-100)*10

    def test_symbols_list(self):
        bus = EventBus()
        engine = ResearchAnalyticsEngine(bus)
        bus.publish(_fill(symbol="AAPL"))
        bus.publish(_fill(symbol="GOOG"))
        a = engine.strategy_analytics()[0]
        assert set(a.symbols) == {"AAPL", "GOOG"}


# ──────────────────────────────────────────────────────────────────────
# Confidence distribution
# ──────────────────────────────────────────────────────────────────────

class TestConfidenceDistribution:
    def test_empty_all_buckets_zero(self):
        engine = ResearchAnalyticsEngine()
        dist = engine.confidence_distribution()
        assert all(v == 0 for v in dist.values())

    def test_bucket_keys_present(self):
        engine = ResearchAnalyticsEngine()
        dist = engine.confidence_distribution()
        assert "0.0-0.3" in dist
        assert "0.9-1.0" in dist

    def test_signals_bucketed_correctly(self):
        bus = EventBus()
        engine = ResearchAnalyticsEngine(bus)
        bus.publish(_signal(action="BUY", confidence=0.1))   # 0.0-0.3
        bus.publish(_signal(action="BUY", confidence=0.4))   # 0.3-0.5
        bus.publish(_signal(action="BUY", confidence=0.95))  # 0.9-1.0
        dist = engine.confidence_distribution()
        assert dist["0.0-0.3"] == 1
        assert dist["0.3-0.5"] == 1
        assert dist["0.9-1.0"] == 1

    def test_flat_signals_excluded_from_distribution(self):
        bus = EventBus()
        engine = ResearchAnalyticsEngine(bus)
        bus.publish(_signal(action="FLAT", confidence=0.0))
        dist = engine.confidence_distribution()
        assert sum(dist.values()) == 0


# ──────────────────────────────────────────────────────────────────────
# Fill price distribution
# ──────────────────────────────────────────────────────────────────────

class TestFillPriceDistribution:
    def test_empty_returns_empty_dict(self):
        engine = ResearchAnalyticsEngine()
        assert engine.fill_price_distribution() == {}

    def test_distribution_sums_to_fill_count(self):
        bus = EventBus()
        engine = ResearchAnalyticsEngine(bus)
        for price in [100, 110, 120, 130, 140]:
            bus.publish(_fill(price=float(price)))
        dist = engine.fill_price_distribution()
        assert sum(dist.values()) == 5

    def test_single_price_returns_single_bucket(self):
        bus = EventBus()
        engine = ResearchAnalyticsEngine(bus)
        bus.publish(_fill(price=150.0))
        bus.publish(_fill(price=150.0))
        dist = engine.fill_price_distribution()
        assert sum(dist.values()) == 2


# ──────────────────────────────────────────────────────────────────────
# Counters
# ──────────────────────────────────────────────────────────────────────

class TestCounters:
    def test_signal_count_zero_initially(self):
        engine = ResearchAnalyticsEngine()
        assert engine.signal_count == 0

    def test_fill_count_zero_initially(self):
        engine = ResearchAnalyticsEngine()
        assert engine.fill_count == 0

    def test_signal_count_increments(self):
        bus = EventBus()
        engine = ResearchAnalyticsEngine(bus)
        bus.publish(_signal())
        bus.publish(_signal())
        assert engine.signal_count == 2

    def test_fill_count_increments(self):
        bus = EventBus()
        engine = ResearchAnalyticsEngine(bus)
        bus.publish(_fill())
        bus.publish(_fill())
        assert engine.fill_count == 2

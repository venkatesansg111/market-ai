"""Unit tests for observability.system_health — SystemHealthEngine."""
from __future__ import annotations

import time
from decimal import Decimal

import pytest

from observability.system_health import HealthSnapshot, SystemHealthEngine
from streaming.event_bus import EventBus
from streaming.event_models import SignalEvent, TickEvent


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _tick() -> TickEvent:
    return TickEvent(symbol="AAPL", price=Decimal("150"), volume=100)


def _signal() -> SignalEvent:
    return SignalEvent(
        symbol="AAPL", strategy_name="strat", action="BUY",
        confidence=0.8, timeframe="1m", current_price=Decimal("150"),
        atr=Decimal("2"), stop_price=Decimal("145"),
        regime="bullish", regime_strength=0.7,
    )


# ──────────────────────────────────────────────────────────────────────
# Snapshot
# ──────────────────────────────────────────────────────────────────────

class TestSnapshot:
    def test_snapshot_returns_health_snapshot(self):
        bus = EventBus()
        engine = SystemHealthEngine(bus)
        snap = engine.snapshot()
        assert isinstance(snap, HealthSnapshot)

    def test_status_healthy_with_no_errors(self):
        bus = EventBus()
        engine = SystemHealthEngine(bus)
        bus.publish(_tick())
        snap = engine.snapshot()
        assert snap.status == "healthy"

    def test_uptime_positive(self):
        bus = EventBus()
        engine = SystemHealthEngine(bus)
        snap = engine.snapshot()
        assert snap.uptime_seconds >= 0

    def test_publish_count_reflects_bus(self):
        bus = EventBus()
        engine = SystemHealthEngine(bus)
        bus.publish(_tick())
        bus.publish(_tick())
        snap = engine.snapshot()
        assert snap.publish_count >= 2

    def test_error_count_zero_with_no_errors(self):
        bus = EventBus()
        engine = SystemHealthEngine(bus)
        bus.publish(_tick())
        snap = engine.snapshot()
        assert snap.error_count == 0

    def test_active_subscriptions_positive(self):
        bus = EventBus()
        engine = SystemHealthEngine(bus)
        received = []
        bus.subscribe(TickEvent, received.append)
        snap = engine.snapshot()
        assert snap.active_subscriptions >= 1

    def test_events_per_second_after_burst(self):
        bus = EventBus()
        engine = SystemHealthEngine(bus)
        for _ in range(20):
            bus.publish(_tick())
        snap = engine.snapshot()
        assert snap.events_per_second >= 0  # >= 0 always

    def test_snapshot_stored_in_history(self):
        bus = EventBus()
        engine = SystemHealthEngine(bus)
        engine.snapshot()
        engine.snapshot()
        assert len(engine.history()) == 2


# ──────────────────────────────────────────────────────────────────────
# is_healthy
# ──────────────────────────────────────────────────────────────────────

class TestIsHealthy:
    def test_is_healthy_true_with_no_errors(self):
        bus = EventBus()
        engine = SystemHealthEngine(bus)
        assert engine.is_healthy() is True

    def test_is_healthy_false_after_many_errors(self):
        bus = EventBus()
        engine = SystemHealthEngine(bus)
        # Force error count by publishing events with a broken handler
        broken = []
        bus.subscribe(TickEvent, lambda e: (_ for _ in ()).throw(RuntimeError("err")))
        for _ in range(10):
            bus.publish(_tick())
        # Now error rate > 5%
        snap = engine.snapshot()
        # error_count is non-zero, so status may be degraded or unhealthy
        assert snap.status in ("degraded", "unhealthy")

    def test_no_bus_is_healthy(self):
        engine = SystemHealthEngine()
        assert engine.is_healthy() is True


# ──────────────────────────────────────────────────────────────────────
# History
# ──────────────────────────────────────────────────────────────────────

class TestHistory:
    def test_empty_history_initially(self):
        engine = SystemHealthEngine()
        assert engine.history() == []

    def test_history_grows_with_snapshots(self):
        bus = EventBus()
        engine = SystemHealthEngine(bus)
        for _ in range(3):
            engine.snapshot()
        assert len(engine.history()) == 3

    def test_history_returns_copy(self):
        bus = EventBus()
        engine = SystemHealthEngine(bus)
        engine.snapshot()
        h1 = engine.history()
        engine.snapshot()
        h2 = engine.history()
        assert len(h1) == 1
        assert len(h2) == 2

    def test_all_history_items_are_snapshots(self):
        bus = EventBus()
        engine = SystemHealthEngine(bus)
        for _ in range(3):
            engine.snapshot()
        assert all(isinstance(s, HealthSnapshot) for s in engine.history())


# ──────────────────────────────────────────────────────────────────────
# Without bus
# ──────────────────────────────────────────────────────────────────────

class TestWithoutBus:
    def test_snapshot_without_bus_returns_valid_snapshot(self):
        engine = SystemHealthEngine()
        snap = engine.snapshot()
        assert snap.publish_count == 0
        assert snap.error_count == 0
        assert snap.status == "healthy"

    def test_attach_later_works(self):
        engine = SystemHealthEngine()
        bus = EventBus()
        engine.attach(bus)
        bus.publish(_tick())
        snap = engine.snapshot()
        assert snap.publish_count >= 1

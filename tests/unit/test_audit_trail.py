"""Unit tests for observability.audit_trail — AuditTrail."""
from __future__ import annotations

from decimal import Decimal

import pytest

from observability.audit_trail import AuditEntry, AuditTrail
from streaming.event_bus import EventBus
from streaming.event_models import CandleEvent, FillEvent, PortfolioEvent, SignalEvent, TickEvent


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _tick(symbol: str = "AAPL") -> TickEvent:
    return TickEvent(symbol=symbol, price=Decimal("150"), volume=100)


def _signal() -> SignalEvent:
    return SignalEvent(
        symbol="AAPL", strategy_name="strat", action="BUY",
        confidence=0.8, timeframe="1m", current_price=Decimal("150"),
        atr=Decimal("2"), stop_price=Decimal("145"),
        regime="bullish", regime_strength=0.7,
    )


def _portfolio() -> PortfolioEvent:
    return PortfolioEvent(
        equity=Decimal("100000"), cash=Decimal("98500"),
        unrealized_pnl=Decimal("0"), realized_pnl=Decimal("0"),
        daily_pnl=Decimal("0"), current_drawdown_pct=0.0,
    )


# ──────────────────────────────────────────────────────────────────────
# Basic recording
# ──────────────────────────────────────────────────────────────────────

class TestAuditTrailBasic:
    def test_empty_trail_has_zero_entries(self):
        trail = AuditTrail()
        assert trail.entry_count() == 0

    def test_recording_via_bus_increments_count(self):
        bus = EventBus()
        trail = AuditTrail(bus)
        bus.publish(_tick())
        assert trail.entry_count() == 1

    def test_entry_is_audit_entry(self):
        bus = EventBus()
        trail = AuditTrail(bus)
        bus.publish(_tick())
        assert isinstance(trail.entries()[0], AuditEntry)

    def test_entry_event_type_matches(self):
        bus = EventBus()
        trail = AuditTrail(bus)
        bus.publish(_tick())
        assert trail.entries()[0].event_type == "TickEvent"

    def test_entry_symbol_extracted(self):
        bus = EventBus()
        trail = AuditTrail(bus)
        bus.publish(_tick(symbol="GOOG"))
        assert trail.entries()[0].symbol == "GOOG"

    def test_sequence_starts_at_zero(self):
        bus = EventBus()
        trail = AuditTrail(bus)
        bus.publish(_tick())
        assert trail.entries()[0].seq == 0

    def test_sequence_increments(self):
        bus = EventBus()
        trail = AuditTrail(bus)
        for _ in range(5):
            bus.publish(_tick())
        seqs = [e.seq for e in trail.entries()]
        assert seqs == list(range(5))

    def test_last_sequence_tracks_latest(self):
        bus = EventBus()
        trail = AuditTrail(bus)
        bus.publish(_tick())
        bus.publish(_tick())
        assert trail.last_sequence() == 1

    def test_last_sequence_minus_one_on_empty(self):
        trail = AuditTrail()
        assert trail.last_sequence() == -1

    def test_entries_stores_original_event(self):
        bus = EventBus()
        trail = AuditTrail(bus)
        t = _tick()
        bus.publish(t)
        assert trail.entries()[0].event is t


# ──────────────────────────────────────────────────────────────────────
# Filtering
# ──────────────────────────────────────────────────────────────────────

class TestAuditTrailFiltering:
    def test_filter_by_event_type(self):
        bus = EventBus()
        trail = AuditTrail(bus)
        bus.publish(_tick())
        bus.publish(_signal())
        tick_entries = trail.entries(event_type="TickEvent")
        assert len(tick_entries) == 1
        assert all(e.event_type == "TickEvent" for e in tick_entries)

    def test_filter_by_symbol(self):
        bus = EventBus()
        trail = AuditTrail(bus)
        bus.publish(_tick("AAPL"))
        bus.publish(_tick("GOOG"))
        bus.publish(_tick("AAPL"))
        aapl = trail.entries(symbol="AAPL")
        assert len(aapl) == 2

    def test_filter_by_type_and_symbol(self):
        bus = EventBus()
        trail = AuditTrail(bus)
        bus.publish(_tick("AAPL"))
        bus.publish(_signal())  # signal symbol is AAPL too
        result = trail.entries(event_type="TickEvent", symbol="AAPL")
        assert len(result) == 1

    def test_no_filter_returns_all(self):
        bus = EventBus()
        trail = AuditTrail(bus)
        bus.publish(_tick())
        bus.publish(_signal())
        bus.publish(_portfolio())
        assert len(trail.entries()) == 3


# ──────────────────────────────────────────────────────────────────────
# Append-only (immutability)
# ──────────────────────────────────────────────────────────────────────

class TestAuditTrailImmutability:
    def test_entries_returns_copy(self):
        bus = EventBus()
        trail = AuditTrail(bus)
        bus.publish(_tick())
        snapshot = trail.entries()
        bus.publish(_tick())  # new event after snapshot
        assert len(snapshot) == 1  # snapshot unchanged
        assert trail.entry_count() == 2

    def test_is_monotonic_wall_time(self):
        bus = EventBus()
        trail = AuditTrail(bus)
        for _ in range(20):
            bus.publish(_tick())
        assert trail.is_monotonic() is True

    def test_multiple_event_types_all_recorded(self):
        bus = EventBus()
        trail = AuditTrail(bus)
        bus.publish(_tick())
        bus.publish(_signal())
        bus.publish(_portfolio())
        types = {e.event_type for e in trail.entries()}
        assert types == {"TickEvent", "SignalEvent", "PortfolioEvent"}

    def test_event_id_recorded(self):
        bus = EventBus()
        trail = AuditTrail(bus)
        t = _tick()
        bus.publish(t)
        assert trail.entries()[0].event_id == t.event_id

"""Unit tests for streaming.event_replay — EventLog, ReplayEngine, DeterminismVerifier."""
from __future__ import annotations

import time
from datetime import datetime
from decimal import Decimal

import pytest

from streaming.event_bus import EventBus
from streaming.event_models import (
    CandleEvent, IndicatorEvent, SignalEvent, StreamEvent, TickEvent,
)
from streaming.event_replay import DeterminismVerifier, EventLog, LogEntry, ReplayEngine


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

_FIXED_TS = datetime(2024, 1, 15, 9, 30, 0)


def _tick(symbol: str = "AAPL", price: float = 100.0, ts: datetime | None = None) -> TickEvent:
    return TickEvent(symbol=symbol, price=Decimal(str(price)), volume=10,
                     timestamp=ts or _FIXED_TS)


def _candle(symbol: str = "AAPL") -> CandleEvent:
    return CandleEvent(
        symbol=symbol, timeframe="1m",
        open=Decimal("100"), high=Decimal("101"),
        low=Decimal("99"), close=Decimal("100.5"),
        volume=500, is_closed=True,
        timestamp=_FIXED_TS,
    )


# ──────────────────────────────────────────────────────────────────────
# EventLog
# ──────────────────────────────────────────────────────────────────────

class TestEventLog:
    def test_empty_log_has_len_zero(self):
        log = EventLog()
        assert len(log) == 0

    def test_record_appends_entry(self):
        log = EventLog()
        log.record(_tick())
        assert len(log) == 1

    def test_events_returns_list(self):
        log = EventLog()
        t = _tick()
        log.record(t)
        evs = log.events()
        assert evs[0] is t

    def test_events_filter_by_type(self):
        log = EventLog()
        log.record(_tick())
        log.record(_candle())
        log.record(_tick())
        tick_events = log.events(TickEvent)
        assert len(tick_events) == 2
        assert all(isinstance(e, TickEvent) for e in tick_events)

    def test_entries_returns_log_entries(self):
        log = EventLog()
        log.record(_tick())
        entries = log.entries()
        assert len(entries) == 1
        assert isinstance(entries[0], LogEntry)

    def test_entries_have_monotonic_wall_times(self):
        log = EventLog()
        for _ in range(5):
            log.record(_tick())
        times = [e.wall_time for e in log.entries()]
        assert all(times[i] <= times[i + 1] for i in range(len(times) - 1))

    def test_clear_resets_log(self):
        log = EventLog()
        log.record(_tick())
        log.clear()
        assert len(log) == 0

    def test_attach_to_bus_records_events(self):
        bus = EventBus()
        log = EventLog()
        log.attach_to_bus(bus)
        bus.publish(_tick())
        bus.publish(_tick())
        assert len(log) == 2

    def test_attach_to_bus_specific_type(self):
        bus = EventBus()
        log = EventLog()
        log.attach_to_bus(bus, TickEvent)
        bus.publish(_tick())
        bus.publish(_candle())
        assert len(log) == 1
        assert isinstance(log.events()[0], TickEvent)

    def test_detach_from_bus_stops_recording(self):
        bus = EventBus()
        log = EventLog()
        log.attach_to_bus(bus)
        bus.publish(_tick())
        log.detach_from_bus(bus)
        bus.publish(_tick())
        assert len(log) == 1


# ──────────────────────────────────────────────────────────────────────
# ReplayEngine — instant mode
# ──────────────────────────────────────────────────────────────────────

class TestReplayEngineInstant:
    def test_replay_returns_zero_for_empty_log(self):
        bus = EventBus()
        engine = ReplayEngine(bus)
        log = EventLog()
        count = engine.replay(log)
        assert count == 0

    def test_replay_publishes_all_events(self):
        bus = EventBus()
        received = []
        bus.subscribe(TickEvent, received.append)
        engine = ReplayEngine(bus)

        log = EventLog()
        for i in range(5):
            log.record(_tick(price=100.0 + i))

        count = engine.replay(log)
        assert count == 5
        assert len(received) == 5

    def test_replay_count_accumulates(self):
        bus = EventBus()
        engine = ReplayEngine(bus)
        log = EventLog()
        log.record(_tick())
        log.record(_tick())
        engine.replay(log)
        engine.replay(log)
        assert engine.replay_count == 4

    def test_instant_replay_preserves_event_types(self):
        bus = EventBus()
        received = []
        bus.subscribe(StreamEvent, received.append)
        engine = ReplayEngine(bus)

        log = EventLog()
        log.record(_tick())
        log.record(_candle())
        engine.replay(log)

        assert isinstance(received[0], TickEvent)
        assert isinstance(received[1], CandleEvent)

    def test_instant_replay_is_fast(self):
        bus = EventBus()
        engine = ReplayEngine(bus)
        log = EventLog()
        for _ in range(1000):
            log.record(_tick())
        start = time.monotonic()
        engine.replay(log, speed=0.0)
        elapsed = time.monotonic() - start
        assert elapsed < 1.0  # 1000 events in under 1 second

    def test_replay_filter_by_event_type(self):
        bus = EventBus()
        received = []
        bus.subscribe(TickEvent, received.append)
        engine = ReplayEngine(bus)

        log = EventLog()
        log.record(_tick())
        log.record(_candle())
        log.record(_tick())

        count = engine.replay(log, event_type=TickEvent)
        assert count == 2
        assert len(received) == 2


# ──────────────────────────────────────────────────────────────────────
# ReplayEngine — preserves event content
# ──────────────────────────────────────────────────────────────────────

class TestReplayEventContent:
    def test_replayed_event_has_same_symbol(self):
        bus = EventBus()
        received = []
        bus.subscribe(TickEvent, received.append)
        engine = ReplayEngine(bus)

        original = _tick(symbol="GOOG", price=2000.0)
        log = EventLog()
        log.record(original)
        engine.replay(log)

        assert received[0].symbol == "GOOG"
        assert received[0].price == Decimal("2000.0")

    def test_replayed_events_same_as_originals(self):
        bus = EventBus()
        received = []
        bus.subscribe(StreamEvent, received.append)
        engine = ReplayEngine(bus)

        originals = [_tick(price=100.0 + i) for i in range(5)]
        log = EventLog()
        for e in originals:
            log.record(e)
        engine.replay(log)

        for orig, replayed in zip(originals, received):
            assert orig is replayed  # same object (events are immutable frozen dataclasses)


# ──────────────────────────────────────────────────────────────────────
# DeterminismVerifier
# ──────────────────────────────────────────────────────────────────────

class TestDeterminismVerifier:
    def _make_bus_and_verifier(self):
        bus = EventBus()
        verifier = DeterminismVerifier(bus, TickEvent)
        return bus, verifier

    def test_runs_match_for_identical_events(self):
        bus, verifier = self._make_bus_and_verifier()

        verifier.start_capture("run1")
        bus.publish(_tick(symbol="AAPL", price=100.0))
        bus.publish(_tick(symbol="AAPL", price=101.0))
        verifier.stop_capture()

        verifier.start_capture("run2")
        bus.publish(_tick(symbol="AAPL", price=100.0))
        bus.publish(_tick(symbol="AAPL", price=101.0))
        verifier.stop_capture()

        assert verifier.runs_match("run1", "run2")

    def test_runs_differ_on_different_prices(self):
        bus, verifier = self._make_bus_and_verifier()

        verifier.start_capture("run1")
        bus.publish(_tick(price=100.0))
        verifier.stop_capture()

        verifier.start_capture("run2")
        bus.publish(_tick(price=200.0))
        verifier.stop_capture()

        assert not verifier.runs_match("run1", "run2")

    def test_runs_differ_on_event_count_mismatch(self):
        bus, verifier = self._make_bus_and_verifier()

        verifier.start_capture("run1")
        bus.publish(_tick())
        bus.publish(_tick())
        verifier.stop_capture()

        verifier.start_capture("run2")
        bus.publish(_tick())
        verifier.stop_capture()

        assert not verifier.runs_match("run1", "run2")

    def test_runs_differ_on_event_type_mismatch(self):
        bus = EventBus()
        verifier = DeterminismVerifier(bus, StreamEvent)

        verifier.start_capture("run1")
        bus.publish(_tick())
        verifier.stop_capture()

        verifier.start_capture("run2")
        bus.publish(_candle())
        verifier.stop_capture()

        assert not verifier.runs_match("run1", "run2")

    def test_uuid_event_ids_differ_but_runs_match(self):
        """Two runs with identical logic but different UUIDs should still match."""
        bus, verifier = self._make_bus_and_verifier()

        verifier.start_capture("run1")
        bus.publish(_tick(price=100.0))
        verifier.stop_capture()

        verifier.start_capture("run2")
        bus.publish(_tick(price=100.0))
        verifier.stop_capture()

        # event_ids will differ (uuid4), but compare_event_id=False by default
        assert verifier.runs_match("run1", "run2", compare_event_id=False)

    def test_compare_event_id_true_forces_mismatch(self):
        """With compare_event_id=True, two fresh events should NOT match."""
        bus, verifier = self._make_bus_and_verifier()

        verifier.start_capture("run1")
        bus.publish(_tick(price=100.0))
        verifier.stop_capture()

        verifier.start_capture("run2")
        bus.publish(_tick(price=100.0))
        verifier.stop_capture()

        assert not verifier.runs_match("run1", "run2", compare_event_id=True)

    def test_get_run_returns_captured_events(self):
        bus, verifier = self._make_bus_and_verifier()
        verifier.start_capture("run1")
        bus.publish(_tick())
        bus.publish(_tick())
        verifier.stop_capture()
        run = verifier.get_run("run1")
        assert len(run) == 2

    def test_empty_run_matches_empty_run(self):
        bus, verifier = self._make_bus_and_verifier()
        verifier.start_capture("r1")
        verifier.stop_capture()
        verifier.start_capture("r2")
        verifier.stop_capture()
        assert verifier.runs_match("r1", "r2")

    def test_stop_capture_twice_is_safe(self):
        bus, verifier = self._make_bus_and_verifier()
        verifier.start_capture("r1")
        bus.publish(_tick())
        verifier.stop_capture()
        verifier.stop_capture()  # second call should be no-op

    def test_capture_only_subscribes_correct_type(self):
        bus = EventBus()
        verifier = DeterminismVerifier(bus, TickEvent)

        verifier.start_capture("r1")
        bus.publish(_candle())  # candle, not tick
        verifier.stop_capture()

        run = verifier.get_run("r1")
        assert len(run) == 0


# ──────────────────────────────────────────────────────────────────────
# Stress test — large volume replay
# ──────────────────────────────────────────────────────────────────────

class TestReplayStress:
    def test_10k_events_replay_deterministically(self):
        bus = EventBus()
        received: list[TickEvent] = []
        bus.subscribe(TickEvent, received.append)
        engine = ReplayEngine(bus)

        log = EventLog()
        originals = [_tick(price=100.0 + i) for i in range(10_000)]
        for e in originals:
            log.record(e)

        count = engine.replay(log, speed=0.0)
        assert count == 10_000
        assert len(received) == 10_000

        for i, (orig, recv) in enumerate(zip(originals, received)):
            assert recv.price == orig.price, f"Mismatch at index {i}"

    def test_determinism_verifier_stress_with_1k_events(self):
        bus = EventBus()
        verifier = DeterminismVerifier(bus, TickEvent)

        # Use fixed prices AND fixed timestamps for deterministic comparison
        prices = [100.0 + (i % 50) for i in range(1000)]

        verifier.start_capture("r1")
        for p in prices:
            bus.publish(_tick(price=p))  # _tick uses _FIXED_TS
        verifier.stop_capture()

        verifier.start_capture("r2")
        for p in prices:
            bus.publish(_tick(price=p))
        verifier.stop_capture()

        assert verifier.runs_match("r1", "r2")

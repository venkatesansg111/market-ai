"""Unit tests for streaming.event_bus — EventBus."""
from __future__ import annotations

import threading
import time
from decimal import Decimal
from datetime import datetime

import pytest

from streaming.event_bus import EventBus
from streaming.event_models import (
    StreamEvent, TickEvent, CandleEvent, SignalEvent,
    IndicatorEvent, FillEvent, PortfolioEvent,
)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _tick(symbol: str = "AAPL", price: float = 100.0) -> TickEvent:
    return TickEvent(symbol=symbol, price=Decimal(str(price)), volume=10)


def _candle(symbol: str = "AAPL") -> CandleEvent:
    return CandleEvent(
        symbol=symbol, timeframe="1m",
        open=Decimal("100"), high=Decimal("101"),
        low=Decimal("99"), close=Decimal("100.5"),
        volume=1000, is_closed=True,
    )


# ──────────────────────────────────────────────────────────────────────
# Basic subscription
# ──────────────────────────────────────────────────────────────────────

class TestSubscription:
    def test_subscribe_and_receive(self):
        bus = EventBus()
        received = []
        bus.subscribe(TickEvent, received.append)
        bus.publish(_tick())
        assert len(received) == 1
        assert isinstance(received[0], TickEvent)

    def test_unsubscribe_stops_delivery(self):
        bus = EventBus()
        received = []
        bus.subscribe(TickEvent, received.append)
        bus.unsubscribe(TickEvent, received.append)
        bus.publish(_tick())
        assert received == []

    def test_unsubscribe_nonexistent_is_silent(self):
        bus = EventBus()
        bus.unsubscribe(TickEvent, lambda e: None)  # should not raise

    def test_duplicate_subscription_is_ignored(self):
        bus = EventBus()
        received = []
        handler = received.append
        bus.subscribe(TickEvent, handler)
        bus.subscribe(TickEvent, handler)  # duplicate
        bus.publish(_tick())
        assert len(received) == 1

    def test_subscriber_count(self):
        bus = EventBus()
        bus.subscribe(TickEvent, lambda e: None)
        bus.subscribe(TickEvent, lambda e: None)
        assert bus.subscriber_count(TickEvent) == 2

    def test_clear_subscriptions_specific_type(self):
        bus = EventBus()
        received = []
        bus.subscribe(TickEvent, received.append)
        bus.subscribe(CandleEvent, received.append)
        bus.clear_subscriptions(TickEvent)
        bus.publish(_tick())
        assert received == []
        bus.publish(_candle())
        assert len(received) == 1

    def test_clear_all_subscriptions(self):
        bus = EventBus()
        received = []
        bus.subscribe(TickEvent, received.append)
        bus.subscribe(CandleEvent, received.append)
        bus.clear_subscriptions()
        bus.publish(_tick())
        bus.publish(_candle())
        assert received == []


# ──────────────────────────────────────────────────────────────────────
# MRO-based routing
# ──────────────────────────────────────────────────────────────────────

class TestMRORouting:
    def test_parent_subscription_receives_child_events(self):
        bus = EventBus()
        received = []
        bus.subscribe(StreamEvent, received.append)
        bus.publish(_tick())
        assert len(received) == 1
        assert isinstance(received[0], TickEvent)

    def test_child_subscription_does_not_receive_sibling(self):
        bus = EventBus()
        tick_received = []
        candle_received = []
        bus.subscribe(TickEvent, tick_received.append)
        bus.subscribe(CandleEvent, candle_received.append)
        bus.publish(_tick())
        assert len(tick_received) == 1
        assert candle_received == []

    def test_handler_called_once_when_subscribed_to_parent_and_child(self):
        bus = EventBus()
        call_count = [0]

        def handler(e):
            call_count[0] += 1

        bus.subscribe(StreamEvent, handler)
        bus.subscribe(TickEvent, handler)
        bus.publish(_tick())
        assert call_count[0] == 1  # deduplication

    def test_multiple_levels_of_inheritance(self):
        bus = EventBus()
        received = []
        bus.subscribe(StreamEvent, received.append)
        bus.publish(_candle())
        assert len(received) == 1
        assert isinstance(received[0], CandleEvent)


# ──────────────────────────────────────────────────────────────────────
# Multi-handler dispatch
# ──────────────────────────────────────────────────────────────────────

class TestMultiHandler:
    def test_multiple_handlers_all_called(self):
        bus = EventBus()
        a, b, c = [], [], []
        bus.subscribe(TickEvent, a.append)
        bus.subscribe(TickEvent, b.append)
        bus.subscribe(TickEvent, c.append)
        bus.publish(_tick())
        assert len(a) == len(b) == len(c) == 1

    def test_handler_order_preserved(self):
        bus = EventBus()
        order = []
        bus.subscribe(TickEvent, lambda e: order.append(1))
        bus.subscribe(TickEvent, lambda e: order.append(2))
        bus.subscribe(TickEvent, lambda e: order.append(3))
        bus.publish(_tick())
        assert order == [1, 2, 3]

    def test_publish_returns_dispatched_count(self):
        bus = EventBus()
        bus.subscribe(TickEvent, lambda e: None)
        bus.subscribe(TickEvent, lambda e: None)
        count = bus.publish(_tick())
        assert count == 2


# ──────────────────────────────────────────────────────────────────────
# Exception isolation
# ──────────────────────────────────────────────────────────────────────

class TestExceptionIsolation:
    def test_failing_handler_does_not_block_others(self):
        bus = EventBus()
        received = []

        def bad_handler(e):
            raise RuntimeError("boom")

        bus.subscribe(TickEvent, bad_handler)
        bus.subscribe(TickEvent, received.append)
        bus.publish(_tick())
        assert len(received) == 1

    def test_error_count_incremented_on_failure(self):
        bus = EventBus()
        bus.subscribe(TickEvent, lambda e: (_ for _ in ()).throw(ValueError("err")))
        bus.publish(_tick())
        assert bus.error_count == 1

    def test_error_count_not_incremented_on_success(self):
        bus = EventBus()
        bus.subscribe(TickEvent, lambda e: None)
        bus.publish(_tick())
        assert bus.error_count == 0


# ──────────────────────────────────────────────────────────────────────
# Publish metrics
# ──────────────────────────────────────────────────────────────────────

class TestMetrics:
    def test_publish_count_increments(self):
        bus = EventBus()
        bus.publish(_tick())
        bus.publish(_tick())
        assert bus.publish_count == 2

    def test_reset_metrics(self):
        bus = EventBus()
        bus.publish(_tick())
        bus.reset_metrics()
        assert bus.publish_count == 0
        assert bus.error_count == 0

    def test_no_subscribers_publish_returns_zero(self):
        bus = EventBus()
        count = bus.publish(_tick())
        assert count == 0


# ──────────────────────────────────────────────────────────────────────
# Event log
# ──────────────────────────────────────────────────────────────────────

class TestEventLog:
    def test_event_log_disabled_by_default(self):
        bus = EventBus()
        bus.publish(_tick())
        assert bus.get_event_log() == []

    def test_event_log_captures_when_enabled(self):
        bus = EventBus(enable_log=True)
        bus.publish(_tick())
        bus.publish(_candle())
        log = bus.get_event_log()
        assert len(log) == 2

    def test_event_log_filter_by_type(self):
        bus = EventBus(enable_log=True)
        bus.publish(_tick())
        bus.publish(_candle())
        ticks = bus.get_event_log(TickEvent)
        assert len(ticks) == 1
        assert isinstance(ticks[0], TickEvent)

    def test_clear_event_log(self):
        bus = EventBus(enable_log=True)
        bus.publish(_tick())
        bus.clear_event_log()
        assert bus.get_event_log() == []


# ──────────────────────────────────────────────────────────────────────
# Thread safety
# ──────────────────────────────────────────────────────────────────────

class TestThreadSafety:
    def test_concurrent_subscribe_publish_no_errors(self):
        bus = EventBus()
        received = []
        lock = threading.Lock()
        errors = []

        def subscriber():
            try:
                bus.subscribe(TickEvent, lambda e: None)
            except Exception as exc:
                with lock:
                    errors.append(exc)

        def publisher():
            try:
                for _ in range(100):
                    bus.publish(_tick())
            except Exception as exc:
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=subscriber) for _ in range(5)]
        threads += [threading.Thread(target=publisher) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"

    def test_concurrent_publish_all_delivered(self):
        bus = EventBus()
        received = []
        lock = threading.Lock()

        def handler(e):
            with lock:
                received.append(e)

        bus.subscribe(TickEvent, handler)

        def publish_batch():
            for _ in range(50):
                bus.publish(_tick())

        threads = [threading.Thread(target=publish_batch) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(received) == 200

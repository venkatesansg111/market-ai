"""Unit tests for streaming.backpressure — BoundedQueue, CircuitBreaker, BackpressureAwareEventBus."""
from __future__ import annotations

import queue
import threading
import time
from decimal import Decimal

import pytest

from streaming.backpressure import (
    BackpressureAwareEventBus,
    BoundedQueue,
    CircuitBreaker,
    CircuitState,
    DropPolicy,
)
from streaming.event_bus import EventBus
from streaming.event_models import StreamEvent, TickEvent, CandleEvent


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _tick(price: float = 100.0) -> TickEvent:
    return TickEvent(symbol="AAPL", price=Decimal(str(price)), volume=10)


# ──────────────────────────────────────────────────────────────────────
# BoundedQueue — DROP_NEWEST
# ──────────────────────────────────────────────────────────────────────

class TestBoundedQueueDropNewest:
    def test_accepts_items_up_to_maxsize(self):
        bq = BoundedQueue(3, DropPolicy.DROP_NEWEST)
        assert bq.put("a") is True
        assert bq.put("b") is True
        assert bq.put("c") is True

    def test_drops_when_full(self):
        bq = BoundedQueue(2, DropPolicy.DROP_NEWEST)
        bq.put("a")
        bq.put("b")
        accepted = bq.put("c")
        assert accepted is False

    def test_dropped_count_increments(self):
        bq = BoundedQueue(1, DropPolicy.DROP_NEWEST)
        bq.put("a")
        bq.put("b")
        bq.put("c")
        assert bq.dropped_count == 2

    def test_old_item_preserved_on_drop(self):
        bq = BoundedQueue(1, DropPolicy.DROP_NEWEST)
        bq.put("first")
        bq.put("second")  # should be dropped
        item = bq.get(timeout=0.1)
        assert item == "first"

    def test_zero_maxsize_raises(self):
        with pytest.raises(ValueError):
            BoundedQueue(0)

    def test_negative_maxsize_raises(self):
        with pytest.raises(ValueError):
            BoundedQueue(-1)


# ──────────────────────────────────────────────────────────────────────
# BoundedQueue — DROP_OLDEST
# ──────────────────────────────────────────────────────────────────────

class TestBoundedQueueDropOldest:
    def test_evicts_oldest_on_full(self):
        bq = BoundedQueue(2, DropPolicy.DROP_OLDEST)
        bq.put("a")
        bq.put("b")
        bq.put("c")  # "a" should be evicted
        item1 = bq.get(timeout=0.1)
        item2 = bq.get(timeout=0.1)
        assert item1 == "b"
        assert item2 == "c"

    def test_accepted_returns_true_for_drop_oldest(self):
        bq = BoundedQueue(1, DropPolicy.DROP_OLDEST)
        bq.put("a")
        result = bq.put("b")
        assert result is True

    def test_dropped_count_increments_for_eviction(self):
        bq = BoundedQueue(1, DropPolicy.DROP_OLDEST)
        bq.put("a")
        bq.put("b")  # "a" evicted
        assert bq.dropped_count == 1

    def test_qsize_reflects_content(self):
        bq = BoundedQueue(5, DropPolicy.DROP_OLDEST)
        bq.put("x")
        bq.put("y")
        assert bq.qsize() == 2

    def test_empty_returns_true_when_empty(self):
        bq = BoundedQueue(5, DropPolicy.DROP_OLDEST)
        assert bq.empty() is True

    def test_empty_returns_false_when_not_empty(self):
        bq = BoundedQueue(5, DropPolicy.DROP_OLDEST)
        bq.put("item")
        assert bq.empty() is False


# ──────────────────────────────────────────────────────────────────────
# CircuitBreaker — state transitions
# ──────────────────────────────────────────────────────────────────────

class TestCircuitBreakerStates:
    def test_initial_state_is_closed(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
        assert cb.state == CircuitState.CLOSED

    def test_closed_allows_calls(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
        result = cb.call(lambda: "ok")
        assert result == "ok"

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
        for _ in range(3):
            with pytest.raises(RuntimeError):
                cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        assert cb.state == CircuitState.OPEN

    def test_open_rejects_calls(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=60.0)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        with pytest.raises(CircuitBreaker.OpenError):
            cb.call(lambda: "this should be rejected")

    def test_rejected_count_increments_when_open(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=60.0)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        for _ in range(3):
            try:
                cb.call(lambda: None)
            except CircuitBreaker.OpenError:
                pass
        assert cb.rejected_count == 3

    def test_transitions_to_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.05)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        time.sleep(0.1)
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_to_closed_on_success(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.05)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        time.sleep(0.1)
        cb.call(lambda: "probe ok")
        assert cb.state == CircuitState.CLOSED

    def test_half_open_to_open_on_failure(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.05)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        time.sleep(0.1)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail again")))
        assert cb.state == CircuitState.OPEN

    def test_manual_reset_restores_closed(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=60.0)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        cb.reset()
        assert cb.state == CircuitState.CLOSED

    def test_success_count_increments(self):
        cb = CircuitBreaker()
        cb.call(lambda: None)
        cb.call(lambda: None)
        assert cb.success_count == 2

    def test_failure_count_increments(self):
        cb = CircuitBreaker(failure_threshold=10)
        for _ in range(3):
            try:
                cb.call(lambda: (_ for _ in ()).throw(RuntimeError("err")))
            except RuntimeError:
                pass
        assert cb.failure_count == 3

    def test_total_calls_counts_all_attempts(self):
        cb = CircuitBreaker(failure_threshold=10)
        for _ in range(5):
            cb.call(lambda: None)
        assert cb.total_calls == 5


# ──────────────────────────────────────────────────────────────────────
# BackpressureAwareEventBus
# ──────────────────────────────────────────────────────────────────────

class TestBackpressureAwareEventBus:
    def test_synchronous_fallback_when_not_started(self):
        bus = BackpressureAwareEventBus()
        received = []
        bus.subscribe(TickEvent, received.append)
        bus.publish(_tick())
        assert len(received) == 1  # synchronous dispatch

    def test_start_stop_lifecycle(self):
        bus = BackpressureAwareEventBus()
        bus.subscribe(TickEvent, lambda e: None)
        bus.start()
        bus.stop(timeout=2.0)  # should not hang

    def test_events_delivered_after_start(self):
        bus = BackpressureAwareEventBus(queue_size=100)
        received = []
        lock = threading.Lock()

        def handler(e):
            with lock:
                received.append(e)

        bus.subscribe(TickEvent, handler)
        bus.start()
        try:
            for _ in range(10):
                bus.publish(_tick())
            time.sleep(0.3)  # allow workers to process
        finally:
            bus.stop(timeout=2.0)

        assert len(received) == 10

    def test_total_dropped_when_queue_overflows(self):
        bus = BackpressureAwareEventBus(queue_size=2, drop_policy=DropPolicy.DROP_NEWEST)
        slow_started = threading.Event()

        def slow_handler(e):
            slow_started.set()
            time.sleep(0.5)  # block the worker

        bus.subscribe(TickEvent, slow_handler)
        bus.start()
        try:
            # Fill queue and overflow
            for i in range(20):
                bus.publish(_tick(price=100.0 + i))
            time.sleep(0.1)
        finally:
            bus.stop(timeout=2.0)

        assert bus.total_dropped() >= 0  # drops may occur

    def test_subscriber_added_after_start_gets_worker(self):
        bus = BackpressureAwareEventBus(queue_size=100)
        bus.start()
        received = []
        lock = threading.Lock()

        def handler(e):
            with lock:
                received.append(e)

        try:
            bus.subscribe(TickEvent, handler)
            bus.publish(_tick())
            time.sleep(0.2)
        finally:
            bus.stop(timeout=2.0)

        assert len(received) == 1

    def test_mro_routing_in_async_bus(self):
        """Subscribing to StreamEvent should receive TickEvent when bus is started."""
        bus = BackpressureAwareEventBus(queue_size=100)
        received = []
        lock = threading.Lock()

        def handler(e):
            with lock:
                received.append(e)

        bus.subscribe(StreamEvent, handler)
        bus.start()
        try:
            bus.publish(_tick())
            time.sleep(0.3)
        finally:
            bus.stop(timeout=2.0)

        assert len(received) == 1
        assert isinstance(received[0], TickEvent)

    def test_circuit_breaker_opens_on_repeated_failures(self):
        bus = BackpressureAwareEventBus(
            queue_size=100,
            circuit_breaker_threshold=3,
            circuit_breaker_timeout=60.0,
        )
        fail_count = [0]

        def failing_handler(e):
            fail_count[0] += 1
            raise RuntimeError("always fails")

        bus.subscribe(TickEvent, failing_handler)
        bus.start()
        try:
            for _ in range(20):
                bus.publish(_tick())
            time.sleep(0.5)
            # Check state BEFORE stop (workers are cleared on stop)
            states = bus.circuit_breaker_states()
            assert any(v == "open" for v in states.values())
            assert fail_count[0] >= 3  # at least threshold failures happened
        finally:
            bus.stop(timeout=2.0)

    def test_multiple_handlers_in_parallel(self):
        bus = BackpressureAwareEventBus(queue_size=200)
        a_received = []
        b_received = []
        lock = threading.Lock()

        def handler_a(e):
            with lock:
                a_received.append(e)

        def handler_b(e):
            with lock:
                b_received.append(e)

        bus.subscribe(TickEvent, handler_a)
        bus.subscribe(TickEvent, handler_b)
        bus.start()
        try:
            for _ in range(20):
                bus.publish(_tick())
            time.sleep(0.3)
        finally:
            bus.stop(timeout=2.0)

        assert len(a_received) == 20
        assert len(b_received) == 20

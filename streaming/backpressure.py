"""Phase 9 — Backpressure + Failure Handling: BoundedQueue, CircuitBreaker, BackpressureAwareEventBus."""
from __future__ import annotations

import logging
import queue
import threading
import time
from enum import Enum
from typing import Any, Callable, Optional

from streaming.event_bus import EventBus
from streaming.event_models import StreamEvent

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Drop Policies
# ──────────────────────────────────────────────────────────────────────

class DropPolicy(str, Enum):
    DROP_NEWEST = "drop_newest"   # reject new item when full
    DROP_OLDEST = "drop_oldest"   # evict oldest item to make room


# ──────────────────────────────────────────────────────────────────────
# Bounded Queue
# ──────────────────────────────────────────────────────────────────────

class BoundedQueue:
    """
    Thread-safe bounded queue with configurable drop policy.

    - DROP_NEWEST: incoming item is discarded when the queue is full.
    - DROP_OLDEST: the oldest item is evicted to make room.

    `dropped_count` tracks cumulative drops since creation.
    """

    def __init__(self, maxsize: int, policy: DropPolicy = DropPolicy.DROP_NEWEST) -> None:
        if maxsize <= 0:
            raise ValueError("maxsize must be positive")
        self._q: queue.Queue = queue.Queue(maxsize=maxsize)
        self._policy = policy
        self._maxsize = maxsize
        self._dropped: int = 0
        self._lock = threading.Lock()

    def put(self, item: Any) -> bool:
        """
        Enqueue item.  Returns True if accepted, False if dropped.
        """
        try:
            self._q.put_nowait(item)
            return True
        except queue.Full:
            with self._lock:
                self._dropped += 1
            if self._policy == DropPolicy.DROP_OLDEST:
                try:
                    self._q.get_nowait()    # discard oldest
                except queue.Empty:
                    pass
                try:
                    self._q.put_nowait(item)
                    return True
                except queue.Full:
                    pass
            logger.debug("BoundedQueue: dropped item (policy=%s)", self._policy.value)
            return False

    def get(self, timeout: Optional[float] = None) -> Any:
        """Dequeue item, blocking up to `timeout` seconds (None = block forever)."""
        return self._q.get(timeout=timeout)

    def task_done(self) -> None:
        self._q.task_done()

    def empty(self) -> bool:
        return self._q.empty()

    def qsize(self) -> int:
        return self._q.qsize()

    @property
    def dropped_count(self) -> int:
        return self._dropped

    @property
    def maxsize(self) -> int:
        return self._maxsize


# ──────────────────────────────────────────────────────────────────────
# Circuit Breaker
# ──────────────────────────────────────────────────────────────────────

class CircuitState(str, Enum):
    CLOSED = "closed"           # normal operation
    OPEN = "open"               # failing — reject calls
    HALF_OPEN = "half_open"     # probe — allow one call to test recovery


class CircuitBreaker:
    """
    Classic three-state circuit breaker.

    CLOSED  → OPEN   : after `failure_threshold` consecutive failures
    OPEN    → HALF_OPEN: after `recovery_timeout` seconds
    HALF_OPEN → CLOSED  : on successful call
    HALF_OPEN → OPEN    : on failed call (reset timer)

    Usage:
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)
        result = cb.call(my_function, arg1, arg2)
    """

    class OpenError(RuntimeError):
        """Raised when call is rejected because the breaker is OPEN."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        name: str = "breaker",
    ) -> None:
        self._threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._name = name

        self._state = CircuitState.CLOSED
        self._failure_count: int = 0
        self._last_failure_time: Optional[float] = None
        self._success_count: int = 0
        self._total_calls: int = 0
        self._rejected_count: int = 0
        self._lock = threading.Lock()

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """
        Execute `func(*args, **kwargs)` through the circuit breaker.

        Raises CircuitBreaker.OpenError if state is OPEN (and timeout
        has not elapsed yet).
        """
        with self._lock:
            state = self._get_state()

        if state == CircuitState.OPEN:
            with self._lock:
                self._rejected_count += 1
            logger.debug("CircuitBreaker[%s]: call rejected (OPEN)", self._name)
            raise CircuitBreaker.OpenError(
                f"CircuitBreaker '{self._name}' is OPEN — call rejected"
            )

        # CLOSED or HALF_OPEN: attempt the call
        with self._lock:
            self._total_calls += 1

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as exc:
            self._on_failure()
            raise

    def reset(self) -> None:
        """Manually reset to CLOSED state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = None

    # ──────────────────────────────────────────────────────────────────
    # Properties
    # ──────────────────────────────────────────────────────────────────

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._get_state()

    @property
    def failure_count(self) -> int:
        return self._failure_count

    @property
    def success_count(self) -> int:
        return self._success_count

    @property
    def total_calls(self) -> int:
        return self._total_calls

    @property
    def rejected_count(self) -> int:
        return self._rejected_count

    # ──────────────────────────────────────────────────────────────────
    # Internal
    # ──────────────────────────────────────────────────────────────────

    def _get_state(self) -> CircuitState:
        """Return effective state (may auto-transition OPEN → HALF_OPEN)."""
        if self._state == CircuitState.OPEN:
            if (
                self._last_failure_time is not None
                and time.monotonic() - self._last_failure_time >= self._recovery_timeout
            ):
                self._state = CircuitState.HALF_OPEN
                logger.info("CircuitBreaker[%s]: OPEN → HALF_OPEN (probe)", self._name)
        return self._state

    def _on_success(self) -> None:
        with self._lock:
            self._success_count += 1
            if self._state in (CircuitState.HALF_OPEN, CircuitState.CLOSED):
                self._failure_count = 0
                if self._state == CircuitState.HALF_OPEN:
                    self._state = CircuitState.CLOSED
                    logger.info(
                        "CircuitBreaker[%s]: HALF_OPEN → CLOSED (recovered)", self._name
                    )

    def _on_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning(
                    "CircuitBreaker[%s]: HALF_OPEN → OPEN (probe failed)", self._name
                )
            elif (
                self._state == CircuitState.CLOSED
                and self._failure_count >= self._threshold
            ):
                self._state = CircuitState.OPEN
                logger.warning(
                    "CircuitBreaker[%s]: CLOSED → OPEN (%d failures)",
                    self._name, self._failure_count,
                )


# ──────────────────────────────────────────────────────────────────────
# Backpressure-Aware Event Bus
# ──────────────────────────────────────────────────────────────────────

_SENTINEL = object()  # signals worker thread to stop


class BackpressureAwareEventBus(EventBus):
    """
    EventBus variant that dispatches to each handler in its own worker
    thread through a BoundedQueue.

    - Non-blocking publish: publisher never blocks waiting for slow handlers.
    - Per-handler isolation: one slow/failing handler doesn't affect others.
    - Optional CircuitBreaker per handler: disable broken handlers automatically.

    Lifecycle:
        bus = BackpressureAwareEventBus(queue_size=1000)
        bus.start()
        ...
        bus.stop()

    The `subscribe()` API is inherited from EventBus; workers are created
    on `start()`.  Handlers registered after `start()` also get a worker.
    """

    def __init__(
        self,
        queue_size: int = 1000,
        drop_policy: DropPolicy = DropPolicy.DROP_OLDEST,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_timeout: float = 30.0,
    ) -> None:
        super().__init__()
        self._queue_size = queue_size
        self._drop_policy = drop_policy
        self._cb_threshold = circuit_breaker_threshold
        self._cb_timeout = circuit_breaker_timeout

        self._running = False
        # handler_id → (BoundedQueue, Thread, CircuitBreaker)
        self._workers: dict[int, tuple[BoundedQueue, threading.Thread, CircuitBreaker]] = {}
        self._workers_lock = threading.Lock()

    # ──────────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start per-handler worker threads for all currently registered handlers."""
        with self._workers_lock:
            self._running = True
        # Prime workers for any handlers already subscribed
        all_handlers = self._all_handlers()
        for handler in all_handlers:
            self._ensure_worker(handler)
        logger.debug("BackpressureAwareEventBus: started (%d workers)", len(self._workers))

    def stop(self, timeout: float = 5.0) -> None:
        """Stop all worker threads gracefully."""
        with self._workers_lock:
            self._running = False
            workers_snapshot = dict(self._workers)

        for hid, (bq, thread, _cb) in workers_snapshot.items():
            bq.put(_SENTINEL)

        for hid, (bq, thread, _cb) in workers_snapshot.items():
            thread.join(timeout=timeout)

        with self._workers_lock:
            self._workers.clear()

        logger.debug("BackpressureAwareEventBus: stopped")

    # ──────────────────────────────────────────────────────────────────
    # Override subscribe to auto-wire worker when running
    # ──────────────────────────────────────────────────────────────────

    def subscribe(self, event_type: type, handler) -> None:
        super().subscribe(event_type, handler)
        if self._running:
            self._ensure_worker(handler)

    # ──────────────────────────────────────────────────────────────────
    # Override publish to enqueue rather than direct-call
    # ──────────────────────────────────────────────────────────────────

    def publish(self, event: StreamEvent) -> int:
        if not self._running:
            # Fall back to synchronous dispatch when not started
            return super().publish(event)

        handlers = self._collect_handlers(event)
        dispatched = 0
        for handler in handlers:
            hid = id(handler)
            with self._workers_lock:
                if hid not in self._workers:
                    self._ensure_worker(handler)
                bq, _, _ = self._workers[hid]
            accepted = bq.put(event)
            if accepted:
                dispatched += 1
            else:
                logger.warning(
                    "BackpressureAwareEventBus: queue full for handler %r, event dropped",
                    getattr(handler, "__name__", repr(handler)),
                )
        self._publish_count += 1
        return dispatched

    # ──────────────────────────────────────────────────────────────────
    # Metrics
    # ──────────────────────────────────────────────────────────────────

    def total_dropped(self) -> int:
        with self._workers_lock:
            return sum(bq.dropped_count for bq, _, _ in self._workers.values())

    def queue_sizes(self) -> dict[str, int]:
        with self._workers_lock:
            return {
                getattr(h, "__name__", str(hid)): bq.qsize()
                for hid, (bq, _, _) in self._workers.items()
                for h in [self._handler_by_id(hid)]
                if h is not None
            }

    def circuit_breaker_states(self) -> dict[str, str]:
        with self._workers_lock:
            return {
                getattr(h, "__name__", str(hid)): cb.state.value
                for hid, (_, _, cb) in self._workers.items()
                for h in [self._handler_by_id(hid)]
                if h is not None
            }

    # ──────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────

    def _ensure_worker(self, handler) -> None:
        hid = id(handler)
        with self._workers_lock:
            if hid in self._workers:
                return
            bq = BoundedQueue(self._queue_size, self._drop_policy)
            cb = CircuitBreaker(
                failure_threshold=self._cb_threshold,
                recovery_timeout=self._cb_timeout,
                name=getattr(handler, "__name__", str(hid)),
            )
            thread = threading.Thread(
                target=self._worker_loop,
                args=(handler, bq, cb),
                daemon=True,
                name=f"bp-worker-{hid}",
            )
            self._workers[hid] = (bq, thread, cb)
            thread.start()

    def _worker_loop(self, handler, bq: BoundedQueue, cb: CircuitBreaker) -> None:
        while True:
            try:
                item = bq.get(timeout=0.1)
            except queue.Empty:
                if not self._running:
                    break
                continue

            if item is _SENTINEL:
                break

            try:
                cb.call(handler, item)
            except CircuitBreaker.OpenError:
                logger.warning(
                    "BackpressureAwareEventBus: handler %r circuit OPEN — event skipped",
                    getattr(handler, "__name__", repr(handler)),
                )
            except Exception as exc:
                logger.error(
                    "BackpressureAwareEventBus: handler %r raised: %s",
                    getattr(handler, "__name__", repr(handler)), exc,
                    exc_info=True,
                )
            finally:
                bq.task_done()

    def _collect_handlers(self, event: StreamEvent) -> list:
        """Collect deduplicated handlers for this event via MRO walk (mirrors EventBus.publish)."""
        seen: set[int] = set()
        result = []
        with self._lock:
            for cls in type(event).__mro__:
                for handler in self._handlers.get(cls, []):
                    hid = id(handler)
                    if hid not in seen:
                        seen.add(hid)
                        result.append(handler)
        return result

    def _all_handlers(self) -> list:
        seen: set[int] = set()
        result = []
        with self._lock:
            for handlers in self._handlers.values():
                for h in handlers:
                    hid = id(h)
                    if hid not in seen:
                        seen.add(hid)
                        result.append(h)
        return result

    def _handler_by_id(self, hid: int):
        """Reverse lookup: find handler object by id (best-effort)."""
        with self._lock:
            for handlers in self._handlers.values():
                for h in handlers:
                    if id(h) == hid:
                        return h
        return None

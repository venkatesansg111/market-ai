"""Phase 9 — Event Bus core: thread-safe synchronous pub/sub."""
from __future__ import annotations

import logging
import threading
from collections import defaultdict
from typing import Callable, Optional

from streaming.event_models import StreamEvent

logger = logging.getLogger(__name__)

Handler = Callable[[StreamEvent], None]


class EventBus:
    """
    Thread-safe synchronous pub/sub event bus.

    Design:
      - Handlers are called in the publisher's thread (synchronous dispatch).
      - MRO-based routing: subscribing to a parent type (e.g. StreamEvent) receives
        all child event types as well.
      - Handler exceptions are caught, logged, and isolated — a failing handler
        never interrupts delivery to subsequent handlers.
      - The handler list is copied before dispatch so subscribe/unsubscribe during
        a handler never causes a concurrent-modification error.
    """

    def __init__(self, enable_log: bool = False) -> None:
        self._handlers: dict[type, list[Handler]] = defaultdict(list)
        self._lock = threading.RLock()
        self._event_log: list[StreamEvent] = []
        self._enable_log = enable_log
        self._publish_count: int = 0
        self._error_count: int = 0
        self._dropped_count: int = 0

    # ──────────────────────────────────────────────────────────────────
    # Subscription management
    # ──────────────────────────────────────────────────────────────────

    def subscribe(self, event_type: type, handler: Handler) -> None:
        """Register handler for event_type (and all its subclasses via publish MRO walk)."""
        with self._lock:
            if handler not in self._handlers[event_type]:
                self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: type, handler: Handler) -> None:
        """Remove handler; silently ignores if not registered."""
        with self._lock:
            try:
                self._handlers[event_type].remove(handler)
            except ValueError:
                pass

    def subscriber_count(self, event_type: type) -> int:
        with self._lock:
            return len(self._handlers.get(event_type, []))

    def clear_subscriptions(self, event_type: type | None = None) -> None:
        with self._lock:
            if event_type is None:
                self._handlers.clear()
            else:
                self._handlers.pop(event_type, None)

    # ──────────────────────────────────────────────────────────────────
    # Publishing
    # ──────────────────────────────────────────────────────────────────

    def publish(self, event: StreamEvent) -> int:
        """
        Dispatch event to all matching handlers.

        Walk the MRO so handlers subscribed to a parent type also receive
        child events. Returns number of handlers successfully called.
        """
        if self._enable_log:
            self._event_log.append(event)

        # Collect handlers under lock (copy to avoid holding lock during dispatch)
        handlers: list[Handler] = []
        with self._lock:
            for klass in type(event).__mro__:
                if klass in self._handlers:
                    handlers.extend(self._handlers[klass])

        # Deduplicate while preserving order (same handler registered for both
        # parent and child type should only be called once)
        seen: set[int] = set()
        unique: list[Handler] = []
        for h in handlers:
            hid = id(h)
            if hid not in seen:
                seen.add(hid)
                unique.append(h)

        dispatched = 0
        for handler in unique:
            try:
                handler(event)
                dispatched += 1
            except Exception as exc:
                self._error_count += 1
                logger.error(
                    "EventBus: handler %s raised for %s: %s",
                    getattr(handler, "__name__", repr(handler)),
                    type(event).__name__,
                    exc,
                    exc_info=True,
                )

        self._publish_count += 1
        return dispatched

    # ──────────────────────────────────────────────────────────────────
    # Event log (for replay)
    # ──────────────────────────────────────────────────────────────────

    def enable_event_log(self) -> None:
        self._enable_log = True

    def disable_event_log(self) -> None:
        self._enable_log = False

    def get_event_log(self, event_type: type | None = None) -> list[StreamEvent]:
        if event_type is None:
            return list(self._event_log)
        return [e for e in self._event_log if isinstance(e, event_type)]

    def clear_event_log(self) -> None:
        self._event_log.clear()

    # ──────────────────────────────────────────────────────────────────
    # Metrics
    # ──────────────────────────────────────────────────────────────────

    @property
    def publish_count(self) -> int:
        return self._publish_count

    @property
    def error_count(self) -> int:
        return self._error_count

    def reset_metrics(self) -> None:
        self._publish_count = 0
        self._error_count = 0
        self._dropped_count = 0

"""Phase 10 — System Health Engine."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from streaming.event_bus import EventBus
from streaming.event_models import StreamEvent


@dataclass
class HealthSnapshot:
    timestamp: datetime
    publish_count: int
    error_count: int
    events_per_second: float
    active_subscriptions: int
    uptime_seconds: float
    status: str  # "healthy" | "degraded" | "unhealthy"


class SystemHealthEngine:
    """Monitors event bus throughput, error rates, and overall system health."""

    def __init__(self, bus: EventBus | None = None) -> None:
        self._bus: Optional[EventBus] = None
        self._start_time = time.monotonic()
        self._event_timestamps: list[float] = []
        self._lock = threading.RLock()
        self._snapshots: list[HealthSnapshot] = []
        if bus is not None:
            self.attach(bus)

    def attach(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe(StreamEvent, self._on_event)

    def _on_event(self, _: StreamEvent) -> None:
        now = time.monotonic()
        cutoff = now - 60.0
        with self._lock:
            self._event_timestamps.append(now)
            self._event_timestamps = [t for t in self._event_timestamps if t >= cutoff]

    def snapshot(self) -> HealthSnapshot:
        now = time.monotonic()
        uptime = now - self._start_time
        with self._lock:
            recent_window = 10.0
            cutoff = now - recent_window
            recent = sum(1 for t in self._event_timestamps if t >= cutoff)
            eps = recent / recent_window

        publish_count = self._bus.publish_count if self._bus else 0
        error_count = self._bus.error_count if self._bus else 0

        if error_count == 0:
            status = "healthy"
        elif error_count / max(publish_count, 1) < 0.05:
            status = "degraded"
        else:
            status = "unhealthy"

        sub_count = 0
        if self._bus:
            for event_type in list(getattr(self._bus, "_handlers", {}).keys()):
                sub_count += self._bus.subscriber_count(event_type)

        snap = HealthSnapshot(
            timestamp=datetime.utcnow(),
            publish_count=publish_count,
            error_count=error_count,
            events_per_second=eps,
            active_subscriptions=sub_count,
            uptime_seconds=uptime,
            status=status,
        )
        with self._lock:
            self._snapshots.append(snap)
        return snap

    def is_healthy(self) -> bool:
        return self.snapshot().status == "healthy"

    def history(self) -> list[HealthSnapshot]:
        with self._lock:
            return list(self._snapshots)

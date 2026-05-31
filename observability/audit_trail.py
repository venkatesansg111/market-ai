"""Phase 10 — Audit Trail: append-only immutable event log."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime

from streaming.event_bus import EventBus
from streaming.event_models import StreamEvent


@dataclass(frozen=True)
class AuditEntry:
    seq: int
    wall_time: float
    timestamp: datetime
    event_type: str
    event_id: str
    symbol: str
    event: StreamEvent


class AuditTrail:
    """Append-only audit trail — entries cannot be modified or removed."""

    def __init__(self, bus: EventBus | None = None) -> None:
        self._entries: list[AuditEntry] = []
        self._seq: int = 0
        self._lock = threading.RLock()
        if bus is not None:
            self.attach(bus)

    def attach(self, bus: EventBus) -> None:
        bus.subscribe(StreamEvent, self._record)

    def _record(self, event: StreamEvent) -> None:
        symbol = getattr(event, "symbol", "")
        with self._lock:
            entry = AuditEntry(
                seq=self._seq,
                wall_time=time.monotonic(),
                timestamp=datetime.utcnow(),
                event_type=type(event).__name__,
                event_id=event.event_id,
                symbol=symbol,
                event=event,
            )
            self._seq += 1
            self._entries.append(entry)

    def entries(
        self,
        event_type: str | None = None,
        symbol: str | None = None,
    ) -> list[AuditEntry]:
        with self._lock:
            result = list(self._entries)
        if event_type:
            result = [e for e in result if e.event_type == event_type]
        if symbol:
            result = [e for e in result if e.symbol == symbol]
        return result

    def entry_count(self) -> int:
        with self._lock:
            return len(self._entries)

    def is_monotonic(self) -> bool:
        with self._lock:
            times = [e.wall_time for e in self._entries]
        return all(times[i] <= times[i + 1] for i in range(len(times) - 1))

    def last_sequence(self) -> int:
        with self._lock:
            return self._seq - 1 if self._seq > 0 else -1

"""Phase 9 — Event Replay System: deterministic log-and-replay for testing/debugging."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from streaming.event_bus import EventBus
from streaming.event_models import StreamEvent

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Event Log
# ──────────────────────────────────────────────────────────────────────

@dataclass
class LogEntry:
    wall_time: float       # time.monotonic() at recording
    event: StreamEvent


class EventLog:
    """
    Ordered, append-only log of StreamEvents.

    Can be attached to an EventBus to automatically record all published
    events, or fed manually.
    """

    def __init__(self) -> None:
        self._entries: list[LogEntry] = []
        self._start_wall: Optional[float] = None

    # ──────────────────────────────────────────────────────────────────
    # Recording
    # ──────────────────────────────────────────────────────────────────

    def record(self, event: StreamEvent) -> None:
        """Append an event with a monotonic wall-clock timestamp."""
        now = time.monotonic()
        if self._start_wall is None:
            self._start_wall = now
        self._entries.append(LogEntry(wall_time=now, event=event))

    def attach_to_bus(self, bus: EventBus, event_type: type = StreamEvent) -> None:
        """Subscribe record() to an EventBus to capture all events of event_type."""
        bus.subscribe(event_type, self.record)

    def detach_from_bus(self, bus: EventBus, event_type: type = StreamEvent) -> None:
        bus.unsubscribe(event_type, self.record)

    # ──────────────────────────────────────────────────────────────────
    # Retrieval
    # ──────────────────────────────────────────────────────────────────

    def events(self, event_type: type | None = None) -> list[StreamEvent]:
        if event_type is None:
            return [e.event for e in self._entries]
        return [e.event for e in self._entries if isinstance(e.event, event_type)]

    def entries(self) -> list[LogEntry]:
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()
        self._start_wall = None


# ──────────────────────────────────────────────────────────────────────
# Replay Engine
# ──────────────────────────────────────────────────────────────────────

class ReplayEngine:
    """
    Replays a recorded EventLog through an EventBus.

    Two replay modes:
      - Instant (speed=0): all events published without delay. Fully deterministic.
      - Real-time (speed=1.0): honours original inter-event timing.
      - Fast-forward (0 < speed < 1): timing compressed.

    For regression testing, always use instant mode.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._bus = event_bus
        self._replay_count: int = 0

    def replay(
        self,
        log: EventLog,
        speed: float = 0.0,             # 0 = instant, 1.0 = real-time
        event_type: type | None = None, # None = replay all types
    ) -> int:
        """
        Replay events from log. Returns the number of events replayed.
        """
        entries = log.entries()
        if not entries:
            return 0

        if event_type is not None:
            entries = [e for e in entries if isinstance(e.event, event_type)]

        replayed = 0
        prev_wall: Optional[float] = None

        for entry in entries:
            if speed > 0 and prev_wall is not None:
                delay = (entry.wall_time - prev_wall) / speed
                if delay > 0:
                    time.sleep(delay)
            prev_wall = entry.wall_time

            self._bus.publish(entry.event)
            replayed += 1

        self._replay_count += replayed
        logger.debug("ReplayEngine: replayed %d events", replayed)
        return replayed

    @property
    def replay_count(self) -> int:
        return self._replay_count


# ──────────────────────────────────────────────────────────────────────
# Determinism verifier
# ──────────────────────────────────────────────────────────────────────

class DeterminismVerifier:
    """
    Helper that captures events from two runs and compares them.

    Usage:
        v = DeterminismVerifier()
        with v.capture_run("run1"):
            feed.run()
        with v.capture_run("run2"):
            feed.run()
        assert v.runs_match("run1", "run2")
    """

    def __init__(self, bus: EventBus, event_type: type) -> None:
        self._bus = bus
        self._event_type = event_type
        self._runs: dict[str, list[StreamEvent]] = {}
        self._current_run: Optional[str] = None
        self._buffer: list[StreamEvent] = []

    def _capture(self, event: StreamEvent) -> None:
        self._buffer.append(event)

    def start_capture(self, run_name: str) -> None:
        self._current_run = run_name
        self._buffer = []
        self._bus.subscribe(self._event_type, self._capture)

    def stop_capture(self) -> None:
        if self._current_run is not None:
            self._bus.unsubscribe(self._event_type, self._capture)
            self._runs[self._current_run] = list(self._buffer)
            self._buffer = []
            self._current_run = None

    def get_run(self, run_name: str) -> list[StreamEvent]:
        return self._runs.get(run_name, [])

    def runs_match(self, run_a: str, run_b: str, compare_event_id: bool = False) -> bool:
        """
        Compare two runs for deterministic equivalence.

        By default, event_ids are excluded from comparison (they're UUIDs
        and differ per run). Set compare_event_id=True to include them.
        """
        evs_a = self._runs.get(run_a, [])
        evs_b = self._runs.get(run_b, [])

        if len(evs_a) != len(evs_b):
            logger.debug(
                "DeterminismVerifier: %s has %d events, %s has %d",
                run_a, len(evs_a), run_b, len(evs_b),
            )
            return False

        for i, (a, b) in enumerate(zip(evs_a, evs_b)):
            if type(a) != type(b):
                logger.debug(
                    "DeterminismVerifier: event %d type mismatch %s vs %s",
                    i, type(a).__name__, type(b).__name__,
                )
                return False
            # Compare all fields except event_id (if requested)
            a_dict = a.__dict__.copy() if compare_event_id else {
                k: v for k, v in a.__dict__.items() if k != "event_id"
            }
            b_dict = b.__dict__.copy() if compare_event_id else {
                k: v for k, v in b.__dict__.items() if k != "event_id"
            }
            if a_dict != b_dict:
                logger.debug(
                    "DeterminismVerifier: event %d mismatch:\n  %s\n  %s",
                    i, a_dict, b_dict,
                )
                return False

        return True

"""Phase 9 — Market data feed: produces TickEvents into the event bus."""
from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterator, Optional

from streaming.event_bus import EventBus
from streaming.event_models import TickEvent

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Raw tick data container
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RawTick:
    symbol: str
    price: Decimal
    volume: int
    timestamp: datetime
    bid: Optional[Decimal] = None
    ask: Optional[Decimal] = None


# ──────────────────────────────────────────────────────────────────────
# Abstract producer interface
# ──────────────────────────────────────────────────────────────────────

class TickProducer(ABC):
    """Produces a stream of RawTick objects."""

    @abstractmethod
    def ticks(self) -> Iterator[RawTick]:
        """Yield ticks one at a time."""
        ...

    def is_live(self) -> bool:
        return False


# ──────────────────────────────────────────────────────────────────────
# Simulated / replay producer
# ──────────────────────────────────────────────────────────────────────

class SimulatedTickProducer(TickProducer):
    """
    Deterministic tick producer from a pre-built list.

    tick_delay_seconds=0 → instant (useful for testing/replay).
    tick_delay_seconds>0 → real-time simulation.
    """

    def __init__(
        self,
        ticks: list[RawTick],
        tick_delay_seconds: float = 0.0,
    ) -> None:
        self._ticks = list(ticks)
        self._delay = tick_delay_seconds

    def ticks(self) -> Iterator[RawTick]:
        for tick in self._ticks:
            if self._delay > 0:
                time.sleep(self._delay)
            yield tick

    def add_tick(self, tick: RawTick) -> None:
        self._ticks.append(tick)

    def __len__(self) -> int:
        return len(self._ticks)


# ──────────────────────────────────────────────────────────────────────
# Market data feed
# ──────────────────────────────────────────────────────────────────────

class MarketDataFeed:
    """
    Consumes ticks from a TickProducer, normalises them, and publishes
    TickEvents to the EventBus.

    Features:
      - Multi-symbol: all symbols on the same feed
      - Ordering integrity: per-symbol sequence tracking
      - Replay mode: producer determines ordering
      - Backpressure: caller controls publishing pace via run()
    """

    def __init__(
        self,
        event_bus: EventBus,
        producer: TickProducer,
        drop_stale: bool = True,
    ) -> None:
        self._bus = event_bus
        self._producer = producer
        self._drop_stale = drop_stale
        self._last_ts: dict[str, datetime] = {}
        self._tick_count: int = 0
        self._dropped_count: int = 0
        self._running = False
        self._thread: Optional[threading.Thread] = None

    # ──────────────────────────────────────────────────────────────────
    # Synchronous run (blocks until producer exhausted)
    # ──────────────────────────────────────────────────────────────────

    def run(self) -> None:
        """Process all ticks synchronously (blocks until producer done)."""
        self._running = True
        try:
            for raw in self._producer.ticks():
                if not self._running:
                    break
                self._process_tick(raw)
        finally:
            self._running = False

    # ──────────────────────────────────────────────────────────────────
    # Background thread mode
    # ──────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start tick processing in a background thread."""
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self.run, name="MarketDataFeed", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)

    def is_running(self) -> bool:
        return self._running

    # ──────────────────────────────────────────────────────────────────
    # Single-tick injection (for testing / manual control)
    # ──────────────────────────────────────────────────────────────────

    def inject_tick(self, raw: RawTick) -> bool:
        """Publish a single tick directly. Returns True if accepted."""
        return self._process_tick(raw)

    # ──────────────────────────────────────────────────────────────────
    # Internal
    # ──────────────────────────────────────────────────────────────────

    def _process_tick(self, raw: RawTick) -> bool:
        # Stale tick detection (per symbol)
        if self._drop_stale:
            last = self._last_ts.get(raw.symbol)
            if last is not None and raw.timestamp < last:
                self._dropped_count += 1
                logger.debug(
                    "MarketDataFeed: dropped stale tick %s @ %s (last=%s)",
                    raw.symbol, raw.timestamp, last,
                )
                return False

        self._last_ts[raw.symbol] = raw.timestamp
        self._tick_count += 1

        event = TickEvent(
            symbol=raw.symbol,
            price=raw.price,
            volume=raw.volume,
            timestamp=raw.timestamp,
            bid=raw.bid,
            ask=raw.ask,
        )
        self._bus.publish(event)
        return True

    # ──────────────────────────────────────────────────────────────────
    # Metrics
    # ──────────────────────────────────────────────────────────────────

    @property
    def tick_count(self) -> int:
        return self._tick_count

    @property
    def dropped_count(self) -> int:
        return self._dropped_count

"""Phase 9 — Real-time candle builder: Tick → OHLCV candle aggregation."""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from streaming.event_bus import EventBus
from streaming.event_models import CandleEvent, TickEvent

logger = logging.getLogger(__name__)

# Supported timeframes → seconds per interval
_TIMEFRAME_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


# ──────────────────────────────────────────────────────────────────────
# Internal candle state (mutable accumulator)
# ──────────────────────────────────────────────────────────────────────

@dataclass
class _CandleState:
    symbol: str
    timeframe: str
    bucket_start: datetime      # floored timestamp of this candle
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int = 0
    tick_count: int = 0


# ──────────────────────────────────────────────────────────────────────
# Candle Builder Engine
# ──────────────────────────────────────────────────────────────────────

class CandleBuilderEngine:
    """
    Aggregates TickEvents into OHLCV CandleEvents.

    Subscribes to TickEvent on the bus.  When a new time bucket starts
    (i.e. a tick's timestamp belongs to a different interval than the
    current candle), the current candle is closed and emitted as a
    CandleEvent(is_closed=True), then a new candle is started.

    Out-of-order tick handling:
      - Ticks with a timestamp earlier than the current candle's bucket_start
        are dropped (warning logged).

    Multi-timeframe:
      - Each (symbol, timeframe) pair is tracked independently.

    flush():
      - Forces emission of all pending (open) candles as closed events.
        Use at end-of-session or in tests.
    """

    def __init__(
        self,
        event_bus: EventBus,
        timeframes: list[str] | None = None,
        emit_live_updates: bool = False,
    ) -> None:
        self._bus = event_bus
        self._timeframes = timeframes or ["1m", "5m"]
        self._emit_live = emit_live_updates
        # (symbol, timeframe) → _CandleState
        self._pending: dict[tuple[str, str], _CandleState] = {}
        self._candle_count: int = 0
        self._tick_count: int = 0
        self._dropped_count: int = 0

        # Register with bus
        event_bus.subscribe(TickEvent, self.on_tick)

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def on_tick(self, event: TickEvent) -> None:
        """Process a single tick across all configured timeframes."""
        self._tick_count += 1
        for tf in self._timeframes:
            self._update(event, tf)

    def flush(self) -> int:
        """
        Close and emit all pending candles immediately.
        Returns the number of candles flushed.
        """
        flushed = 0
        for key in list(self._pending.keys()):
            self._emit(self._pending.pop(key), closed=True)
            flushed += 1
        return flushed

    def pending_count(self) -> int:
        return len(self._pending)

    # ──────────────────────────────────────────────────────────────────
    # Internal
    # ──────────────────────────────────────────────────────────────────

    def _update(self, tick: TickEvent, timeframe: str) -> None:
        key = (tick.symbol, timeframe)
        bucket = _bucket_start(tick.timestamp, timeframe)

        if key not in self._pending:
            # First tick for this (symbol, timeframe): start new candle
            self._pending[key] = _CandleState(
                symbol=tick.symbol,
                timeframe=timeframe,
                bucket_start=bucket,
                open=tick.price,
                high=tick.price,
                low=tick.price,
                close=tick.price,
                volume=tick.volume,
                tick_count=1,
            )
        else:
            state = self._pending[key]

            if bucket < state.bucket_start:
                # Out-of-order tick — drop
                self._dropped_count += 1
                logger.warning(
                    "CandleBuilder: out-of-order tick %s %s (tick=%s < candle=%s); dropped",
                    tick.symbol, timeframe, tick.timestamp, state.bucket_start,
                )
                return

            if bucket > state.bucket_start:
                # New bucket — close current candle and start fresh
                self._emit(state, closed=True)
                del self._pending[key]
                self._pending[key] = _CandleState(
                    symbol=tick.symbol,
                    timeframe=timeframe,
                    bucket_start=bucket,
                    open=tick.price,
                    high=tick.price,
                    low=tick.price,
                    close=tick.price,
                    volume=tick.volume,
                    tick_count=1,
                )
            else:
                # Same bucket — update OHLCV
                state.high = max(state.high, tick.price)
                state.low = min(state.low, tick.price)
                state.close = tick.price
                state.volume += tick.volume
                state.tick_count += 1

                if self._emit_live:
                    self._emit(state, closed=False)

    def _emit(self, state: _CandleState, closed: bool) -> None:
        event = CandleEvent(
            symbol=state.symbol,
            timeframe=state.timeframe,
            open=state.open,
            high=state.high,
            low=state.low,
            close=state.close,
            volume=state.volume,
            is_closed=closed,
            candle_open_time=state.bucket_start,
        )
        self._bus.publish(event)
        if closed:
            self._candle_count += 1
            logger.debug(
                "CandleBuilder: emitted %s %s O=%s H=%s L=%s C=%s V=%d",
                state.symbol, state.timeframe,
                state.open, state.high, state.low, state.close, state.volume,
            )

    # ──────────────────────────────────────────────────────────────────
    # Metrics
    # ──────────────────────────────────────────────────────────────────

    @property
    def candle_count(self) -> int:
        return self._candle_count

    @property
    def tick_count(self) -> int:
        return self._tick_count

    @property
    def dropped_count(self) -> int:
        return self._dropped_count


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _bucket_start(ts: datetime, timeframe: str) -> datetime:
    """Floor ts to the nearest interval boundary (UTC epoch aligned)."""
    interval = _TIMEFRAME_SECONDS.get(timeframe)
    if interval is None:
        raise ValueError(f"Unknown timeframe: {timeframe!r}")
    epoch = ts.timestamp()
    floored = math.floor(epoch / interval) * interval
    return datetime.utcfromtimestamp(floored)

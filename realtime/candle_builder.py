from __future__ import annotations

import threading
from datetime import datetime
from decimal import Decimal
from typing import Optional

from data_providers.base import Timeframe
from realtime.tick_models import CandleDataRealtime, TickData

# Minutes per interval for each intraday timeframe
_INTERVAL_MINUTES: dict[Timeframe, int] = {
    Timeframe.MIN_1: 1,
    Timeframe.MIN_5: 5,
    Timeframe.MIN_15: 15,
}


class CandleBuilder:
    """Accumulates ticks into OHLCV candles for a single (instrument, timeframe) pair.

    Thread-safe: each instance carries its own RLock, so concurrent tick feeds
    from different threads converge correctly on open/high/low/close/volume.
    """

    def __init__(
        self,
        instrument: str,
        timeframe: Timeframe,
        session_start: tuple[int, int] = (9, 15),
    ) -> None:
        self._instrument = instrument
        self._timeframe = timeframe
        self._session_start = session_start  # (hour, minute) for DAY_1 open
        self._current: Optional[CandleDataRealtime] = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_tick(self, tick: TickData) -> Optional[CandleDataRealtime]:
        """Feed one tick. Returns the finalized candle if the interval just closed, else None."""
        if tick.instrument != self._instrument:
            return None

        with self._lock:
            candle_open_time = self._floor_to_interval(tick.tick_time)

            if self._current is None:
                self._current = self._new_candle(tick, candle_open_time)
                return None

            if candle_open_time > self._current.candle_open_time:
                finalized = self._current
                finalized.finalize()
                self._current = self._new_candle(tick, candle_open_time)
                return finalized

            self._current.update(tick)
            return None

    def get_current_candle(self) -> Optional[CandleDataRealtime]:
        with self._lock:
            return self._current

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _new_candle(self, tick: TickData, open_time: datetime) -> CandleDataRealtime:
        return CandleDataRealtime(
            instrument=self._instrument,
            timeframe=self._timeframe,
            candle_open_time=open_time,
            open=tick.price,
            high=tick.price,
            low=tick.price,
            close=tick.price,
            volume=tick.volume,
            tick_count=1,
        )

    def _floor_to_interval(self, dt: datetime) -> datetime:
        """Floor a datetime to the start of the current candle interval."""
        if self._timeframe == Timeframe.DAY_1:
            # Daily candle opens at session start (09:15 IST by default)
            return dt.replace(
                hour=self._session_start[0],
                minute=self._session_start[1],
                second=0,
                microsecond=0,
            )
        minutes = _INTERVAL_MINUTES[self._timeframe]
        floored = (dt.minute // minutes) * minutes
        return dt.replace(minute=floored, second=0, microsecond=0)

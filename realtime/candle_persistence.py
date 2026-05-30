from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy.dialects.postgresql import insert as pg_insert

from database.connection import get_session
from database.models import MarketRealtimeStatus, MarketTick
from ingestion.loader import bulk_upsert
from realtime.tick_models import CandleDataRealtime, TickData
from utils.logger import get_logger
from config import settings

logger = get_logger(__name__, settings.log_dir, settings.log_level)

_DEFAULT_TICK_BUFFER_SIZE = 100


class CandlePersistenceService:
    """Handles all DB writes for the realtime pipeline.

    Tick persistence is buffered (flush every N ticks) to reduce round-trips.
    Candle persistence reuses the existing bulk_upsert from Phase 1.
    Status updates use UPSERT (ON CONFLICT DO UPDATE) on the unique (instrument, timeframe) key.
    """

    def __init__(self, tick_buffer_size: int = _DEFAULT_TICK_BUFFER_SIZE) -> None:
        self._tick_buffer: deque[dict] = deque()
        self._buffer_size = tick_buffer_size

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def persist_tick(self, tick: TickData) -> None:
        """Buffer a tick for batch insertion."""
        self._tick_buffer.append(
            {
                "instrument": tick.instrument,
                "tick_time": tick.tick_time,
                "price": float(tick.price),
                "volume": tick.volume,
            }
        )
        if len(self._tick_buffer) >= self._buffer_size:
            self.flush_tick_buffer()

    def flush_tick_buffer(self) -> int:
        """Drain the tick buffer to the database. Returns count flushed."""
        if not self._tick_buffer:
            return 0
        rows = list(self._tick_buffer)
        self._tick_buffer.clear()
        try:
            with get_session() as session:
                session.execute(pg_insert(MarketTick).values(rows))
            logger.debug("[CandlePersistence] Flushed %d ticks to DB", len(rows))
            return len(rows)
        except Exception as exc:
            logger.error("[CandlePersistence] Tick flush failed: %s", exc)
            return 0

    def persist_candles(self, candles: Sequence[CandleDataRealtime]) -> int:
        """Persist finalized candles via Phase 1's bulk_upsert (ON CONFLICT DO NOTHING)."""
        if not candles:
            return 0
        candle_data = [c.to_candle_data() for c in candles]
        result = bulk_upsert(candle_data)
        return result.inserted

    def upsert_status(
        self,
        instrument: str,
        timeframe: str,
        *,
        last_tick_time: Optional[datetime] = None,
        last_candle_time: Optional[datetime] = None,
        last_indicator_time: Optional[datetime] = None,
        last_signal_time: Optional[datetime] = None,
        status: Optional[str] = None,
    ) -> None:
        """UPSERT the processing watermark row for (instrument, timeframe)."""
        update_cols: dict = {"updated_at": datetime.utcnow()}
        if last_tick_time is not None:
            update_cols["last_tick_time"] = last_tick_time
        if last_candle_time is not None:
            update_cols["last_candle_time"] = last_candle_time
        if last_indicator_time is not None:
            update_cols["last_indicator_time"] = last_indicator_time
        if last_signal_time is not None:
            update_cols["last_signal_time"] = last_signal_time
        if status is not None:
            update_cols["status"] = status

        stmt = (
            pg_insert(MarketRealtimeStatus)
            .values(instrument=instrument, timeframe=timeframe, **update_cols)
            .on_conflict_do_update(
                index_elements=["instrument", "timeframe"],
                set_=update_cols,
            )
        )
        try:
            with get_session() as session:
                session.execute(stmt)
        except Exception as exc:
            logger.error(
                "[CandlePersistence] Status upsert failed for %s/%s: %s",
                instrument, timeframe, exc,
            )

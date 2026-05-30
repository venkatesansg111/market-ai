from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Sequence

from sqlalchemy.dialects.postgresql import insert as pg_insert

from data_providers.base import CandleData
from database.connection import get_session
from database.models import MarketCandle
from utils.logger import get_logger
from config import settings

logger = get_logger(__name__, settings.log_dir, settings.log_level)


@dataclass
class LoadResult:
    instrument: str
    timeframe: str
    attempted: int = 0
    inserted: int = 0
    duplicates: int = 0
    errors: int = 0

    @property
    def skipped(self) -> int:
        return self.attempted - self.inserted - self.errors


def _parse_dt(raw: str) -> datetime:
    """Parse ISO timestamp string to naive datetime."""
    dt = datetime.fromisoformat(raw.split(".")[0].replace("Z", ""))
    return dt


def bulk_upsert(
    candles: Sequence[CandleData],
    batch_size: int = 500,
) -> LoadResult:
    """
    Insert candle records using PostgreSQL ON CONFLICT DO NOTHING.
    Returns a LoadResult with counts of inserted vs duplicates.
    """
    if not candles:
        return LoadResult(instrument="", timeframe="")

    result = LoadResult(
        instrument=candles[0].instrument,
        timeframe=candles[0].timeframe,
        attempted=len(candles),
    )

    rows = []
    for c in candles:
        try:
            rows.append(
                {
                    "instrument": c.instrument,
                    "candle_time": _parse_dt(c.candle_time),
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                    "timeframe": c.timeframe,
                }
            )
        except Exception as exc:
            logger.warning("Skipping malformed candle %s: %s", c, exc)
            result.errors += 1

    # Chunk into batches
    for batch_start in range(0, len(rows), batch_size):
        batch = rows[batch_start : batch_start + batch_size]

        stmt = (
            pg_insert(MarketCandle)
            .values(batch)
            .on_conflict_do_nothing(
                index_elements=["instrument", "candle_time", "timeframe"]
            )
        )

        try:
            with get_session() as session:
                res = session.execute(stmt)
                inserted = res.rowcount if res.rowcount >= 0 else len(batch)
                result.inserted += inserted
                result.duplicates += len(batch) - inserted
        except Exception as exc:
            logger.error(
                "Batch insert failed (rows %d–%d): %s",
                batch_start, batch_start + len(batch), exc,
            )
            result.errors += len(batch)

    return result

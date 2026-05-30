from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date
from typing import Sequence

from data_providers.base import CandleData, MarketDataProvider, Timeframe
from ingestion.loader import LoadResult, bulk_upsert
from utils.logger import get_logger
from utils.time_utils import history_start_date, month_chunks
from config import settings

logger = get_logger(__name__, settings.log_dir, settings.log_level)


@dataclass
class InstrumentSummary:
    instrument: str
    timeframe: str
    fetched: int = 0
    inserted: int = 0
    duplicates: int = 0
    errors: int = 0
    chunks_failed: int = 0


def _fetch_chunk_with_retry(
    provider: MarketDataProvider,
    symbol: str,
    chunk_start: date,
    chunk_end: date,
    interval: Timeframe,
    max_retries: int,
    backoff: float,
) -> list[CandleData]:
    """Fetch one monthly chunk with exponential backoff on failure."""
    for attempt in range(1, max_retries + 1):
        try:
            candles = list(
                provider.get_historical_data(symbol, chunk_start, chunk_end, interval)
            )
            return candles
        except Exception as exc:
            wait = backoff * attempt
            logger.warning(
                "[%s] %s %s chunk %s→%s attempt %d/%d failed: %s — retrying in %.1fs",
                provider.provider_name(), symbol, interval.value,
                chunk_start, chunk_end, attempt, max_retries, exc, wait,
            )
            time.sleep(wait)

    logger.error(
        "[%s] %s %s chunk %s→%s exhausted all retries — skipping chunk.",
        provider.provider_name(), symbol, interval.value, chunk_start, chunk_end,
    )
    return []


def fetch_and_store(
    provider: MarketDataProvider,
    instruments: Sequence[str],
    timeframes: Sequence[Timeframe],
    history_months: int | None = None,
    request_delay: float | None = None,
    max_retries: int | None = None,
    retry_backoff: float | None = None,
    batch_size: int | None = None,
) -> list[InstrumentSummary]:
    """
    Orchestrates fetching + loading for all instruments × timeframes.
    Returns one InstrumentSummary per (instrument, timeframe) pair.
    """
    cfg = settings.ingestion
    months = history_months if history_months is not None else cfg.history_months
    delay = request_delay if request_delay is not None else cfg.request_delay_seconds
    retries = max_retries if max_retries is not None else cfg.max_retries
    backoff = retry_backoff if retry_backoff is not None else cfg.retry_backoff_seconds
    bsize = batch_size if batch_size is not None else cfg.batch_size

    end_date = date.today()
    start_date = history_start_date(months)

    logger.info(
        "Starting historical ingestion: %d instruments × %d timeframes | %s → %s",
        len(instruments), len(timeframes), start_date, end_date,
    )

    summaries: list[InstrumentSummary] = []

    for instrument in instruments:
        for tf in timeframes:
            summary = InstrumentSummary(instrument=instrument, timeframe=tf.value)
            logger.info("── Ingesting  %-15s  %-6s ──", instrument, tf.value)

            for chunk_start, chunk_end in month_chunks(start_date, end_date):
                candles = _fetch_chunk_with_retry(
                    provider, instrument, chunk_start, chunk_end,
                    tf, retries, backoff,
                )

                if not candles:
                    summary.chunks_failed += 1
                    continue

                summary.fetched += len(candles)

                load_result: LoadResult = bulk_upsert(candles, batch_size=bsize)
                summary.inserted += load_result.inserted
                summary.duplicates += load_result.duplicates
                summary.errors += load_result.errors

                logger.debug(
                    "  chunk %s→%s: fetched=%d inserted=%d dupes=%d",
                    chunk_start, chunk_end,
                    len(candles), load_result.inserted, load_result.duplicates,
                )

                if delay > 0:
                    time.sleep(delay)

            summaries.append(summary)

    return summaries


def print_summary(summaries: list[InstrumentSummary]) -> None:
    """Pretty-print the ingestion summary to stdout."""
    print("\n" + "=" * 60)
    print("  INGESTION SUMMARY")
    print("=" * 60)

    for s in summaries:
        print(f"\n{s.instrument}  [{s.timeframe}]")
        print(f"  Records fetched : {s.fetched:>8,}")
        print(f"  Inserted        : {s.inserted:>8,}")
        print(f"  Duplicates      : {s.duplicates:>8,}")
        print(f"  Errors          : {s.errors:>8,}")
        if s.chunks_failed:
            print(f"  Chunks failed   : {s.chunks_failed:>8,}")

    print("\n" + "=" * 60 + "\n")

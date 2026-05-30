from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional, Sequence

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from config import settings
from database.connection import get_session
from database.models import MarketCandle, MarketIndicator
from indicators.indicator_calculators import (
    calculate_ema,
    calculate_macd,
    calculate_rsi,
    calculate_vwap_session,
)
from indicators.indicator_models import IndicatorRecord
from utils.logger import get_logger

logger = get_logger(__name__, settings.log_dir, settings.log_level)


class IndicatorEngineService:
    """Incrementally calculates EMA20/50/200, RSI14, VWAP, MACD for stored candles.

    Incremental logic:
      1. Query market_indicators for the latest candle_time processed (watermark).
      2. On first run (no watermark): load ALL candles, calculate, insert everything.
      3. On subsequent runs: load LOOKBACK warmup candles + all new candles,
         calculate on the full window, insert only rows beyond the watermark.
      This ensures EMA200 always has sufficient history without re-inserting duplicates.
    """

    LOOKBACK: int = 250  # warmup window for EMA200

    def __init__(self, lookback: int = 250) -> None:
        self.LOOKBACK = lookback

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        instruments: Sequence[str],
        timeframes: Sequence[str],
    ) -> dict[tuple[str, str], int]:
        """Process all (instrument, timeframe) pairs. Returns counts of new indicator rows."""
        results: dict[tuple[str, str], int] = {}
        for instrument in instruments:
            for timeframe in timeframes:
                count = self.process_pair(instrument, timeframe)
                results[(instrument, timeframe)] = count
                logger.info(
                    "[IndicatorEngine] %s %s → %d new indicator rows",
                    instrument, timeframe, count,
                )
        return results

    def process_pair(self, instrument: str, timeframe: str) -> int:
        """Calculate and store indicators for one (instrument, timeframe). Returns count inserted."""
        last_time = self._get_last_indicator_time(instrument, timeframe)
        df = self._load_candles(instrument, timeframe, last_time)

        if df.empty:
            logger.debug(
                "[IndicatorEngine] No candles found for %s %s", instrument, timeframe
            )
            return 0

        df = self._calculate_all(df)

        # Filter to only rows beyond the current watermark
        new_df = df if last_time is None else df[df.index > pd.Timestamp(last_time)]

        if new_df.empty:
            return 0

        records = self._df_to_records(new_df, instrument, timeframe)
        return self._store_indicators(records)

    # ------------------------------------------------------------------
    # Private: data loading
    # ------------------------------------------------------------------

    def _get_last_indicator_time(
        self, instrument: str, timeframe: str
    ) -> Optional[datetime]:
        with get_session() as session:
            return session.execute(
                select(func.max(MarketIndicator.candle_time)).where(
                    MarketIndicator.instrument == instrument,
                    MarketIndicator.timeframe == timeframe,
                )
            ).scalar()

    def _load_candles(
        self,
        instrument: str,
        timeframe: str,
        since: Optional[datetime],
    ) -> pd.DataFrame:
        with get_session() as session:
            if since is not None:
                # Warmup: last LOOKBACK rows at or before watermark (for EMA seed values)
                warmup_rows = list(
                    reversed(
                        session.execute(
                            select(MarketCandle)
                            .where(
                                MarketCandle.instrument == instrument,
                                MarketCandle.timeframe == timeframe,
                                MarketCandle.candle_time <= since,
                            )
                            .order_by(MarketCandle.candle_time.desc())
                            .limit(self.LOOKBACK)
                        ).scalars().all()
                    )
                )
                # New rows: all candles after the watermark
                new_rows = session.execute(
                    select(MarketCandle)
                    .where(
                        MarketCandle.instrument == instrument,
                        MarketCandle.timeframe == timeframe,
                        MarketCandle.candle_time > since,
                    )
                    .order_by(MarketCandle.candle_time.asc())
                ).scalars().all()
                all_rows = warmup_rows + list(new_rows)
            else:
                # First run: load all candles to calculate full history
                all_rows = session.execute(
                    select(MarketCandle)
                    .where(
                        MarketCandle.instrument == instrument,
                        MarketCandle.timeframe == timeframe,
                    )
                    .order_by(MarketCandle.candle_time.asc())
                ).scalars().all()

        if not all_rows:
            return pd.DataFrame()

        data = [
            {
                "candle_time": r.candle_time,
                "open": float(r.open),
                "high": float(r.high),
                "low": float(r.low),
                "close": float(r.close),
                "volume": float(r.volume or 0),
            }
            for r in all_rows
        ]
        df = pd.DataFrame(data).set_index("candle_time")
        df.index = pd.to_datetime(df.index)
        # Drop exact duplicates (shouldn't exist due to DB constraint, but be safe)
        df = df[~df.index.duplicated(keep="last")].sort_index()
        return df

    # ------------------------------------------------------------------
    # Private: calculation
    # ------------------------------------------------------------------

    def _calculate_all(self, df: pd.DataFrame) -> pd.DataFrame:
        closes = df["close"]
        df = df.copy()
        df["ema20"] = calculate_ema(closes, 20)
        df["ema50"] = calculate_ema(closes, 50)
        df["ema200"] = calculate_ema(closes, 200)
        df["rsi14"] = calculate_rsi(closes, 14)
        df["vwap"] = calculate_vwap_session(df[["high", "low", "close", "volume"]])
        macd_line, signal_line = calculate_macd(closes)
        df["macd"] = macd_line
        df["macd_signal"] = signal_line
        return df

    def _df_to_records(
        self, df: pd.DataFrame, instrument: str, timeframe: str
    ) -> list[IndicatorRecord]:
        def to_dec(v) -> Optional[Decimal]:
            if v is None or (hasattr(v, "__float__") and pd.isna(v)):
                return None
            return Decimal(str(round(float(v), 6)))

        return [
            IndicatorRecord(
                instrument=instrument,
                candle_time=ts.to_pydatetime(),
                timeframe=timeframe,
                ema20=to_dec(row.get("ema20")),
                ema50=to_dec(row.get("ema50")),
                ema200=to_dec(row.get("ema200")),
                rsi14=to_dec(row.get("rsi14")),
                vwap=to_dec(row.get("vwap")),
                macd=to_dec(row.get("macd")),
                macd_signal=to_dec(row.get("macd_signal")),
            )
            for ts, row in df.iterrows()
        ]

    # ------------------------------------------------------------------
    # Private: persistence
    # ------------------------------------------------------------------

    def _store_indicators(self, records: list[IndicatorRecord]) -> int:
        if not records:
            return 0

        rows = [
            {
                "instrument": r.instrument,
                "candle_time": r.candle_time,
                "timeframe": r.timeframe,
                "ema20": float(r.ema20) if r.ema20 is not None else None,
                "ema50": float(r.ema50) if r.ema50 is not None else None,
                "ema200": float(r.ema200) if r.ema200 is not None else None,
                "rsi14": float(r.rsi14) if r.rsi14 is not None else None,
                "vwap": float(r.vwap) if r.vwap is not None else None,
                "macd": float(r.macd) if r.macd is not None else None,
                "macd_signal": float(r.macd_signal) if r.macd_signal is not None else None,
            }
            for r in records
        ]

        batch_size = settings.indicators.batch_size
        inserted = 0
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            try:
                with get_session() as session:
                    res = session.execute(
                        pg_insert(MarketIndicator).values(batch).on_conflict_do_nothing()
                    )
                    inserted += res.rowcount if res.rowcount >= 0 else len(batch)
            except Exception as exc:
                logger.error(
                    "[IndicatorEngine] Batch insert failed (rows %d-%d): %s",
                    i, i + len(batch), exc,
                )
        return inserted

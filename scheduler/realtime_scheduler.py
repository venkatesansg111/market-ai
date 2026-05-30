from __future__ import annotations

import random
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Iterator, Optional, Sequence

from data_providers.base import CandleData, Timeframe
from indicators.indicator_engine import IndicatorEngineService
from realtime.candle_manager import CandleManager
from realtime.candle_persistence import CandlePersistenceService
from realtime.tick_models import TickData
from signals.signal_engine import SignalEngineService
from utils.logger import get_logger
from config import settings

logger = get_logger(__name__, settings.log_dir, settings.log_level)


class MockTickGenerator:
    """Generates synthetic tick streams for testing and historical replay.

    Two modes:
      - generate_ticks: random-walk price from a base price, N ticks
      - replay_historical: converts stored candle data into 4 synthetic ticks per candle
        (open, high, low, close) so the CandleBuilder can reconstruct matching OHLCV.
    """

    def generate_ticks(
        self,
        instrument: str,
        from_time: datetime,
        n_ticks: int,
        base_price: float,
        volatility: float = 0.001,
        tick_interval_seconds: int = 1,
    ) -> Iterator[TickData]:
        """Emit a random-walk tick stream starting from base_price."""
        price = Decimal(str(base_price))
        vol_d = Decimal(str(volatility))
        current_time = from_time

        for _ in range(n_ticks):
            change = Decimal(str(random.gauss(0.0, float(vol_d)))) * price
            price = max(Decimal("0.01"), price + change)
            yield TickData(
                instrument=instrument,
                tick_time=current_time,
                price=price.quantize(Decimal("0.01")),
                volume=random.randint(50, 5000),
            )
            current_time += timedelta(seconds=tick_interval_seconds)

    def replay_historical(
        self,
        candles: Sequence[CandleData],
        timeframe: Timeframe = Timeframe.DAY_1,
    ) -> Iterator[TickData]:
        """Convert historical OHLCV candles into 4 synthetic ticks per candle.

        Tick sequence: open → high → low → close, evenly spaced within the interval.
        This lets CandleBuilder reconstruct the same OHLCV (open = open, high = max,
        low = min, close = close) when replayed through the realtime pipeline.
        """
        interval_seconds = {
            Timeframe.MIN_1: 60,
            Timeframe.MIN_5: 300,
            Timeframe.MIN_15: 900,
            Timeframe.DAY_1: 23400,  # 6.5 trading hours
        }.get(timeframe, 60)
        tick_spacing = interval_seconds // 4

        for candle in candles:
            try:
                open_time = datetime.fromisoformat(candle.candle_time.split(".")[0])
            except (ValueError, AttributeError):
                continue

            for i, price in enumerate(
                [candle.open, candle.high, candle.low, candle.close]
            ):
                yield TickData(
                    instrument=candle.instrument,
                    tick_time=open_time + timedelta(seconds=tick_spacing * i),
                    price=Decimal(str(price)).quantize(Decimal("0.01")),
                    volume=max(0, candle.volume // 4),
                )


class RealtimeCandleService:
    """Orchestrates the full realtime pipeline: tick → candle → indicator → signal.

    Designed for dependency injection: all four sub-services are passed in,
    making each independently testable and replaceable (e.g., swap in Kite WebSocket
    by replacing MockTickGenerator without changing this class).

    Future integration point for Kite WebSocket:
        Replace MockTickGenerator.generate_ticks() with KiteFeed.on_tick()
        callback that calls self.process_tick() directly.
    """

    def __init__(
        self,
        candle_manager: CandleManager,
        persistence_service: CandlePersistenceService,
        indicator_service: IndicatorEngineService,
        signal_service: SignalEngineService,
    ) -> None:
        self._manager = candle_manager
        self._persistence = persistence_service
        self._indicator = indicator_service
        self._signal = signal_service

    def process_tick(self, tick: TickData) -> None:
        """Process one tick through the full pipeline."""
        self._persistence.persist_tick(tick)
        finalized = self._manager.process_tick(tick)

        if finalized:
            self._persistence.persist_candles(finalized)
            for candle in finalized:
                self._persistence.upsert_status(
                    candle.instrument,
                    candle.timeframe.value,
                    last_candle_time=candle.candle_open_time,
                )

    def run_mock_session(
        self,
        instruments: Sequence[str],
        n_ticks: int = 1000,
        base_prices: Optional[dict[str, float]] = None,
    ) -> dict:
        """Run a mock trading session with synthetic tick data."""
        base_prices = base_prices or {
            "NIFTY 50": 22500.0,
            "NIFTY BANK": 48000.0,
        }
        generator = MockTickGenerator()
        from_time = datetime.now().replace(hour=9, minute=15, second=0, microsecond=0)

        stats: dict = {"ticks_processed": 0, "instruments": list(instruments)}
        for instrument in instruments:
            self._manager.register_instrument(instrument)
            base = base_prices.get(instrument, 20000.0)
            for tick in generator.generate_ticks(
                instrument=instrument,
                from_time=from_time,
                n_ticks=n_ticks,
                base_price=base,
            ):
                self.process_tick(tick)
                stats["ticks_processed"] += 1

        self._persistence.flush_tick_buffer()
        logger.info(
            "[RealtimeCandleService] Mock session complete: %d ticks processed",
            stats["ticks_processed"],
        )
        return stats

    def run_historical_replay(
        self,
        instruments: Sequence[str],
        timeframes: Sequence[Timeframe],
        months_back: int = 1,
    ) -> dict:
        """Replay existing DB candles as synthetic ticks through the candle builder."""
        from utils.time_utils import history_start_date

        since = history_start_date(months_back)
        stats: dict = {"ticks_processed": 0}

        for instrument in instruments:
            for tf in timeframes:
                candles = self._load_candles_from_db(instrument, tf.value, since)
                if not candles:
                    logger.debug(
                        "[RealtimeCandleService] No candles for replay: %s %s",
                        instrument, tf.value,
                    )
                    continue

                self._manager.register_instrument(instrument)
                generator = MockTickGenerator()
                for tick in generator.replay_historical(candles, tf):
                    self.process_tick(tick)
                    stats["ticks_processed"] += 1

                logger.info(
                    "[RealtimeCandleService] Replayed %s %s: %d candles → ticks",
                    instrument, tf.value, len(candles),
                )

        self._persistence.flush_tick_buffer()
        return stats

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_candles_from_db(
        self, instrument: str, timeframe: str, since
    ) -> list[CandleData]:
        from sqlalchemy import select
        from database.connection import get_session
        from database.models import MarketCandle

        with get_session() as session:
            rows = session.execute(
                select(MarketCandle)
                .where(
                    MarketCandle.instrument == instrument,
                    MarketCandle.timeframe == timeframe,
                    MarketCandle.candle_time >= since,
                )
                .order_by(MarketCandle.candle_time.asc())
            ).scalars().all()

        return [
            CandleData(
                instrument=row.instrument,
                candle_time=row.candle_time.isoformat(),
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=row.volume or 0,
                timeframe=row.timeframe,
            )
            for row in rows
        ]

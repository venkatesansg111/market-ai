from __future__ import annotations

import threading
from typing import Optional

from data_providers.base import Timeframe
from realtime.candle_builder import CandleBuilder
from realtime.tick_models import CandleDataRealtime, TickData
from utils.logger import get_logger
from config import settings

logger = get_logger(__name__, settings.log_dir, settings.log_level)


class CandleManager:
    """Thread-safe manager that routes each tick to all CandleBuilders for that instrument.

    Designed to handle 100+ instruments simultaneously. The dict of builders is protected
    by a coarse lock only for mutations (registration); individual builder locks handle
    concurrent tick processing.
    """

    def __init__(self, timeframes: list[Timeframe]) -> None:
        self._timeframes = timeframes
        self._builders: dict[tuple[str, Timeframe], CandleBuilder] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_instrument(self, instrument: str) -> None:
        """Ensure CandleBuilders exist for all configured timeframes for this instrument."""
        with self._lock:
            for tf in self._timeframes:
                key = (instrument, tf)
                if key not in self._builders:
                    self._builders[key] = CandleBuilder(instrument, tf)
                    logger.debug(
                        "[CandleManager] Registered builder: %s %s", instrument, tf.value
                    )

    def process_tick(self, tick: TickData) -> list[CandleDataRealtime]:
        """Route a tick to all registered builders for its instrument.

        Auto-registers the instrument if not seen before.
        Returns the list of candles that were finalized by this tick (0 or more).
        """
        if not self._has_instrument(tick.instrument):
            self.register_instrument(tick.instrument)

        finalized: list[CandleDataRealtime] = []
        for builder in self._get_builders(tick.instrument):
            result = builder.process_tick(tick)
            if result is not None:
                finalized.append(result)
                logger.debug(
                    "[CandleManager] Finalized %s %s candle @ %s",
                    result.instrument,
                    result.timeframe.value,
                    result.candle_open_time,
                )
        return finalized

    def get_open_candles(self) -> dict[tuple[str, str], CandleDataRealtime]:
        """Snapshot of all in-progress (not yet finalized) candles. For monitoring only."""
        with self._lock:
            snapshot: dict[tuple[str, str], CandleDataRealtime] = {}
            for (instrument, tf), builder in self._builders.items():
                candle = builder.get_current_candle()
                if candle is not None and not candle.is_finalized:
                    snapshot[(instrument, tf.value)] = candle
            return snapshot

    def registered_instruments(self) -> list[str]:
        with self._lock:
            return list({instrument for instrument, _ in self._builders})

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _has_instrument(self, instrument: str) -> bool:
        with self._lock:
            return any(instr == instrument for instr, _ in self._builders)

    def _get_builders(self, instrument: str) -> list[CandleBuilder]:
        with self._lock:
            return [
                builder
                for (instr, _), builder in self._builders.items()
                if instr == instrument
            ]

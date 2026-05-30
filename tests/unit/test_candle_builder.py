from __future__ import annotations

import threading
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from data_providers.base import Timeframe
from realtime.candle_builder import CandleBuilder
from realtime.tick_models import TickData


def make_tick(
    instrument: str = "NIFTY 50",
    time: datetime = datetime(2024, 1, 15, 9, 15, 30),
    price: float = 22500.0,
    volume: int = 100,
) -> TickData:
    return TickData(
        instrument=instrument,
        tick_time=time,
        price=Decimal(str(price)),
        volume=volume,
    )


# ──────────────────────────────────────────────────────────────────────
# First tick
# ──────────────────────────────────────────────────────────────────────

class TestFirstTick:
    def test_first_tick_returns_none(self):
        builder = CandleBuilder("NIFTY 50", Timeframe.MIN_1)
        result = builder.process_tick(make_tick())
        assert result is None

    def test_first_tick_sets_ohlcv(self):
        builder = CandleBuilder("NIFTY 50", Timeframe.MIN_1)
        builder.process_tick(make_tick(price=22500.0, volume=200))
        candle = builder.get_current_candle()
        assert candle is not None
        assert candle.open == Decimal("22500.00")
        assert candle.high == Decimal("22500.00")
        assert candle.low == Decimal("22500.00")
        assert candle.close == Decimal("22500.00")
        assert candle.volume == 200
        assert candle.tick_count == 1

    def test_wrong_instrument_ignored(self):
        builder = CandleBuilder("NIFTY 50", Timeframe.MIN_1)
        result = builder.process_tick(make_tick(instrument="NIFTY BANK"))
        assert result is None
        assert builder.get_current_candle() is None


# ──────────────────────────────────────────────────────────────────────
# OHLCV updates within a single candle
# ──────────────────────────────────────────────────────────────────────

class TestCandleUpdates:
    def setup_method(self):
        self.builder = CandleBuilder("NIFTY 50", Timeframe.MIN_1)
        base = datetime(2024, 1, 15, 9, 15, 0)
        # Tick 1: open
        self.builder.process_tick(make_tick(time=base, price=22500.0, volume=100))
        # Tick 2: higher price
        self.builder.process_tick(make_tick(time=base + timedelta(seconds=20), price=22600.0, volume=150))
        # Tick 3: lower price
        self.builder.process_tick(make_tick(time=base + timedelta(seconds=40), price=22400.0, volume=200))
        # Tick 4: close
        self.builder.process_tick(make_tick(time=base + timedelta(seconds=55), price=22550.0, volume=50))

    def test_open_is_first_price(self):
        assert self.builder.get_current_candle().open == Decimal("22500.00")

    def test_high_is_maximum(self):
        assert self.builder.get_current_candle().high == Decimal("22600.00")

    def test_low_is_minimum(self):
        assert self.builder.get_current_candle().low == Decimal("22400.00")

    def test_close_is_last_price(self):
        assert self.builder.get_current_candle().close == Decimal("22550.00")

    def test_volume_accumulates(self):
        assert self.builder.get_current_candle().volume == 500

    def test_tick_count(self):
        assert self.builder.get_current_candle().tick_count == 4


# ──────────────────────────────────────────────────────────────────────
# Candle finalization
# ──────────────────────────────────────────────────────────────────────

class TestCandleFinalization:
    def test_candle_finalizes_on_new_interval(self):
        builder = CandleBuilder("NIFTY 50", Timeframe.MIN_1)
        base = datetime(2024, 1, 15, 9, 15, 0)
        builder.process_tick(make_tick(time=base, price=22500.0))
        # Tick in the next minute → previous candle should finalize
        next_minute = base + timedelta(minutes=1)
        result = builder.process_tick(make_tick(time=next_minute, price=22550.0))
        assert result is not None
        assert result.is_finalized

    def test_finalized_candle_has_correct_open_time(self):
        builder = CandleBuilder("NIFTY 50", Timeframe.MIN_1)
        base = datetime(2024, 1, 15, 9, 15, 30)  # 30 seconds into 09:15
        builder.process_tick(make_tick(time=base, price=22500.0))
        result = builder.process_tick(
            make_tick(time=base + timedelta(minutes=1), price=22600.0)
        )
        assert result is not None
        assert result.candle_open_time == datetime(2024, 1, 15, 9, 15, 0)

    def test_new_candle_starts_after_finalization(self):
        builder = CandleBuilder("NIFTY 50", Timeframe.MIN_5)
        base = datetime(2024, 1, 15, 9, 15, 0)
        builder.process_tick(make_tick(time=base, price=22500.0))
        builder.process_tick(make_tick(time=base + timedelta(minutes=5), price=22600.0))
        candle = builder.get_current_candle()
        assert candle is not None
        assert candle.candle_open_time == datetime(2024, 1, 15, 9, 20, 0)
        assert candle.open == Decimal("22600.00")

    def test_5min_interval_boundary(self):
        builder = CandleBuilder("NIFTY 50", Timeframe.MIN_5)
        # Tick at 09:17 → floor to 09:15
        t1 = datetime(2024, 1, 15, 9, 17, 0)
        builder.process_tick(make_tick(time=t1, price=22500.0))
        # Tick at 09:21 → floor to 09:20 → triggers finalization
        t2 = datetime(2024, 1, 15, 9, 21, 0)
        result = builder.process_tick(make_tick(time=t2, price=22600.0))
        assert result is not None
        assert result.candle_open_time == datetime(2024, 1, 15, 9, 15, 0)

    def test_daily_candle_opens_at_session_start(self):
        builder = CandleBuilder("NIFTY 50", Timeframe.DAY_1, session_start=(9, 15))
        t1 = datetime(2024, 1, 15, 10, 30, 0)
        builder.process_tick(make_tick(time=t1, price=22500.0))
        candle = builder.get_current_candle()
        assert candle.candle_open_time == datetime(2024, 1, 15, 9, 15, 0)


# ──────────────────────────────────────────────────────────────────────
# Conversion to CandleData
# ──────────────────────────────────────────────────────────────────────

class TestToCandleData:
    def test_to_candle_data_fields(self):
        builder = CandleBuilder("NIFTY 50", Timeframe.MIN_1)
        base = datetime(2024, 1, 15, 9, 15, 0)
        builder.process_tick(make_tick(time=base, price=22500.0, volume=300))
        result = builder.process_tick(
            make_tick(time=base + timedelta(minutes=1), price=22550.0)
        )
        assert result is not None
        cd = result.to_candle_data()
        assert cd.instrument == "NIFTY 50"
        assert cd.timeframe == "1min"
        assert cd.open == 22500.0
        assert cd.volume == 300


# ──────────────────────────────────────────────────────────────────────
# Thread safety
# ──────────────────────────────────────────────────────────────────────

class TestThreadSafety:
    def test_concurrent_tick_feeding_does_not_raise(self):
        builder = CandleBuilder("NIFTY 50", Timeframe.MIN_1)
        base = datetime(2024, 1, 15, 9, 15, 0)
        errors: list[Exception] = []

        def feed_ticks():
            try:
                for i in range(50):
                    builder.process_tick(
                        make_tick(
                            time=base + timedelta(seconds=i),
                            price=22500.0 + i,
                        )
                    )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=feed_ticks) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"

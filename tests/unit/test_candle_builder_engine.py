"""Unit tests for streaming.candle_builder — CandleBuilderEngine."""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from streaming.candle_builder import CandleBuilderEngine, _bucket_start
from streaming.event_bus import EventBus
from streaming.event_models import CandleEvent, TickEvent


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _bus() -> EventBus:
    return EventBus()


def _tick(
    symbol: str = "AAPL",
    price: float = 100.0,
    volume: int = 100,
    ts: datetime | None = None,
) -> TickEvent:
    if ts is None:
        ts = _T0
    return TickEvent(symbol=symbol, price=Decimal(str(price)), volume=volume, timestamp=ts)


# Use datetime.fromtimestamp so that .timestamp() round-trips correctly
# regardless of local timezone.  Pick an epoch that's divisible by 3600
# (hour) so it's also divisible by 60 and 300.
_T0_EPOCH = 1705311000  # 2024-01-15 09:30:00 UTC; 1705311000 % 60 == 0
_T0 = datetime.fromtimestamp(_T0_EPOCH)  # local naive, epoch-aligned

# Convenience offsets within the same 1-min bucket as _T0
_T0_20s = _T0 + timedelta(seconds=20)
_T0_40s = _T0 + timedelta(seconds=40)

# Next buckets
_T1m = _T0 + timedelta(minutes=1)   # next 1-min boundary
_T5m = _T0 + timedelta(minutes=5)   # next 5-min boundary (T0 is 5m-aligned too)


# ──────────────────────────────────────────────────────────────────────
# _bucket_start helper
# ──────────────────────────────────────────────────────────────────────

class TestBucketStart:
    def test_same_bucket_for_ticks_in_same_1m_interval(self):
        t1 = _T0 + timedelta(seconds=10)
        t2 = _T0 + timedelta(seconds=55)
        assert _bucket_start(t1, "1m") == _bucket_start(t2, "1m")

    def test_different_buckets_for_adjacent_1m(self):
        t1 = _T0
        t2 = _T0 + timedelta(minutes=1)
        assert _bucket_start(t1, "1m") != _bucket_start(t2, "1m")

    def test_same_bucket_for_ticks_in_same_5m_interval(self):
        t1 = _T0 + timedelta(seconds=10)
        t2 = _T0 + timedelta(minutes=4, seconds=55)
        assert _bucket_start(t1, "5m") == _bucket_start(t2, "5m")

    def test_different_buckets_for_adjacent_5m(self):
        t1 = _T0
        t2 = _T0 + timedelta(minutes=5)
        assert _bucket_start(t1, "5m") != _bucket_start(t2, "5m")

    def test_same_bucket_for_ticks_in_same_1h_interval(self):
        # Use t1 and t2 guaranteed within the same epoch-hour bucket
        t1 = _T0
        t2 = _T0 + timedelta(minutes=10)  # safe: _T0 is 30min past hour boundary
        assert _bucket_start(t1, "1h") == _bucket_start(t2, "1h")

    def test_different_buckets_for_adjacent_1h(self):
        # Advance by exactly 2 hours to ensure a different bucket
        t1 = _T0
        t2 = _T0 + timedelta(hours=2)
        assert _bucket_start(t1, "1h") != _bucket_start(t2, "1h")

    def test_unknown_timeframe_raises(self):
        with pytest.raises(ValueError, match="Unknown timeframe"):
            _bucket_start(_T0, "3m")


# ──────────────────────────────────────────────────────────────────────
# First tick initialises candle
# ──────────────────────────────────────────────────────────────────────

class TestFirstTick:
    def test_no_candle_emitted_on_first_tick(self):
        bus = _bus()
        candles = []
        bus.subscribe(CandleEvent, candles.append)
        CandleBuilderEngine(bus, timeframes=["1m"])
        bus.publish(_tick(ts=_T0))
        assert candles == []

    def test_pending_count_after_first_tick(self):
        bus = _bus()
        engine = CandleBuilderEngine(bus, timeframes=["1m", "5m"])
        bus.publish(_tick(ts=_T0))
        assert engine.pending_count() == 2  # one per timeframe

    def test_tick_count_increments(self):
        bus = _bus()
        engine = CandleBuilderEngine(bus, timeframes=["1m"])
        bus.publish(_tick(ts=_T0))
        bus.publish(_tick(ts=_T0))
        assert engine.tick_count == 2


# ──────────────────────────────────────────────────────────────────────
# OHLCV accumulation within a candle
# ──────────────────────────────────────────────────────────────────────

class TestOHLCVAccumulation:
    def setup_method(self):
        self.bus = _bus()
        self.candles: list[CandleEvent] = []
        self.bus.subscribe(CandleEvent, self.candles.append)
        self.engine = CandleBuilderEngine(self.bus, timeframes=["1m"])
        # 3 ticks within the same 1-min bucket
        self.bus.publish(_tick(price=100.0, volume=200, ts=_T0))
        self.bus.publish(_tick(price=105.0, volume=100, ts=_T0_20s))
        self.bus.publish(_tick(price=98.0, volume=150, ts=_T0_40s))
        # Flush to close the candle
        self.engine.flush()

    def test_open_is_first_price(self):
        assert len(self.candles) == 1
        assert self.candles[0].open == Decimal("100.0")

    def test_high_is_max(self):
        assert self.candles[0].high == Decimal("105.0")

    def test_low_is_min(self):
        assert self.candles[0].low == Decimal("98.0")

    def test_close_is_last_price(self):
        assert self.candles[0].close == Decimal("98.0")

    def test_volume_accumulated(self):
        assert self.candles[0].volume == 450

    def test_candle_is_closed(self):
        assert self.candles[0].is_closed is True


# ──────────────────────────────────────────────────────────────────────
# Candle boundary triggers emission
# ──────────────────────────────────────────────────────────────────────

class TestCandleBoundary:
    def test_new_bucket_emits_closed_candle(self):
        bus = _bus()
        candles = []
        bus.subscribe(CandleEvent, candles.append)
        CandleBuilderEngine(bus, timeframes=["1m"])

        bus.publish(_tick(ts=_T0))
        bus.publish(_tick(ts=_T1m + timedelta(seconds=5)))
        closed = [c for c in candles if c.is_closed]
        assert len(closed) == 1

    def test_closed_candle_has_correct_timeframe(self):
        bus = _bus()
        candles = []
        bus.subscribe(CandleEvent, candles.append)
        CandleBuilderEngine(bus, timeframes=["1m"])
        bus.publish(_tick(ts=_T0))
        bus.publish(_tick(ts=_T1m))
        closed = [c for c in candles if c.is_closed]
        assert closed[0].timeframe == "1m"

    def test_candle_count_increments_on_close(self):
        bus = _bus()
        engine = CandleBuilderEngine(bus, timeframes=["1m"])
        bus.publish(_tick(ts=_T0))
        bus.publish(_tick(ts=_T1m))
        assert engine.candle_count == 1


# ──────────────────────────────────────────────────────────────────────
# Multi-timeframe
# ──────────────────────────────────────────────────────────────────────

class TestMultiTimeframe:
    def test_multiple_timeframes_tracked_independently(self):
        bus = _bus()
        candles: list[CandleEvent] = []
        bus.subscribe(CandleEvent, candles.append)
        engine = CandleBuilderEngine(bus, timeframes=["1m", "5m"])
        # Single tick
        bus.publish(_tick(ts=_T0))
        assert engine.pending_count() == 2

    def test_1m_closes_before_5m(self):
        bus = _bus()
        candles: list[CandleEvent] = []
        bus.subscribe(CandleEvent, candles.append)
        CandleBuilderEngine(bus, timeframes=["1m", "5m"])

        bus.publish(_tick(ts=_T0))
        # Move forward 1 minute — 1m closes, 5m does not
        bus.publish(_tick(ts=_T1m))
        closed_tfs = [c.timeframe for c in candles if c.is_closed]
        assert "1m" in closed_tfs
        assert "5m" not in closed_tfs

    def test_5m_closes_after_5_minutes(self):
        bus = _bus()
        candles: list[CandleEvent] = []
        bus.subscribe(CandleEvent, candles.append)
        CandleBuilderEngine(bus, timeframes=["5m"])
        bus.publish(_tick(ts=_T0))
        # Move forward 5 minutes
        bus.publish(_tick(ts=_T5m))
        closed = [c for c in candles if c.is_closed and c.timeframe == "5m"]
        assert len(closed) == 1

    def test_different_symbols_tracked_separately(self):
        bus = _bus()
        engine = CandleBuilderEngine(bus, timeframes=["1m"])
        bus.publish(_tick(symbol="AAPL", ts=_T0))
        bus.publish(_tick(symbol="GOOG", ts=_T0))
        assert engine.pending_count() == 2


# ──────────────────────────────────────────────────────────────────────
# Out-of-order ticks
# ──────────────────────────────────────────────────────────────────────

class TestOutOfOrder:
    def test_out_of_order_tick_dropped(self):
        bus = _bus()
        engine = CandleBuilderEngine(bus, timeframes=["1m"])
        # Tick at T0 starts candle
        bus.publish(_tick(ts=_T0))
        # Old tick (before T0 bucket) should be dropped
        old_ts = _T0 - timedelta(minutes=1)
        bus.publish(_tick(ts=old_ts))
        assert engine.dropped_count == 1

    def test_in_order_tick_not_dropped(self):
        bus = _bus()
        engine = CandleBuilderEngine(bus, timeframes=["1m"])
        bus.publish(_tick(ts=_T0))
        bus.publish(_tick(ts=_T0_20s))
        assert engine.dropped_count == 0


# ──────────────────────────────────────────────────────────────────────
# Flush
# ──────────────────────────────────────────────────────────────────────

class TestFlush:
    def test_flush_emits_all_pending(self):
        bus = _bus()
        candles = []
        bus.subscribe(CandleEvent, candles.append)
        engine = CandleBuilderEngine(bus, timeframes=["1m", "5m"])
        bus.publish(_tick(symbol="AAPL", ts=_T0))
        bus.publish(_tick(symbol="GOOG", ts=_T0))
        flushed = engine.flush()
        # 2 symbols × 2 timeframes = 4 pending candles
        assert flushed == 4
        assert len([c for c in candles if c.is_closed]) == 4

    def test_flush_clears_pending(self):
        bus = _bus()
        engine = CandleBuilderEngine(bus, timeframes=["1m"])
        bus.publish(_tick(ts=_T0))
        engine.flush()
        assert engine.pending_count() == 0

    def test_flush_returns_zero_when_nothing_pending(self):
        bus = _bus()
        engine = CandleBuilderEngine(bus, timeframes=["1m"])
        assert engine.flush() == 0


# ──────────────────────────────────────────────────────────────────────
# Live update emission
# ──────────────────────────────────────────────────────────────────────

class TestLiveUpdates:
    def test_live_updates_disabled_by_default(self):
        bus = _bus()
        candles = []
        bus.subscribe(CandleEvent, candles.append)
        CandleBuilderEngine(bus, timeframes=["1m"], emit_live_updates=False)
        bus.publish(_tick(ts=_T0))
        bus.publish(_tick(ts=_T0_20s))
        open_candles = [c for c in candles if not c.is_closed]
        assert open_candles == []

    def test_live_updates_emitted_when_enabled(self):
        bus = _bus()
        candles = []
        bus.subscribe(CandleEvent, candles.append)
        CandleBuilderEngine(bus, timeframes=["1m"], emit_live_updates=True)
        bus.publish(_tick(ts=_T0))
        bus.publish(_tick(ts=_T0_20s))
        open_candles = [c for c in candles if not c.is_closed]
        assert len(open_candles) >= 1

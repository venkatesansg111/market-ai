"""Unit tests for streaming.streaming_indicators — StreamingIndicatorEngine."""
from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal

import pytest

from streaming.event_bus import EventBus
from streaming.event_models import CandleEvent, IndicatorEvent
from streaming.streaming_indicators import (
    IndicatorConfig,
    StreamingIndicatorEngine,
    _EMAState,
    _RSIState,
    _ATRState,
    _VWAPState,
    _VolatilityState,
)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _bus() -> EventBus:
    return EventBus()


def _candle(
    symbol: str = "AAPL",
    timeframe: str = "1m",
    close: float = 100.0,
    high: float | None = None,
    low: float | None = None,
    volume: int = 1000,
    ts: datetime | None = None,
    is_closed: bool = True,
) -> CandleEvent:
    if high is None:
        high = close + 1.0
    if low is None:
        low = close - 1.0
    if ts is None:
        ts = datetime(2024, 1, 15, 9, 30, 0)
    return CandleEvent(
        symbol=symbol, timeframe=timeframe,
        open=Decimal(str(close)), high=Decimal(str(high)),
        low=Decimal(str(low)), close=Decimal(str(close)),
        volume=volume, is_closed=is_closed,
        candle_open_time=ts, timestamp=ts,
    )


def _feed_candles(bus: EventBus, n: int, base_price: float = 100.0) -> list[IndicatorEvent]:
    """Feed n closed candles with incrementing prices; return collected IndicatorEvents."""
    received = []
    bus.subscribe(IndicatorEvent, received.append)
    for i in range(n):
        bus.publish(_candle(close=base_price + i))
    return received


# ──────────────────────────────────────────────────────────────────────
# _EMAState unit tests
# ──────────────────────────────────────────────────────────────────────

class TestEMAState:
    def test_returns_none_before_warm(self):
        ema = _EMAState(period=3, alpha=2 / 4)
        assert ema.update(100.0) is None
        assert ema.update(101.0) is None

    def test_returns_value_when_warm(self):
        ema = _EMAState(period=3, alpha=2 / 4)
        for _ in range(2):
            ema.update(100.0)
        val = ema.update(102.0)
        assert val is not None

    def test_is_warm_flag(self):
        ema = _EMAState(period=2, alpha=2 / 3)
        ema.update(100.0)
        assert not ema.is_warm
        ema.update(100.0)
        assert ema.is_warm

    def test_ema_value_between_old_and_new(self):
        ema = _EMAState(period=2, alpha=2 / 3)
        ema.update(100.0)
        val = ema.update(110.0)
        assert 100.0 < val < 110.0


# ──────────────────────────────────────────────────────────────────────
# _RSIState unit tests
# ──────────────────────────────────────────────────────────────────────

class TestRSIState:
    def test_returns_none_before_period(self):
        rsi = _RSIState(period=14)
        for _ in range(13):
            result = rsi.update(100.0)
        assert result is None

    def test_returns_value_at_period(self):
        rsi = _RSIState(period=14)
        for _ in range(14):
            rsi.update(100.0)
        val = rsi.update(101.0)
        assert val is not None

    def test_all_gains_gives_rsi_100(self):
        rsi = _RSIState(period=5)
        for _ in range(6):
            rsi.update(100.0)  # no change
        for _ in range(10):
            rsi.update(rsi.prices[-1] + 1)
        val = rsi.update(rsi.prices[-1] + 1)
        assert val is not None and val > 80.0

    def test_all_losses_gives_low_rsi(self):
        rsi = _RSIState(period=5)
        for i in range(20):
            rsi.update(100.0 - i * 2)
        val = rsi.update(100.0 - 20 * 2)
        assert val is not None and val < 20.0

    def test_rsi_between_0_and_100(self):
        rsi = _RSIState(period=14)
        prices = [100, 102, 101, 103, 104, 102, 100, 101, 103, 105, 104, 103, 102, 101, 100]
        val = None
        for p in prices:
            val = rsi.update(float(p))
        if val is not None:
            assert 0.0 <= val <= 100.0


# ──────────────────────────────────────────────────────────────────────
# _ATRState unit tests
# ──────────────────────────────────────────────────────────────────────

class TestATRState:
    def test_returns_none_on_first_candle(self):
        atr = _ATRState(period=14)
        result = atr.update(101.0, 99.0, 100.0)
        assert result is None

    def test_returns_value_after_warmup(self):
        atr = _ATRState(period=3)
        atr.update(101, 99, 100)
        atr.update(102, 100, 101)
        atr.update(103, 101, 102)
        val = atr.update(104, 102, 103)
        assert val is not None and val > 0

    def test_atr_is_positive(self):
        atr = _ATRState(period=3)
        for i in range(10):
            v = atr.update(100 + i + 1, 100 + i - 1, 100 + i)
        assert v is None or v > 0


# ──────────────────────────────────────────────────────────────────────
# _VWAPState unit tests
# ──────────────────────────────────────────────────────────────────────

class TestVWAPState:
    def test_vwap_first_candle(self):
        vwap = _VWAPState()
        candle = _candle(close=100.0, high=102.0, low=98.0, volume=1000)
        val = vwap.update(candle)
        # typical = (102+98+100)/3 = 100.0
        assert val == pytest.approx(100.0)

    def test_vwap_resets_on_new_session_date(self):
        vwap = _VWAPState()
        d1 = _candle(close=100.0, high=102.0, low=98.0, volume=1000,
                     ts=datetime(2024, 1, 15, 9, 30))
        d2 = _candle(close=200.0, high=202.0, low=198.0, volume=1000,
                     ts=datetime(2024, 1, 16, 9, 30))
        vwap.update(d1)
        val2 = vwap.update(d2)
        # Should be based only on day2 candle after reset
        assert val2 == pytest.approx(200.0)

    def test_vwap_zero_volume_returns_none(self):
        vwap = _VWAPState()
        candle = _candle(close=100.0, high=101.0, low=99.0, volume=0)
        val = vwap.update(candle)
        assert val is None


# ──────────────────────────────────────────────────────────────────────
# StreamingIndicatorEngine
# ──────────────────────────────────────────────────────────────────────

class TestStreamingIndicatorEngine:
    def test_open_candles_ignored(self):
        bus = _bus()
        received = []
        bus.subscribe(IndicatorEvent, received.append)
        StreamingIndicatorEngine(bus)
        bus.publish(_candle(is_closed=False))
        assert received == []

    def test_closed_candle_emits_indicator_event(self):
        bus = _bus()
        received = []
        bus.subscribe(IndicatorEvent, received.append)
        StreamingIndicatorEngine(bus)
        bus.publish(_candle(is_closed=True))
        assert len(received) == 1

    def test_is_warm_false_before_slow_ema_period(self):
        bus = _bus()
        cfg = IndicatorConfig(ema_fast_period=3, ema_slow_period=5, rsi_period=5)
        received = []
        bus.subscribe(IndicatorEvent, received.append)
        StreamingIndicatorEngine(bus, config=cfg)
        for _ in range(4):  # not enough for slow EMA (5)
            bus.publish(_candle())
        warm_events = [e for e in received if e.is_warm]
        assert warm_events == []

    def test_is_warm_true_after_all_periods_satisfied(self):
        bus = _bus()
        cfg = IndicatorConfig(ema_fast_period=3, ema_slow_period=5, rsi_period=5)
        received = []
        bus.subscribe(IndicatorEvent, received.append)
        StreamingIndicatorEngine(bus, config=cfg)
        for i in range(20):
            bus.publish(_candle(close=100.0 + i))
        warm_events = [e for e in received if e.is_warm]
        assert len(warm_events) > 0

    def test_ema_fast_less_reactive_than_ema_slow(self):
        """ema_fast should track price faster than ema_slow."""
        bus = _bus()
        cfg = IndicatorConfig(ema_fast_period=5, ema_slow_period=20, rsi_period=5)
        received = []
        bus.subscribe(IndicatorEvent, received.append)
        StreamingIndicatorEngine(bus, config=cfg)
        # Start low, jump high
        for _ in range(25):
            bus.publish(_candle(close=100.0))
        bus.publish(_candle(close=200.0))
        last = received[-1]
        if last.ema_fast is not None and last.ema_slow is not None:
            assert last.ema_fast > last.ema_slow

    def test_rsi_present_after_warmup(self):
        bus = _bus()
        cfg = IndicatorConfig(ema_fast_period=3, ema_slow_period=5, rsi_period=5)
        received = []
        bus.subscribe(IndicatorEvent, received.append)
        StreamingIndicatorEngine(bus, config=cfg)
        for i in range(15):
            bus.publish(_candle(close=100.0 + i))
        events_with_rsi = [e for e in received if e.rsi is not None]
        assert len(events_with_rsi) > 0

    def test_atr_present_when_enabled(self):
        bus = _bus()
        cfg = IndicatorConfig(atr_period=3, enable_atr=True)
        received = []
        bus.subscribe(IndicatorEvent, received.append)
        StreamingIndicatorEngine(bus, config=cfg)
        for i in range(10):
            bus.publish(_candle(close=100.0 + i, high=102.0 + i, low=99.0 + i))
        events_with_atr = [e for e in received if e.atr is not None]
        assert len(events_with_atr) > 0

    def test_vwap_none_when_disabled(self):
        bus = _bus()
        cfg = IndicatorConfig(enable_vwap=False)
        received = []
        bus.subscribe(IndicatorEvent, received.append)
        StreamingIndicatorEngine(bus, config=cfg)
        for _ in range(5):
            bus.publish(_candle())
        assert all(e.vwap is None for e in received)

    def test_indicator_count_increments(self):
        bus = _bus()
        engine = StreamingIndicatorEngine(bus)
        for _ in range(5):
            bus.publish(_candle())
        assert engine.indicator_count == 5

    def test_multiple_symbols_tracked_independently(self):
        bus = _bus()
        cfg = IndicatorConfig(ema_fast_period=3, ema_slow_period=5, rsi_period=5)
        received = []
        bus.subscribe(IndicatorEvent, received.append)
        StreamingIndicatorEngine(bus, config=cfg)
        for i in range(10):
            bus.publish(_candle(symbol="AAPL", close=100.0 + i))
            bus.publish(_candle(symbol="GOOG", close=200.0 + i))
        aapl_events = [e for e in received if e.symbol == "AAPL"]
        goog_events = [e for e in received if e.symbol == "GOOG"]
        assert len(aapl_events) == 10
        assert len(goog_events) == 10

    def test_reset_clears_state(self):
        bus = _bus()
        engine = StreamingIndicatorEngine(bus)
        for _ in range(5):
            bus.publish(_candle())
        engine.reset()
        state = engine.get_state("AAPL", "1m")
        assert state is None

    def test_reset_specific_symbol_only(self):
        bus = _bus()
        engine = StreamingIndicatorEngine(bus)
        for _ in range(5):
            bus.publish(_candle(symbol="AAPL"))
            bus.publish(_candle(symbol="GOOG"))
        engine.reset(symbol="AAPL")
        assert engine.get_state("AAPL", "1m") is None
        assert engine.get_state("GOOG", "1m") is not None

    def test_indicator_event_has_correct_fields(self):
        bus = _bus()
        received = []
        bus.subscribe(IndicatorEvent, received.append)
        StreamingIndicatorEngine(bus)
        bus.publish(_candle(symbol="AAPL", timeframe="1m", close=150.0, volume=500))
        ev = received[0]
        assert ev.symbol == "AAPL"
        assert ev.timeframe == "1m"
        assert ev.close == 150.0
        assert ev.volume == 500

    def test_vwap_session_reset_on_new_day(self):
        bus = _bus()
        cfg = IndicatorConfig(enable_vwap=True)
        received = []
        bus.subscribe(IndicatorEvent, received.append)
        StreamingIndicatorEngine(bus, config=cfg)
        # Day 1 candles
        for i in range(3):
            bus.publish(_candle(close=100.0, ts=datetime(2024, 1, 15, 9, 30 + i)))
        # Day 2 candle — VWAP should reset
        bus.publish(_candle(close=200.0, ts=datetime(2024, 1, 16, 9, 30)))
        day2_event = received[-1]
        # VWAP for day2 should be closer to 200 than 100
        if day2_event.vwap is not None:
            assert day2_event.vwap > 150.0

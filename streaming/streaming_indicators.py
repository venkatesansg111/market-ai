"""Phase 9 — Streaming indicator engine: incremental EMA, RSI, VWAP, Volatility, ATR."""
from __future__ import annotations

import logging
import math
import statistics
from collections import deque
from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from streaming.event_bus import EventBus
from streaming.event_models import CandleEvent, IndicatorEvent

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Indicator configuration
# ──────────────────────────────────────────────────────────────────────

@dataclass
class IndicatorConfig:
    ema_fast_period: int = 9
    ema_slow_period: int = 21
    ema_200_period: int = 200
    rsi_period: int = 14
    volatility_period: int = 20
    atr_period: int = 14
    enable_ema_200: bool = False    # disabled by default; needs 200 candles
    enable_vwap: bool = True
    enable_volatility: bool = True
    enable_atr: bool = True


# ──────────────────────────────────────────────────────────────────────
# Per-series state holders (one per (symbol, timeframe) pair)
# ──────────────────────────────────────────────────────────────────────

@dataclass
class _EMAState:
    period: int
    alpha: float
    value: Optional[float] = None
    count: int = 0

    def update(self, price: float) -> Optional[float]:
        self.count += 1
        if self.value is None:
            self.value = price
        else:
            self.value = self.alpha * price + (1.0 - self.alpha) * self.value
        return self.value if self.count >= self.period else None

    @property
    def is_warm(self) -> bool:
        return self.count >= self.period


@dataclass
class _RSIState:
    period: int
    prices: deque = None       # rolling window of close prices
    avg_gain: float = 0.0
    avg_loss: float = 0.0
    count: int = 0

    def __post_init__(self):
        if self.prices is None:
            self.prices = deque(maxlen=self.period + 1)

    def update(self, price: float) -> Optional[float]:
        self.prices.append(price)
        self.count += 1

        if len(self.prices) < 2:
            return None

        change = self.prices[-1] - self.prices[-2]
        gain = max(0.0, change)
        loss = max(0.0, -change)

        if self.count <= self.period:
            # Initial simple average phase
            self.avg_gain = (self.avg_gain * (self.count - 1) + gain) / self.count
            self.avg_loss = (self.avg_loss * (self.count - 1) + loss) / self.count
        else:
            # Wilder's smoothing
            self.avg_gain = (self.avg_gain * (self.period - 1) + gain) / self.period
            self.avg_loss = (self.avg_loss * (self.period - 1) + loss) / self.period

        if self.count < self.period:
            return None

        if self.avg_loss < 1e-10:
            return 100.0
        rs = self.avg_gain / self.avg_loss
        return 100.0 - 100.0 / (1.0 + rs)

    @property
    def is_warm(self) -> bool:
        return self.count >= self.period


@dataclass
class _VWAPState:
    session_date: Optional[date] = None
    cumulative_pv: float = 0.0
    cumulative_vol: float = 0.0

    def update(self, candle: CandleEvent) -> Optional[float]:
        candle_date = (candle.candle_open_time or candle.timestamp).date()

        # Reset at start of new trading session
        if self.session_date is None or candle_date != self.session_date:
            self.session_date = candle_date
            self.cumulative_pv = 0.0
            self.cumulative_vol = 0.0

        typical_price = (float(candle.high) + float(candle.low) + float(candle.close)) / 3.0
        self.cumulative_pv += typical_price * candle.volume
        self.cumulative_vol += candle.volume

        if self.cumulative_vol == 0:
            return None
        return self.cumulative_pv / self.cumulative_vol


@dataclass
class _VolatilityState:
    period: int
    returns: deque = None

    def __post_init__(self):
        if self.returns is None:
            self.returns = deque(maxlen=self.period)

    _prev_close: Optional[float] = None

    def update(self, close: float) -> Optional[float]:
        if self._prev_close is not None and self._prev_close != 0:
            ret = (close - self._prev_close) / self._prev_close
            self.returns.append(ret)
        self._prev_close = close

        if len(self.returns) < 2:
            return None
        return statistics.stdev(self.returns)

    @property
    def is_warm(self) -> bool:
        return len(self.returns) >= 2


@dataclass
class _ATRState:
    period: int
    alpha: float = 0.0
    atr: Optional[float] = None
    prev_close: Optional[float] = None
    count: int = 0

    def __post_init__(self):
        self.alpha = 1.0 / self.period  # Wilder's smoothing

    def update(self, high: float, low: float, close: float) -> Optional[float]:
        if self.prev_close is None:
            self.prev_close = close
            return None

        tr = max(
            high - low,
            abs(high - self.prev_close),
            abs(low - self.prev_close),
        )
        self.prev_close = close
        self.count += 1

        if self.atr is None:
            self.atr = tr
        else:
            self.atr = self.alpha * tr + (1.0 - self.alpha) * self.atr

        return self.atr if self.count >= self.period else None

    @property
    def is_warm(self) -> bool:
        return self.count >= self.period


# ──────────────────────────────────────────────────────────────────────
# Per-(symbol, timeframe) state container
# ──────────────────────────────────────────────────────────────────────

@dataclass
class _SeriesState:
    ema_fast: _EMAState
    ema_slow: _EMAState
    ema_200: Optional[_EMAState]
    rsi: _RSIState
    vwap: Optional[_VWAPState]
    volatility: Optional[_VolatilityState]
    atr: Optional[_ATRState]


# ──────────────────────────────────────────────────────────────────────
# Streaming Indicator Engine
# ──────────────────────────────────────────────────────────────────────

class StreamingIndicatorEngine:
    """
    Subscribes to CandleEvent (closed candles only) and emits IndicatorEvent.

    Indicators are updated incrementally — no full-history recompute.
    The `is_warm` flag on IndicatorEvent is True when all mandatory
    indicators have sufficient history.

    Mandatory warm indicators:
      - ema_fast (period candles)
      - ema_slow (period candles)
      - rsi (period candles)
    Optional (don't affect is_warm):
      - ema_200, vwap, volatility, atr
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: IndicatorConfig | None = None,
    ) -> None:
        self._bus = event_bus
        self._cfg = config or IndicatorConfig()
        self._series: dict[tuple[str, str], _SeriesState] = {}
        self._indicator_count: int = 0

        event_bus.subscribe(CandleEvent, self.on_candle)

    # ──────────────────────────────────────────────────────────────────
    # Handler
    # ──────────────────────────────────────────────────────────────────

    def on_candle(self, event: CandleEvent) -> None:
        if not event.is_closed:
            return  # only process closed candles

        key = (event.symbol, event.timeframe)
        if key not in self._series:
            self._series[key] = self._make_series()

        s = self._series[key]
        close = float(event.close)
        high = float(event.high)
        low = float(event.low)

        ema_fast_val = s.ema_fast.update(close)
        ema_slow_val = s.ema_slow.update(close)
        ema_200_val = s.ema_200.update(close) if s.ema_200 else None
        rsi_val = s.rsi.update(close)
        vwap_val = s.vwap.update(event) if s.vwap else None
        vol_val = s.volatility.update(close) if s.volatility else None
        atr_val = s.atr.update(high, low, close) if s.atr else None

        is_warm = s.ema_fast.is_warm and s.ema_slow.is_warm and s.rsi.is_warm

        indicator_event = IndicatorEvent(
            symbol=event.symbol,
            timeframe=event.timeframe,
            timestamp=event.timestamp,
            close=close,
            high=high,
            low=low,
            volume=event.volume,
            ema_fast=ema_fast_val,
            ema_slow=ema_slow_val,
            ema_200=ema_200_val,
            rsi=rsi_val,
            vwap=vwap_val,
            volatility=vol_val,
            atr=atr_val,
            is_warm=is_warm,
        )
        self._bus.publish(indicator_event)
        self._indicator_count += 1

    # ──────────────────────────────────────────────────────────────────
    # State management
    # ──────────────────────────────────────────────────────────────────

    def _make_series(self) -> _SeriesState:
        cfg = self._cfg
        return _SeriesState(
            ema_fast=_EMAState(
                period=cfg.ema_fast_period,
                alpha=2.0 / (cfg.ema_fast_period + 1),
            ),
            ema_slow=_EMAState(
                period=cfg.ema_slow_period,
                alpha=2.0 / (cfg.ema_slow_period + 1),
            ),
            ema_200=_EMAState(
                period=cfg.ema_200_period,
                alpha=2.0 / (cfg.ema_200_period + 1),
            ) if cfg.enable_ema_200 else None,
            rsi=_RSIState(period=cfg.rsi_period),
            vwap=_VWAPState() if cfg.enable_vwap else None,
            volatility=_VolatilityState(period=cfg.volatility_period)
            if cfg.enable_volatility else None,
            atr=_ATRState(period=cfg.atr_period) if cfg.enable_atr else None,
        )

    def reset(self, symbol: str | None = None, timeframe: str | None = None) -> None:
        """Reset state for given (symbol, timeframe); pass None to reset all."""
        if symbol is None and timeframe is None:
            self._series.clear()
        else:
            keys = [k for k in self._series if
                    (symbol is None or k[0] == symbol) and
                    (timeframe is None or k[1] == timeframe)]
            for k in keys:
                del self._series[k]

    @property
    def indicator_count(self) -> int:
        return self._indicator_count

    def get_state(self, symbol: str, timeframe: str) -> Optional[_SeriesState]:
        return self._series.get((symbol, timeframe))

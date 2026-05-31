from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from signals.signal_models import SignalType


@dataclass(frozen=True, slots=True)
class CandleSnapshot:
    """Immutable OHLCV snapshot of a single bar passed to Strategy.generate_signal().

    Carries raw price/volume data for the current candle, separate from computed
    indicators. Strategies that compare close against VWAP use candle.close;
    strategies that rely purely on indicator values may ignore candle fields.
    """

    instrument: str
    timeframe: str
    candle_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int = 0


@dataclass(frozen=True, slots=True)
class StrategySignal:
    """Immutable signal produced by a Strategy for one bar.

    signal_type reuses SignalType so the backtest adapter can convert it
    to a TradeAction using the same mapping as SignalToTradeAdapter.

    Confidence scale (consistent with signal engine):
        0   = maximum bearish conviction
        50  = neutral / no-trade
        100 = maximum bullish conviction
    """

    instrument: str
    timeframe: str
    signal_time: datetime
    signal_type: SignalType
    confidence: int      # 0–100
    reason: str
    strategy_name: str

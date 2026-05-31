from __future__ import annotations

from indicators.indicator_models import IndicatorRecord
from signals.signal_models import SignalType
from strategies.base import Strategy
from strategies.strategy_models import CandleSnapshot, StrategySignal

_STRONG_BUY_CONFIDENCE = 80   # all three EMAs fully aligned bullish
_STRONG_SELL_CONFIDENCE = 20  # all three EMAs fully aligned bearish (0-100 scale)
_NO_TRADE_CONFIDENCE = 50


class EmaCrossoverStrategy(Strategy):
    """EMA triple-crossover strategy: trades only full three-EMA alignment.

    BUY  (STRONG_BUY):  EMA20 > EMA50 > EMA200 — full bullish stack
    SELL (STRONG_SELL): EMA20 < EMA50 < EMA200 — full bearish stack
    NO_TRADE: partial alignment, all EMAs equal, or any EMA missing

    Requires EMA200 warmup (~200 bars). Returns NO_TRADE during warmup.
    """

    @property
    def strategy_name(self) -> str:
        return "ema"

    @property
    def description(self) -> str:
        return (
            "EMA triple crossover (EMA20/EMA50/EMA200): "
            "STRONG_BUY on full bullish stack, STRONG_SELL on full bearish stack"
        )

    @property
    def required_indicators(self) -> list[str]:
        # adx_14 and supertrend are consumed by future trend-confluence logic;
        # generate_signal() reads only the three EMAs and handles None gracefully.
        return ["ema20", "ema50", "ema200", "adx_14", "supertrend"]

    def generate_signal(
        self,
        candle: CandleSnapshot,
        indicators: IndicatorRecord,
    ) -> StrategySignal:
        ema20 = indicators.ema20
        ema50 = indicators.ema50
        ema200 = indicators.ema200

        if ema20 is None or ema50 is None or ema200 is None:
            return self._make(
                candle, SignalType.NO_TRADE, _NO_TRADE_CONFIDENCE,
                "Insufficient EMA data — waiting for EMA200 warmup",
            )

        if ema20 > ema50 > ema200:
            return self._make(
                candle, SignalType.STRONG_BUY, _STRONG_BUY_CONFIDENCE,
                f"EMA20({float(ema20):.2f}) > EMA50({float(ema50):.2f})"
                f" > EMA200({float(ema200):.2f}) — full bullish alignment",
            )

        if ema20 < ema50 < ema200:
            return self._make(
                candle, SignalType.STRONG_SELL, _STRONG_SELL_CONFIDENCE,
                f"EMA20({float(ema20):.2f}) < EMA50({float(ema50):.2f})"
                f" < EMA200({float(ema200):.2f}) — full bearish alignment",
            )

        return self._make(
            candle, SignalType.NO_TRADE, _NO_TRADE_CONFIDENCE,
            "Partial or conflicting EMA alignment — no trade",
        )

    def _make(
        self,
        candle: CandleSnapshot,
        signal_type: SignalType,
        confidence: int,
        reason: str,
    ) -> StrategySignal:
        return StrategySignal(
            instrument=candle.instrument,
            timeframe=candle.timeframe,
            signal_time=candle.candle_time,
            signal_type=signal_type,
            confidence=confidence,
            reason=reason,
            strategy_name=self.strategy_name,
        )

from __future__ import annotations

from indicators.indicator_models import IndicatorRecord
from signals.signal_models import SignalType
from strategies.base import Strategy
from strategies.strategy_models import CandleSnapshot, StrategySignal

_BUY_CONFIDENCE = 70   # close > VWAP + RSI bullish
_SELL_CONFIDENCE = 30  # close < VWAP + RSI bearish
_NO_TRADE_CONFIDENCE = 50


class VWAPBreakoutStrategy(Strategy):
    """VWAP breakout strategy with RSI confirmation.

    BUY:      Close > VWAP  AND  RSI > 55 — price breaking above VWAP with momentum
    SELL:     Close < VWAP  AND  RSI < 45 — price breaking below VWAP with momentum
    NO_TRADE: conflicting signals, neutral RSI, or missing VWAP/RSI data

    Both conditions must be met simultaneously — VWAP alone or RSI alone is not enough.
    """

    @property
    def strategy_name(self) -> str:
        return "vwap"

    @property
    def description(self) -> str:
        return (
            "VWAP breakout confirmed by RSI: "
            "BUY when Close>VWAP and RSI>55; SELL when Close<VWAP and RSI<45"
        )

    @property
    def required_indicators(self) -> list[str]:
        return ["vwap", "rsi14"]

    def generate_signal(
        self,
        candle: CandleSnapshot,
        indicators: IndicatorRecord,
    ) -> StrategySignal:
        vwap = indicators.vwap
        rsi = indicators.rsi14

        if vwap is None or rsi is None:
            return self._make(
                candle, SignalType.NO_TRADE, _NO_TRADE_CONFIDENCE,
                "Insufficient VWAP/RSI data",
            )

        rsi_val = float(rsi)
        close = candle.close

        if close > vwap and rsi_val > 55:
            return self._make(
                candle, SignalType.BUY, _BUY_CONFIDENCE,
                f"Close({float(close):.2f}) > VWAP({float(vwap):.2f})"
                f" AND RSI({rsi_val:.1f}) > 55 — breakout confirmed",
            )

        if close < vwap and rsi_val < 45:
            return self._make(
                candle, SignalType.SELL, _SELL_CONFIDENCE,
                f"Close({float(close):.2f}) < VWAP({float(vwap):.2f})"
                f" AND RSI({rsi_val:.1f}) < 45 — breakdown confirmed",
            )

        return self._make(
            candle, SignalType.NO_TRADE, _NO_TRADE_CONFIDENCE,
            f"Close vs VWAP and RSI({rsi_val:.1f}) conditions not both met — no trade",
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

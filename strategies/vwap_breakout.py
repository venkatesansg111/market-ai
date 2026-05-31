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

    BUY:      Close > VWAP  AND  RSI > rsi_buy_threshold
    SELL:     Close < VWAP  AND  RSI < rsi_sell_threshold
    NO_TRADE: conflicting signals or missing data
    """

    def __init__(
        self,
        rsi_buy_threshold: float = 55.0,
        rsi_sell_threshold: float = 45.0,
    ) -> None:
        self._rsi_buy = rsi_buy_threshold
        self._rsi_sell = rsi_sell_threshold

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

        if close > vwap and rsi_val > self._rsi_buy:
            return self._make(
                candle, SignalType.BUY, _BUY_CONFIDENCE,
                f"Close({float(close):.2f}) > VWAP({float(vwap):.2f})"
                f" AND RSI({rsi_val:.1f}) > {self._rsi_buy} — breakout confirmed",
            )

        if close < vwap and rsi_val < self._rsi_sell:
            return self._make(
                candle, SignalType.SELL, _SELL_CONFIDENCE,
                f"Close({float(close):.2f}) < VWAP({float(vwap):.2f})"
                f" AND RSI({rsi_val:.1f}) < {self._rsi_sell} — breakdown confirmed",
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

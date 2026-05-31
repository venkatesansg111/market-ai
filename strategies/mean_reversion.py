from __future__ import annotations

from indicators.indicator_models import IndicatorRecord
from signals.signal_models import SignalType
from strategies.base import Strategy
from strategies.strategy_models import CandleSnapshot, StrategySignal

_BUY_CONFIDENCE = 75   # RSI deeply oversold — expect bounce
_SELL_CONFIDENCE = 25  # RSI deeply overbought — expect reversion
_NO_TRADE_CONFIDENCE = 50


class MeanReversionStrategy(Strategy):
    """RSI mean-reversion strategy: fades extreme readings.

    BUY:      RSI < rsi_oversold  — oversold, bounce expected
    SELL:     RSI > rsi_overbought — overbought, reversion expected
    NO_TRADE: RSI in [rsi_oversold, rsi_overbought] or data unavailable

    Boundary values are NOT signals — strict inequalities.
    """

    def __init__(
        self,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
    ) -> None:
        self._rsi_oversold = rsi_oversold
        self._rsi_overbought = rsi_overbought

    @property
    def strategy_name(self) -> str:
        return "mean_reversion"

    @property
    def description(self) -> str:
        return (
            "RSI mean reversion: BUY when RSI<30 (oversold); "
            "SELL when RSI>70 (overbought)"
        )

    @property
    def required_indicators(self) -> list[str]:
        return ["rsi14"]

    def generate_signal(
        self,
        candle: CandleSnapshot,
        indicators: IndicatorRecord,
    ) -> StrategySignal:
        if indicators.rsi14 is None:
            return self._make(
                candle, SignalType.NO_TRADE, _NO_TRADE_CONFIDENCE,
                "RSI data unavailable — waiting for warmup",
            )

        rsi_val = float(indicators.rsi14)

        if rsi_val < self._rsi_oversold:
            return self._make(
                candle, SignalType.BUY, _BUY_CONFIDENCE,
                f"RSI({rsi_val:.1f}) < {self._rsi_oversold} — oversold, mean reversion buy",
            )

        if rsi_val > self._rsi_overbought:
            return self._make(
                candle, SignalType.SELL, _SELL_CONFIDENCE,
                f"RSI({rsi_val:.1f}) > {self._rsi_overbought} — overbought, mean reversion sell",
            )

        return self._make(
            candle, SignalType.NO_TRADE, _NO_TRADE_CONFIDENCE,
            f"RSI({rsi_val:.1f}) in [{self._rsi_oversold}, {self._rsi_overbought}] — no reversion signal",
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

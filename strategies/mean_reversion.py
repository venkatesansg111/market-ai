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

    BUY:      RSI < 30 — oversold, price expected to bounce toward mean
    SELL:     RSI > 70 — overbought, price expected to revert toward mean
    NO_TRADE: RSI in [30, 70], or RSI data unavailable

    Boundary values (RSI == 30 or RSI == 70) are NOT signals — strict inequalities.
    """

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

        if rsi_val < 30:
            return self._make(
                candle, SignalType.BUY, _BUY_CONFIDENCE,
                f"RSI({rsi_val:.1f}) < 30 — oversold, mean reversion buy",
            )

        if rsi_val > 70:
            return self._make(
                candle, SignalType.SELL, _SELL_CONFIDENCE,
                f"RSI({rsi_val:.1f}) > 70 — overbought, mean reversion sell",
            )

        return self._make(
            candle, SignalType.NO_TRADE, _NO_TRADE_CONFIDENCE,
            f"RSI({rsi_val:.1f}) in [30, 70] — no reversion signal",
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

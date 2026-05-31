from __future__ import annotations

from indicators.indicator_models import IndicatorRecord
from signals.signal_models import SignalType
from strategies.base import Strategy
from strategies.strategy_models import CandleSnapshot, StrategySignal

_BUY_CONFIDENCE = 75   # RSI overbought territory + MACD bullish
_SELL_CONFIDENCE = 25  # RSI oversold territory + MACD bearish
_NO_TRADE_CONFIDENCE = 50


class MomentumStrategy(Strategy):
    """Dual-momentum strategy: RSI and MACD crossover must agree.

    BUY:      RSI > rsi_buy_threshold  AND  MACD > Signal
    SELL:     RSI < rsi_sell_threshold AND  MACD < Signal
    NO_TRADE: conflicting signals or any required indicator missing
    """

    def __init__(
        self,
        rsi_buy_threshold: float = 60.0,
        rsi_sell_threshold: float = 40.0,
    ) -> None:
        self._rsi_buy = rsi_buy_threshold
        self._rsi_sell = rsi_sell_threshold

    @property
    def strategy_name(self) -> str:
        return "momentum"

    @property
    def description(self) -> str:
        return (
            "Dual momentum: BUY when RSI>60 and MACD>Signal; "
            "SELL when RSI<40 and MACD<Signal"
        )

    @property
    def required_indicators(self) -> list[str]:
        # adx_14 and obv are consumed by future scanner/confluence logic;
        # this strategy's generate_signal() reads only rsi14, macd, macd_signal
        # and gracefully handles None for any additional fields.
        return ["rsi14", "macd", "macd_signal", "adx_14", "obv"]

    def generate_signal(
        self,
        candle: CandleSnapshot,
        indicators: IndicatorRecord,
    ) -> StrategySignal:
        rsi = indicators.rsi14
        macd = indicators.macd
        macd_signal = indicators.macd_signal

        if rsi is None or macd is None or macd_signal is None:
            return self._make(
                candle, SignalType.NO_TRADE, _NO_TRADE_CONFIDENCE,
                "Insufficient RSI/MACD data — waiting for warmup",
            )

        rsi_val = float(rsi)

        if rsi_val > self._rsi_buy and macd > macd_signal:
            return self._make(
                candle, SignalType.BUY, _BUY_CONFIDENCE,
                f"RSI({rsi_val:.1f}) > {self._rsi_buy} AND MACD({float(macd):.4f})"
                f" > Signal({float(macd_signal):.4f}) — bullish momentum",
            )

        if rsi_val < self._rsi_sell and macd < macd_signal:
            return self._make(
                candle, SignalType.SELL, _SELL_CONFIDENCE,
                f"RSI({rsi_val:.1f}) < {self._rsi_sell} AND MACD({float(macd):.4f})"
                f" < Signal({float(macd_signal):.4f}) — bearish momentum",
            )

        return self._make(
            candle, SignalType.NO_TRADE, _NO_TRADE_CONFIDENCE,
            f"RSI({rsi_val:.1f}) and MACD not aligned — no trade",
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

"""Momentum Confluence Strategy — multi-timeframe MACD + RSI + OBV.

Signal logic:
    Trend timeframe  (default 15min):  MACD > MACD Signal  (momentum direction)
    Setup timeframe  (default 5min):   RSI > 60            (momentum strength)
    Entry timeframe  (default 1min):   OBV Rising          (volume confirmation)

    BUY  when all three conditions are bullish.
    SELL when all three conditions are bearish
         (MACD < Signal + RSI < 40 + OBV falling).

OBV direction requires two consecutive IndicatorRecords.
The backtesting adapter supplies ``prev_aligned_records`` for this purpose.
When previous data is unavailable, the OBV condition is skipped (counts as
neutral) and a signal may still fire on the other two conditions alone, with
reduced confidence.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from indicators.indicator_models import IndicatorRecord
from signals.signal_models import SignalType
from strategies.multi_timeframe_base import MultiTimeframeStrategy
from strategies.strategy_models import StrategySignal

_RSI_BULL: float = 60.0
_RSI_BEAR: float = 40.0


class MomentumConfluenceStrategy(MultiTimeframeStrategy):
    """Multi-timeframe momentum strategy: MACD, RSI, and OBV direction.

    Uses shorter timeframes than trend-following strategies, making it
    suitable for intraday momentum trades.

    Confidence levels:
        All three conditions confirmed  → confidence 75 (BUY) / 25 (SELL).
        Only MACD + RSI confirmed       → confidence 65 (BUY) / 35 (SELL).
        Only one condition confirmed    → NO_TRADE.
    """

    def __init__(
        self,
        trend_tf: str = "15min",
        setup_tf: str = "5min",
        entry_tf: str = "1min",
        rsi_bull: float = _RSI_BULL,
        rsi_bear: float = _RSI_BEAR,
    ) -> None:
        self._trend_tf = trend_tf
        self._setup_tf = setup_tf
        self._entry_tf = entry_tf
        self._rsi_bull = rsi_bull
        self._rsi_bear = rsi_bear

    # ------------------------------------------------------------------
    # Strategy ABC properties
    # ------------------------------------------------------------------

    @property
    def strategy_name(self) -> str:
        return "momentum_confluence"

    @property
    def description(self) -> str:
        return (
            "Multi-timeframe momentum confluence: "
            f"MACD ({self._trend_tf}) + RSI>{_RSI_BULL:.0f} ({self._setup_tf}) "
            f"+ OBV rising ({self._entry_tf})"
        )

    @property
    def required_indicators(self) -> list[str]:
        return ["macd", "macd_signal", "rsi14", "obv"]

    # ------------------------------------------------------------------
    # MultiTimeframeStrategy properties
    # ------------------------------------------------------------------

    @property
    def trend_timeframe(self) -> str:
        return self._trend_tf

    @property
    def setup_timeframe(self) -> str:
        return self._setup_tf

    @property
    def entry_timeframe(self) -> str:
        return self._entry_tf

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def generate_multi_signal(
        self,
        aligned_records: dict[str, Optional[IndicatorRecord]],
        current_price: Decimal,
        prev_aligned_records: Optional[dict[str, Optional[IndicatorRecord]]] = None,
    ) -> StrategySignal:
        trend_rec = aligned_records.get(self._trend_tf)
        setup_rec = aligned_records.get(self._setup_tf)
        entry_rec = aligned_records.get(self._entry_tf)

        prev_map = prev_aligned_records or {}
        prev_entry_rec = prev_map.get(self._entry_tf)

        ref_rec = entry_rec or next(
            (r for r in aligned_records.values() if r is not None), None
        )
        if ref_rec is None:
            return self._fallback_signal("No indicator data available for any timeframe")

        reasons: list[str] = []

        # ── Trend timeframe: MACD direction ────────────────────────────
        macd_bullish = False
        macd_bearish = False
        if trend_rec is not None and trend_rec.macd is not None and trend_rec.macd_signal is not None:
            macd = float(trend_rec.macd)
            sig = float(trend_rec.macd_signal)
            if macd > sig:
                macd_bullish = True
                reasons.append(f"[{self._trend_tf}] MACD={macd:.4f} > Signal={sig:.4f}")
            elif macd < sig:
                macd_bearish = True
                reasons.append(f"[{self._trend_tf}] MACD={macd:.4f} < Signal={sig:.4f}")
            else:
                reasons.append(f"[{self._trend_tf}] MACD == Signal (no edge)")
        else:
            reasons.append(f"[{self._trend_tf}] MACD data unavailable")

        # ── Setup timeframe: RSI > 60 ───────────────────────────────────
        rsi_bullish = False
        rsi_bearish = False
        if setup_rec is not None and setup_rec.rsi14 is not None:
            rsi = float(setup_rec.rsi14)
            if rsi > self._rsi_bull:
                rsi_bullish = True
                reasons.append(f"[{self._setup_tf}] RSI={rsi:.1f} > {self._rsi_bull}")
            elif rsi < self._rsi_bear:
                rsi_bearish = True
                reasons.append(f"[{self._setup_tf}] RSI={rsi:.1f} < {self._rsi_bear}")
            else:
                reasons.append(f"[{self._setup_tf}] RSI={rsi:.1f} neutral")
        else:
            reasons.append(f"[{self._setup_tf}] RSI data unavailable")

        # ── Entry timeframe: OBV direction ──────────────────────────────
        obv_bullish = False
        obv_bearish = False
        obv_available = False
        if (
            entry_rec is not None
            and entry_rec.obv is not None
            and prev_entry_rec is not None
            and prev_entry_rec.obv is not None
        ):
            obv_available = True
            curr_obv = float(entry_rec.obv)
            prev_obv = float(prev_entry_rec.obv)
            if curr_obv > prev_obv:
                obv_bullish = True
                reasons.append(f"[{self._entry_tf}] OBV rising {prev_obv:.0f}→{curr_obv:.0f}")
            elif curr_obv < prev_obv:
                obv_bearish = True
                reasons.append(f"[{self._entry_tf}] OBV falling {prev_obv:.0f}→{curr_obv:.0f}")
            else:
                reasons.append(f"[{self._entry_tf}] OBV flat at {curr_obv:.0f}")
        else:
            reasons.append(f"[{self._entry_tf}] OBV direction unavailable (no prior bar)")

        reason_str = "; ".join(reasons)

        # ── Signal decision ─────────────────────────────────────────────
        # Full confluence: all three conditions confirmed
        if macd_bullish and rsi_bullish and obv_bullish:
            return self._make(ref_rec, SignalType.BUY, 75, reason_str)

        if macd_bearish and rsi_bearish and obv_bearish:
            return self._make(ref_rec, SignalType.SELL, 25, reason_str)

        # Partial confluence: MACD + RSI confirmed (OBV unavailable or flat)
        if macd_bullish and rsi_bullish and not obv_available:
            return self._make(ref_rec, SignalType.BUY, 65, reason_str)

        if macd_bearish and rsi_bearish and not obv_available:
            return self._make(ref_rec, SignalType.SELL, 35, reason_str)

        return self._make(ref_rec, SignalType.NO_TRADE, 50, reason_str)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _make(
        self,
        ref_rec: IndicatorRecord,
        signal_type: SignalType,
        confidence: int,
        reason: str,
    ) -> StrategySignal:
        return StrategySignal(
            instrument=ref_rec.instrument,
            timeframe=ref_rec.timeframe,
            signal_time=ref_rec.candle_time,
            signal_type=signal_type,
            confidence=confidence,
            reason=reason,
            strategy_name=self.strategy_name,
        )

    def _fallback_signal(self, reason: str) -> StrategySignal:
        return StrategySignal(
            instrument="",
            timeframe=self._entry_tf,
            signal_time=datetime.utcnow(),
            signal_type=SignalType.NO_TRADE,
            confidence=50,
            reason=reason,
            strategy_name=self.strategy_name,
        )

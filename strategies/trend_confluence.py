"""Trend Confluence Strategy — multi-timeframe EMA + ADX + VWAP.

Signal logic:
    Trend timeframe  (default 1day):   EMA20 > EMA50 > EMA200  (bullish stack)
    Setup timeframe  (default 15min):  ADX > 25                (trend strength)
    Entry timeframe  (default 5min):   Price > VWAP            (entry confirmation)

    BUY  when all three conditions are bullish.
    SELL when all three conditions are bearish
         (EMA bear stack + ADX > 25 + price < VWAP).

Timeframes are configurable via the constructor to support different
combinations such as ``15min / 5min / 1min``.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from indicators.indicator_models import IndicatorRecord
from signals.signal_models import SignalType
from strategies.multi_timeframe_base import MultiTimeframeStrategy
from strategies.strategy_models import StrategySignal

_ADX_THRESHOLD: float = 25.0


class TrendConfluenceStrategy(MultiTimeframeStrategy):
    """Multi-timeframe trend following strategy.

    Combines EMA stack alignment on the trend timeframe with ADX trend
    strength on the setup timeframe and VWAP price confirmation on the
    entry timeframe.
    """

    def __init__(
        self,
        trend_tf: str = "1day",
        setup_tf: str = "15min",
        entry_tf: str = "5min",
    ) -> None:
        self._trend_tf = trend_tf
        self._setup_tf = setup_tf
        self._entry_tf = entry_tf

    # ------------------------------------------------------------------
    # Strategy ABC properties
    # ------------------------------------------------------------------

    @property
    def strategy_name(self) -> str:
        return "trend_confluence"

    @property
    def description(self) -> str:
        return (
            "Multi-timeframe trend confluence: "
            f"EMA stack ({self._trend_tf}) + ADX>25 ({self._setup_tf}) "
            f"+ Price>VWAP ({self._entry_tf})"
        )

    @property
    def required_indicators(self) -> list[str]:
        return ["ema20", "ema50", "ema200", "adx_14", "vwap"]

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

        ref_rec = entry_rec or next(
            (r for r in aligned_records.values() if r is not None), None
        )
        if ref_rec is None:
            return self._fallback_signal("No indicator data available for any timeframe")

        reasons: list[str] = []

        # ── Trend timeframe: EMA stack ──────────────────────────────────
        trend_bullish = False
        trend_bearish = False
        if trend_rec is not None:
            e20, e50, e200 = trend_rec.ema20, trend_rec.ema50, trend_rec.ema200
            if None not in (e20, e50, e200):
                if e20 > e50 > e200:
                    trend_bullish = True
                    reasons.append(
                        f"[{self._trend_tf}] EMA bull: "
                        f"{float(e20):.1f}>{float(e50):.1f}>{float(e200):.1f}"
                    )
                elif e20 < e50 < e200:
                    trend_bearish = True
                    reasons.append(
                        f"[{self._trend_tf}] EMA bear: "
                        f"{float(e20):.1f}<{float(e50):.1f}<{float(e200):.1f}"
                    )
                else:
                    reasons.append(f"[{self._trend_tf}] EMA mixed — no clear stack")
            else:
                reasons.append(f"[{self._trend_tf}] EMA data unavailable")
        else:
            reasons.append(f"[{self._trend_tf}] No trend-timeframe data")

        # ── Setup timeframe: ADX > 25 ───────────────────────────────────
        adx_confirms = False
        if setup_rec is not None and setup_rec.adx_14 is not None:
            adx = float(setup_rec.adx_14)
            if adx > _ADX_THRESHOLD:
                adx_confirms = True
                reasons.append(f"[{self._setup_tf}] ADX={adx:.1f} > {_ADX_THRESHOLD}")
            else:
                reasons.append(f"[{self._setup_tf}] ADX={adx:.1f} ≤ {_ADX_THRESHOLD} (weak)")
        else:
            reasons.append(f"[{self._setup_tf}] ADX data unavailable")

        # ── Entry timeframe: Price vs VWAP ─────────────────────────────
        price_above_vwap = False
        price_below_vwap = False
        if entry_rec is not None and entry_rec.vwap is not None:
            vwap = entry_rec.vwap
            if current_price > vwap:
                price_above_vwap = True
                reasons.append(f"[{self._entry_tf}] Price {float(current_price):.1f} > VWAP {float(vwap):.1f}")
            else:
                price_below_vwap = True
                reasons.append(f"[{self._entry_tf}] Price {float(current_price):.1f} ≤ VWAP {float(vwap):.1f}")
        else:
            reasons.append(f"[{self._entry_tf}] VWAP data unavailable")

        reason_str = "; ".join(reasons)

        # ── Signal decision ─────────────────────────────────────────────
        if trend_bullish and adx_confirms and price_above_vwap:
            return self._make(ref_rec, SignalType.BUY, 75, reason_str)

        if trend_bearish and adx_confirms and price_below_vwap:
            return self._make(ref_rec, SignalType.SELL, 25, reason_str)

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

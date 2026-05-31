"""Supertrend Confluence Strategy — multi-timeframe Supertrend + ADX + RSI.

Signal logic:
    Trend timeframe  (default 1day):   Supertrend direction = +1 (bullish)
    Setup timeframe  (default 15min):  ADX > 25               (trend strength)
    Entry timeframe  (default 5min):   RSI > 55               (momentum confirmation)

    BUY  when all three conditions are bullish.
    SELL when all three conditions are bearish
         (Supertrend direction = -1 + ADX > 25 + RSI < 45).
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
_RSI_BULL: float = 55.0
_RSI_BEAR: float = 45.0


class SupertrendConfluenceStrategy(MultiTimeframeStrategy):
    """Multi-timeframe strategy combining Supertrend, ADX, and RSI.

    Trend direction is set by the Supertrend indicator on the trend timeframe.
    ADX on the setup timeframe filters out low-conviction ranging markets.
    RSI on the entry timeframe confirms momentum before entry.
    """

    def __init__(
        self,
        trend_tf: str = "1day",
        setup_tf: str = "15min",
        entry_tf: str = "5min",
        adx_threshold: float = _ADX_THRESHOLD,
        rsi_bull: float = _RSI_BULL,
        rsi_bear: float = _RSI_BEAR,
    ) -> None:
        self._trend_tf = trend_tf
        self._setup_tf = setup_tf
        self._entry_tf = entry_tf
        self._adx_threshold = adx_threshold
        self._rsi_bull = rsi_bull
        self._rsi_bear = rsi_bear

    # ------------------------------------------------------------------
    # Strategy ABC properties
    # ------------------------------------------------------------------

    @property
    def strategy_name(self) -> str:
        return "supertrend_confluence"

    @property
    def description(self) -> str:
        return (
            "Multi-timeframe Supertrend confluence: "
            f"Supertrend direction ({self._trend_tf}) + ADX>25 ({self._setup_tf}) "
            f"+ RSI>{_RSI_BULL:.0f} ({self._entry_tf})"
        )

    @property
    def required_indicators(self) -> list[str]:
        return ["supertrend_direction", "adx_14", "rsi14"]

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

        # ── Trend timeframe: Supertrend direction ───────────────────────
        trend_bullish = False
        trend_bearish = False
        if trend_rec is not None and trend_rec.supertrend_direction is not None:
            direction = trend_rec.supertrend_direction
            if direction == 1:
                trend_bullish = True
                reasons.append(f"[{self._trend_tf}] Supertrend bullish (direction=+1)")
            elif direction == -1:
                trend_bearish = True
                reasons.append(f"[{self._trend_tf}] Supertrend bearish (direction=-1)")
            else:
                reasons.append(f"[{self._trend_tf}] Supertrend neutral (direction={direction})")
        else:
            reasons.append(f"[{self._trend_tf}] Supertrend data unavailable")

        # ── Setup timeframe: ADX > 25 ───────────────────────────────────
        adx_confirms = False
        if setup_rec is not None and setup_rec.adx_14 is not None:
            adx = float(setup_rec.adx_14)
            if adx > self._adx_threshold:
                adx_confirms = True
                reasons.append(f"[{self._setup_tf}] ADX={adx:.1f} > {self._adx_threshold}")
            else:
                reasons.append(f"[{self._setup_tf}] ADX={adx:.1f} ≤ {self._adx_threshold} (weak trend)")
        else:
            reasons.append(f"[{self._setup_tf}] ADX data unavailable")

        # ── Entry timeframe: RSI momentum ───────────────────────────────
        rsi_bullish = False
        rsi_bearish = False
        if entry_rec is not None and entry_rec.rsi14 is not None:
            rsi = float(entry_rec.rsi14)
            if rsi > self._rsi_bull:
                rsi_bullish = True
                reasons.append(f"[{self._entry_tf}] RSI={rsi:.1f} > {self._rsi_bull}")
            elif rsi < self._rsi_bear:
                rsi_bearish = True
                reasons.append(f"[{self._entry_tf}] RSI={rsi:.1f} < {self._rsi_bear}")
            else:
                reasons.append(f"[{self._entry_tf}] RSI={rsi:.1f} neutral ({self._rsi_bear}–{self._rsi_bull})")
        else:
            reasons.append(f"[{self._entry_tf}] RSI data unavailable")

        reason_str = "; ".join(reasons)

        # ── Signal decision ─────────────────────────────────────────────
        if trend_bullish and adx_confirms and rsi_bullish:
            return self._make(ref_rec, SignalType.BUY, 75, reason_str)

        if trend_bearish and adx_confirms and rsi_bearish:
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

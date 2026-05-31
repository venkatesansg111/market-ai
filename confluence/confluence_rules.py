"""Reusable, stateless confluence rule definitions.

Each rule class exposes:
    name       — unique string key used in the registry.
    max_score  — maximum positive contribution to the aggregate score.

    evaluate(indicators, prev_indicators=None, current_price=None)
        → RuleResult

Rules return positive scores for bullish conditions and negative scores for
bearish conditions.  A score of zero means neutral or data unavailable.

Scoring design — maximum bullish total = 100:

    EMA Alignment       +20
    ADX Strength        +15
    VWAP Confirmation   +15
    Supertrend          +20
    MACD Confirmation   +15
    RSI Momentum        +15   (strong signal only)
    OBV Confirmation    +15
    Breakout            +15   (partial — only one rule applies per bar)

Total max if all rules fire = 100 (some rules are exclusive by design).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from indicators.indicator_models import IndicatorRecord


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RuleResult:
    """Immutable output of a single confluence rule evaluation.

    Attributes:
        score:     Raw score contribution. Positive = bullish, negative = bearish.
        reason:    Human-readable explanation (empty string when unavailable).
        available: ``False`` when required indicator data is missing, meaning the
                   rule did not fire and the score is always 0.
    """

    score: int
    reason: str
    available: bool


# ---------------------------------------------------------------------------
# Rule base (documentation only — rules are duck-typed via evaluate())
# ---------------------------------------------------------------------------

class _BaseRule:
    """Mixin that makes rule evaluation callable via __call__."""

    name: str = ""
    max_score: int = 0

    def __call__(
        self,
        indicators: IndicatorRecord,
        prev_indicators: Optional[IndicatorRecord] = None,
        current_price: Optional[Decimal] = None,
    ) -> RuleResult:
        return self.evaluate(indicators, prev_indicators, current_price)

    def evaluate(
        self,
        indicators: IndicatorRecord,
        prev_indicators: Optional[IndicatorRecord] = None,
        current_price: Optional[Decimal] = None,
    ) -> RuleResult:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# EMA Alignment  (+/- 20)
# ---------------------------------------------------------------------------

class EmaAlignmentRule(_BaseRule):
    """Score based on EMA 20 / 50 / 200 stack alignment.

    Bullish  (+20): EMA20 > EMA50 > EMA200
    Bearish  (-20): EMA20 < EMA50 < EMA200
    Neutral  (  0): Mixed alignment or any EMA is None.
    """

    name = "ema_alignment"
    max_score = 20

    def evaluate(
        self,
        indicators: IndicatorRecord,
        prev_indicators: Optional[IndicatorRecord] = None,
        current_price: Optional[Decimal] = None,
    ) -> RuleResult:
        e20, e50, e200 = indicators.ema20, indicators.ema50, indicators.ema200
        if None in (e20, e50, e200):
            return RuleResult(score=0, reason="EMA alignment: data unavailable", available=False)

        if e20 > e50 > e200:
            return RuleResult(
                score=20,
                reason=f"EMA bull stack: {float(e20):.2f}>{float(e50):.2f}>{float(e200):.2f}",
                available=True,
            )
        if e20 < e50 < e200:
            return RuleResult(
                score=-20,
                reason=f"EMA bear stack: {float(e20):.2f}<{float(e50):.2f}<{float(e200):.2f}",
                available=True,
            )
        return RuleResult(
            score=0,
            reason=f"EMA mixed: {float(e20):.2f}/{float(e50):.2f}/{float(e200):.2f}",
            available=True,
        )


# ---------------------------------------------------------------------------
# ADX Strength  (+15 / 0)
# ---------------------------------------------------------------------------

class AdxStrengthRule(_BaseRule):
    """Score based on ADX trend-strength threshold.

    ADX > 25 → strong trend → +15 (direction-agnostic; amplifies existing bias).
    ADX ≤ 25 → weak / choppy →  0.
    Missing   →  0.

    ADX confirms directional strength but does not itself give direction.
    Used to gate other directional signals.
    """

    name = "adx_strength"
    max_score = 15
    _THRESHOLD: float = 25.0

    def evaluate(
        self,
        indicators: IndicatorRecord,
        prev_indicators: Optional[IndicatorRecord] = None,
        current_price: Optional[Decimal] = None,
    ) -> RuleResult:
        if indicators.adx_14 is None:
            return RuleResult(score=0, reason="ADX: data unavailable", available=False)

        adx = float(indicators.adx_14)
        if adx > self._THRESHOLD:
            return RuleResult(
                score=15,
                reason=f"ADX={adx:.1f} > {self._THRESHOLD} (strong trend)",
                available=True,
            )
        return RuleResult(
            score=0,
            reason=f"ADX={adx:.1f} <= {self._THRESHOLD} (weak trend)",
            available=True,
        )


# ---------------------------------------------------------------------------
# VWAP Confirmation  (+/- 15)
# ---------------------------------------------------------------------------

class VWAPConfirmationRule(_BaseRule):
    """Score based on price position relative to VWAP.

    Price > VWAP → +15 (buyers in control).
    Price < VWAP → -15 (sellers in control).
    VWAP or price unavailable → 0.
    """

    name = "vwap_confirmation"
    max_score = 15

    def evaluate(
        self,
        indicators: IndicatorRecord,
        prev_indicators: Optional[IndicatorRecord] = None,
        current_price: Optional[Decimal] = None,
    ) -> RuleResult:
        vwap = indicators.vwap
        price = current_price

        if vwap is None:
            return RuleResult(score=0, reason="VWAP: data unavailable", available=False)
        if price is None:
            return RuleResult(score=0, reason="VWAP: current price unavailable", available=False)

        if price > vwap:
            return RuleResult(
                score=15,
                reason=f"Price {float(price):.2f} > VWAP {float(vwap):.2f}",
                available=True,
            )
        if price < vwap:
            return RuleResult(
                score=-15,
                reason=f"Price {float(price):.2f} < VWAP {float(vwap):.2f}",
                available=True,
            )
        return RuleResult(
            score=0,
            reason=f"Price == VWAP {float(vwap):.2f}",
            available=True,
        )


# ---------------------------------------------------------------------------
# Supertrend  (+/- 20)
# ---------------------------------------------------------------------------

class SupertrendRule(_BaseRule):
    """Score based on Supertrend direction indicator.

    Direction = +1 (bullish) → +20.
    Direction = -1 (bearish) → -20.
    Missing / 0              →  0.
    """

    name = "supertrend"
    max_score = 20

    def evaluate(
        self,
        indicators: IndicatorRecord,
        prev_indicators: Optional[IndicatorRecord] = None,
        current_price: Optional[Decimal] = None,
    ) -> RuleResult:
        direction = indicators.supertrend_direction
        if direction is None:
            return RuleResult(score=0, reason="Supertrend: data unavailable", available=False)

        if direction == 1:
            return RuleResult(score=20, reason="Supertrend bullish (direction=+1)", available=True)
        if direction == -1:
            return RuleResult(score=-20, reason="Supertrend bearish (direction=-1)", available=True)
        return RuleResult(score=0, reason=f"Supertrend neutral (direction={direction})", available=True)


# ---------------------------------------------------------------------------
# RSI Momentum  (+/- 15)
# ---------------------------------------------------------------------------

class RsiMomentumRule(_BaseRule):
    """Score based on RSI 14 momentum zones.

    RSI > 60   → strong bull →  +15
    RSI 55-60  → mild bull   →   +7
    RSI 45-55  → neutral     →    0
    RSI 40-45  → mild bear   →   -7
    RSI < 40   → strong bear →  -15
    Missing    →               0
    """

    name = "rsi_momentum"
    max_score = 15

    def evaluate(
        self,
        indicators: IndicatorRecord,
        prev_indicators: Optional[IndicatorRecord] = None,
        current_price: Optional[Decimal] = None,
    ) -> RuleResult:
        if indicators.rsi14 is None:
            return RuleResult(score=0, reason="RSI: data unavailable", available=False)

        rsi = float(indicators.rsi14)

        if rsi > 60.0:
            return RuleResult(score=15, reason=f"RSI={rsi:.1f} > 60 (strong bull)", available=True)
        if rsi > 55.0:
            return RuleResult(score=7, reason=f"RSI={rsi:.1f} 55-60 (mild bull)", available=True)
        if rsi < 40.0:
            return RuleResult(score=-15, reason=f"RSI={rsi:.1f} < 40 (strong bear)", available=True)
        if rsi < 45.0:
            return RuleResult(score=-7, reason=f"RSI={rsi:.1f} 40-45 (mild bear)", available=True)
        return RuleResult(score=0, reason=f"RSI={rsi:.1f} neutral (45-55)", available=True)


# ---------------------------------------------------------------------------
# MACD Confirmation  (+/- 15)
# ---------------------------------------------------------------------------

class MacdConfirmationRule(_BaseRule):
    """Score based on MACD line vs signal line crossover.

    MACD > signal → +15 (bullish momentum).
    MACD < signal → -15 (bearish momentum).
    Equal or missing →  0.
    """

    name = "macd_confirmation"
    max_score = 15

    def evaluate(
        self,
        indicators: IndicatorRecord,
        prev_indicators: Optional[IndicatorRecord] = None,
        current_price: Optional[Decimal] = None,
    ) -> RuleResult:
        macd, signal = indicators.macd, indicators.macd_signal
        if macd is None or signal is None:
            return RuleResult(score=0, reason="MACD: data unavailable", available=False)

        if macd > signal:
            return RuleResult(
                score=15,
                reason=f"MACD {float(macd):.4f} > Signal {float(signal):.4f}",
                available=True,
            )
        if macd < signal:
            return RuleResult(
                score=-15,
                reason=f"MACD {float(macd):.4f} < Signal {float(signal):.4f}",
                available=True,
            )
        return RuleResult(score=0, reason="MACD == Signal (no edge)", available=True)


# ---------------------------------------------------------------------------
# OBV Confirmation  (+/- 15)
# ---------------------------------------------------------------------------

class ObvConfirmationRule(_BaseRule):
    """Score based on On-Balance Volume trend direction.

    Requires two consecutive IndicatorRecords to compare OBV.

    OBV rising  (current > prev) → +15.
    OBV falling (current < prev) → -15.
    OBV flat or no previous data →  0.
    """

    name = "obv_confirmation"
    max_score = 15

    def evaluate(
        self,
        indicators: IndicatorRecord,
        prev_indicators: Optional[IndicatorRecord] = None,
        current_price: Optional[Decimal] = None,
    ) -> RuleResult:
        if indicators.obv is None:
            return RuleResult(score=0, reason="OBV: data unavailable", available=False)
        if prev_indicators is None or prev_indicators.obv is None:
            return RuleResult(
                score=0,
                reason="OBV: previous record unavailable (cannot assess direction)",
                available=False,
            )

        curr_obv = float(indicators.obv)
        prev_obv = float(prev_indicators.obv)

        if curr_obv > prev_obv:
            return RuleResult(
                score=15,
                reason=f"OBV rising: {prev_obv:.0f} → {curr_obv:.0f}",
                available=True,
            )
        if curr_obv < prev_obv:
            return RuleResult(
                score=-15,
                reason=f"OBV falling: {prev_obv:.0f} → {curr_obv:.0f}",
                available=True,
            )
        return RuleResult(score=0, reason=f"OBV flat at {curr_obv:.0f}", available=True)


# ---------------------------------------------------------------------------
# Breakout Confirmation  (+/- 15)
# ---------------------------------------------------------------------------

class BreakoutConfirmationRule(_BaseRule):
    """Score based on Bollinger Band breakout / breakdown.

    Price > BB upper → +15 (bullish breakout).
    Price < BB lower → -15 (bearish breakdown).
    Price inside     →  0  (consolidation).
    Missing price or bands → 0.
    """

    name = "breakout_confirmation"
    max_score = 15

    def evaluate(
        self,
        indicators: IndicatorRecord,
        prev_indicators: Optional[IndicatorRecord] = None,
        current_price: Optional[Decimal] = None,
    ) -> RuleResult:
        upper, lower = indicators.bb_upper, indicators.bb_lower
        price = current_price

        if upper is None or lower is None:
            return RuleResult(score=0, reason="Bollinger Bands: data unavailable", available=False)
        if price is None:
            return RuleResult(score=0, reason="Breakout: current price unavailable", available=False)

        if price > upper:
            return RuleResult(
                score=15,
                reason=f"Breakout: price {float(price):.2f} > BB_upper {float(upper):.2f}",
                available=True,
            )
        if price < lower:
            return RuleResult(
                score=-15,
                reason=f"Breakdown: price {float(price):.2f} < BB_lower {float(lower):.2f}",
                available=True,
            )
        return RuleResult(
            score=0,
            reason=f"Price inside Bollinger Bands [{float(lower):.2f}, {float(upper):.2f}]",
            available=True,
        )

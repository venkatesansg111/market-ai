"""Confluence Engine — pure, stateless multi-timeframe scoring service.

Responsibilities:
    - Accept pre-aligned IndicatorRecord instances for each timeframe.
    - Evaluate the specified confluence rules per timeframe.
    - Compute an aggregate score and a 0–100 confidence value.
    - Derive a SignalType from the confidence.
    - Return an immutable ConfluenceResult.

No database access.  No side-effects.  Safe for concurrent use.

Designed so the future scanner engine can reuse this service by simply
providing aligned indicator records fetched from any source.

Scoring model
-------------
- Each rule contributes a signed integer score:
    + positive → bullish evidence
    - negative → bearish evidence
    0 → neutral or data unavailable

- Aggregate score is the sum across all (timeframe, rule) pairs.
- Score is unbounded in theory but designed to stay within [-100, +100]
  when the default rule set is used.

- Confidence:  ``clamp(50 + score // 2, 0, 100)``
    score = +100 → confidence = 100  (fully bullish)
    score =    0 → confidence =  50  (neutral)
    score = -100 → confidence =   0  (fully bearish)

- Signal classification from confidence:
    ≥ 70 → STRONG_BUY
    55–69 → BUY
    46–54 → NO_TRADE
    31–45 → SELL
    ≤ 30 → STRONG_SELL
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from confluence.confluence_models import ConfluenceComponent, ConfluenceResult
from confluence.confluence_registry import get_rule, list_rules
from indicators.indicator_models import IndicatorRecord
from signals.signal_models import SignalType


class ConfluenceEngineService:
    """Evaluate multi-timeframe confluence and produce a :class:`ConfluenceResult`.

    Instantiate once and reuse — the engine is stateless after ``__init__``.

    Example::

        engine = ConfluenceEngineService()
        result = engine.evaluate(
            strategy_name="trend_confluence",
            instrument="NIFTY 50",
            signal_time=datetime(2024, 1, 15, 10, 25),
            trend_tf="1day",
            setup_tf="15min",
            entry_tf="5min",
            aligned_records={
                "1day":  daily_record,    # IndicatorRecord or None
                "15min": min15_record,
                "5min":  min5_record,
            },
            rule_config={
                "1day":  ["ema_alignment"],
                "15min": ["adx_strength"],
                "5min":  ["vwap_confirmation"],
            },
            current_price=Decimal("19750.00"),
        )
    """

    def __init__(self) -> None:
        # Pre-instantiate all registered rules for performance.
        self._rules: dict[str, object] = {
            name: get_rule(name)() for name in list_rules()
        }

    def evaluate(
        self,
        strategy_name: str,
        instrument: str,
        signal_time: datetime,
        trend_tf: str,
        setup_tf: str,
        entry_tf: str,
        aligned_records: dict[str, Optional[IndicatorRecord]],
        rule_config: dict[str, list[str]],
        current_price: Optional[Decimal] = None,
        prev_records: Optional[dict[str, Optional[IndicatorRecord]]] = None,
    ) -> ConfluenceResult:
        """Evaluate confluence and return an immutable :class:`ConfluenceResult`.

        Args:
            strategy_name:    Strategy identifier for the result.
            instrument:       Trading instrument.
            signal_time:      Candle time of the entry bar.
            trend_tf:         Trend timeframe label (e.g. ``"1day"``).
            setup_tf:         Setup timeframe label (e.g. ``"15min"``).
            entry_tf:         Entry timeframe label (e.g. ``"5min"``).
            aligned_records:  Timeframe → aligned IndicatorRecord (``None`` if
                              no data available for that timeframe).
            rule_config:      Timeframe → list of rule names to evaluate.
                              Rules not listed are not evaluated for that TF.
            current_price:    Current market price, required by price-relative
                              rules (VWAP, Breakout). Pass ``None`` to skip.
            prev_records:     Timeframe → previous IndicatorRecord, required
                              by history-dependent rules (OBV). Optional.

        Returns:
            :class:`ConfluenceResult` with signal type, confidence, score, and
            per-timeframe components.
        """
        prev_map = prev_records or {}
        components: list[ConfluenceComponent] = []
        total_score = 0

        for tf, rule_names in rule_config.items():
            current_rec = aligned_records.get(tf)
            prev_rec = prev_map.get(tf)
            tf_score = 0
            tf_reasons: list[str] = []

            for rule_name in rule_names:
                rule = self._rules.get(rule_name)
                if rule is None:
                    tf_reasons.append(f"{rule_name}: rule not found")
                    continue

                if current_rec is None:
                    tf_reasons.append(f"{rule_name}: no indicator data for {tf}")
                    continue

                result = rule.evaluate(current_rec, prev_rec, current_price)
                tf_score += result.score
                if result.reason:
                    tf_reasons.append(result.reason)

            components.append(
                ConfluenceComponent(
                    timeframe=tf,
                    score=tf_score,
                    bullish=tf_score > 0,
                    bearish=tf_score < 0,
                    reason="; ".join(tf_reasons),
                )
            )
            total_score += tf_score

        confidence = max(0, min(100, 50 + total_score // 2))
        signal_type = self._classify_signal(confidence)
        reason = "; ".join(c.reason for c in components if c.reason)

        return ConfluenceResult(
            instrument=instrument,
            signal_time=signal_time,
            signal_type=signal_type,
            confidence=confidence,
            score=total_score,
            trend_timeframe=trend_tf,
            setup_timeframe=setup_tf,
            entry_timeframe=entry_tf,
            strategy_name=strategy_name,
            reason=reason,
            components=tuple(components),
        )

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_signal(confidence: int) -> SignalType:
        """Map 0–100 confidence to a :class:`SignalType`.

        Boundaries:
            ≥ 70  → STRONG_BUY
            55–69 → BUY
            46–54 → NO_TRADE
            31–45 → SELL
            ≤ 30  → STRONG_SELL
        """
        if confidence >= 70:
            return SignalType.STRONG_BUY
        if confidence >= 55:
            return SignalType.BUY
        if confidence <= 30:
            return SignalType.STRONG_SELL
        if confidence <= 45:
            return SignalType.SELL
        return SignalType.NO_TRADE

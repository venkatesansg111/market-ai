"""RegimeDetector — classify market regime from indicator data."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from meta.meta_models import MarketRegime, RegimeType

# ADX thresholds
_ADX_STRONG_TREND = 25.0
_ADX_WEAK_THRESHOLD = 20.0

# ATR ratio thresholds (atr / mean_atr)
_ATR_HIGH_VOL = 1.5
_ATR_LOW_VOL = 0.5

# Confidence floor / cap
_CONF_FLOOR = 0.35
_CONF_CAP = 0.95


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Convert an ORM Decimal or None to float safely."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _extract_features(row: Any) -> dict[str, Any]:
    """Extract normalised float features from a MarketIndicator-like row."""
    adx = _safe_float(getattr(row, "adx_14", None))
    atr = _safe_float(getattr(row, "atr_14", None))
    st_dir = _safe_int(getattr(row, "supertrend_direction", None))
    ema20 = _safe_float(getattr(row, "ema20", None))
    ema50 = _safe_float(getattr(row, "ema50", None))
    ema200 = _safe_float(getattr(row, "ema200", None))
    bb_width = _safe_float(getattr(row, "bb_width", None))

    ema_bullish = ema20 > 0 and ema50 > 0 and ema200 > 0 and ema20 > ema50 > ema200
    ema_bearish = ema20 > 0 and ema50 > 0 and ema200 > 0 and ema20 < ema50 < ema200

    return {
        "adx": adx,
        "atr": atr,
        "supertrend_direction": st_dir,
        "ema_bullish_aligned": ema_bullish,
        "ema_bearish_aligned": ema_bearish,
        "bb_width": bb_width,
    }


def _classify(features: dict[str, Any], mean_atr: float) -> tuple[RegimeType, float]:
    """Pure function: compute (RegimeType, confidence) from extracted features."""
    adx = features["adx"]
    atr = features["atr"]
    st_dir = features["supertrend_direction"]
    ema_bullish: bool = features["ema_bullish_aligned"]
    ema_bearish: bool = features["ema_bearish_aligned"]
    bb_width = features["bb_width"]

    atr_ratio = atr / mean_atr if mean_atr > 0 else 1.0

    # ── Volatility takes priority when ADX is not strongly trending ──────
    if atr_ratio > _ATR_HIGH_VOL and adx <= 35.0:
        excess = atr_ratio - _ATR_HIGH_VOL
        conf = min(_CONF_FLOOR + excess * 0.25, _CONF_CAP)
        return RegimeType.HIGH_VOLATILITY, round(conf, 4)

    if atr_ratio < _ATR_LOW_VOL and adx <= _ADX_STRONG_TREND:
        deficit = _ATR_LOW_VOL - atr_ratio
        conf = min(_CONF_FLOOR + deficit * 0.50, _CONF_CAP)
        return RegimeType.LOW_VOLATILITY, round(conf, 4)

    # ── Trending regime ───────────────────────────────────────────────────
    if adx > _ADX_STRONG_TREND:
        base_conf = min(_CONF_FLOOR + (adx - _ADX_STRONG_TREND) / 50.0, _CONF_CAP)
        # Incorporate BB width: narrow BB lowers confidence in trend
        if bb_width > 0:
            base_conf = min(base_conf * (1.0 + bb_width * 2.0), _CONF_CAP)

        bullish_votes = int(st_dir == 1) + int(ema_bullish)
        bearish_votes = int(st_dir == -1) + int(ema_bearish)

        if bullish_votes > bearish_votes:
            return RegimeType.TRENDING_UP, round(base_conf, 4)
        if bearish_votes > bullish_votes:
            return RegimeType.TRENDING_DOWN, round(base_conf, 4)
        # Tied — use price EMAs as tiebreaker
        if ema_bullish:
            return RegimeType.TRENDING_UP, round(base_conf * 0.85, 4)
        if ema_bearish:
            return RegimeType.TRENDING_DOWN, round(base_conf * 0.85, 4)
        return RegimeType.TRENDING_UP, round(base_conf * 0.70, 4)

    # ── Ranging regime (default) ─────────────────────────────────────────
    range_conf = min(_CONF_FLOOR + (_ADX_STRONG_TREND - adx) / 50.0, _CONF_CAP)
    return RegimeType.RANGING, round(range_conf, 4)


class RegimeDetector:
    """Classify market regime from indicator row(s).

    Real-time single-row usage::

        detector = RegimeDetector()
        regime = detector.detect_from_row(row, mean_atr=some_value)

    Batch usage (mean ATR computed internally)::

        regimes = detector.detect_from_series(rows)
    """

    # ── Public API ────────────────────────────────────────────────────────

    def detect_from_row(
        self,
        row: Any,
        mean_atr: float = 0.0,
        timestamp: Optional[datetime] = None,
    ) -> MarketRegime:
        """Detect regime for a single indicator row.

        Args:
            row:       MarketIndicator ORM object or any object with indicator attrs.
            mean_atr:  Historical mean ATR for ratio computation.
                       Pass 0.0 to skip ATR-based volatility classification.
            timestamp: Explicit timestamp; defaults to ``row.candle_time`` if present.
        """
        ts = timestamp or getattr(row, "candle_time", datetime.utcnow())
        features = _extract_features(row)
        regime_type, confidence = _classify(features, mean_atr)

        return MarketRegime(
            regime_type=regime_type,
            confidence=confidence,
            timestamp=ts,
            supporting_features={
                "adx": features["adx"],
                "atr": features["atr"],
                "atr_ratio": round(features["atr"] / mean_atr, 4) if mean_atr > 0 else None,
                "supertrend_direction": features["supertrend_direction"],
                "ema_bullish_aligned": features["ema_bullish_aligned"],
                "ema_bearish_aligned": features["ema_bearish_aligned"],
                "bb_width": features["bb_width"],
            },
        )

    def detect_from_series(self, rows: list[Any]) -> list[MarketRegime]:
        """Detect regime for every row in a chronological series.

        The global mean ATR across all rows is used as the normalisation reference.
        Rows with missing ATR are skipped.

        Returns:
            List of :class:`MarketRegime`, one per input row (excluding skipped rows).
        """
        if not rows:
            return []

        atr_values = [_safe_float(getattr(r, "atr_14", None)) for r in rows]
        valid_atr = [v for v in atr_values if v > 0]
        mean_atr = sum(valid_atr) / len(valid_atr) if valid_atr else 0.0

        results: list[MarketRegime] = []
        for row in rows:
            atr = _safe_float(getattr(row, "atr_14", None))
            if atr == 0.0 and getattr(row, "atr_14", None) is None:
                continue
            results.append(self.detect_from_row(row, mean_atr))

        return results

    def detect_latest(self, rows: list[Any]) -> Optional[MarketRegime]:
        """Return the regime for the most recent row in *rows*.

        Returns ``None`` if *rows* is empty.
        """
        if not rows:
            return None
        regimes = self.detect_from_series(rows)
        return regimes[-1] if regimes else None

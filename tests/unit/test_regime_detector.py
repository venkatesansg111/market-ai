"""Unit tests for RegimeDetector."""
from datetime import datetime
from types import SimpleNamespace

import pytest

from meta.meta_models import MarketRegime, RegimeType
from meta.regime_detector import RegimeDetector, _classify, _extract_features


# ──────────────────────────────────────────────────────────────────────
# Helper factory
# ──────────────────────────────────────────────────────────────────────

def _row(
    adx=20.0,
    atr=100.0,
    supertrend_direction=0,
    ema20=100.0,
    ema50=100.0,
    ema200=100.0,
    bb_width=0.02,
    candle_time=None,
):
    return SimpleNamespace(
        adx_14=adx,
        atr_14=atr,
        supertrend_direction=supertrend_direction,
        ema20=ema20,
        ema50=ema50,
        ema200=ema200,
        bb_width=bb_width,
        candle_time=candle_time or datetime(2024, 1, 15),
    )


# ──────────────────────────────────────────────────────────────────────
# _classify — pure function
# ──────────────────────────────────────────────────────────────────────

class TestClassify:
    def _feat(self, adx, atr, st=0, bull=False, bear=False, bb=0.02):
        return {
            "adx": adx,
            "atr": atr,
            "supertrend_direction": st,
            "ema_bullish_aligned": bull,
            "ema_bearish_aligned": bear,
            "bb_width": bb,
        }

    def test_high_volatility_high_atr_ratio(self):
        regime, conf = _classify(self._feat(adx=20, atr=200), mean_atr=100)
        assert regime == RegimeType.HIGH_VOLATILITY
        assert conf > 0.35

    def test_low_volatility_low_atr_ratio(self):
        regime, conf = _classify(self._feat(adx=15, atr=30), mean_atr=100)
        assert regime == RegimeType.LOW_VOLATILITY
        assert conf > 0.35

    def test_trending_up_supertrend_bullish(self):
        regime, conf = _classify(self._feat(adx=30, atr=100, st=1), mean_atr=100)
        assert regime == RegimeType.TRENDING_UP

    def test_trending_down_supertrend_bearish(self):
        regime, conf = _classify(self._feat(adx=30, atr=100, st=-1), mean_atr=100)
        assert regime == RegimeType.TRENDING_DOWN

    def test_trending_up_ema_bullish(self):
        regime, conf = _classify(self._feat(adx=30, atr=100, bull=True), mean_atr=100)
        assert regime == RegimeType.TRENDING_UP

    def test_trending_down_ema_bearish(self):
        regime, conf = _classify(self._feat(adx=30, atr=100, bear=True), mean_atr=100)
        assert regime == RegimeType.TRENDING_DOWN

    def test_ranging_low_adx(self):
        regime, conf = _classify(self._feat(adx=15, atr=100), mean_atr=100)
        assert regime == RegimeType.RANGING

    def test_confidence_capped_at_0_95(self):
        _, conf = _classify(self._feat(adx=80, atr=100, st=1), mean_atr=100)
        assert conf <= 0.95

    def test_confidence_floored_at_0_35(self):
        _, conf = _classify(self._feat(adx=0, atr=0), mean_atr=0)
        assert conf >= 0.35

    def test_zero_mean_atr_skips_vol_classification(self):
        # With mean_atr=0, atr_ratio = 1.0 (neutral), should not go to high/low vol
        regime, _ = _classify(self._feat(adx=15, atr=100), mean_atr=0)
        assert regime == RegimeType.RANGING

    def test_high_volatility_does_not_override_strong_trend(self):
        # Very high ATR but also very high ADX (>35) — high vol override suppressed
        regime, _ = _classify(self._feat(adx=40, atr=300), mean_atr=100)
        # adx > 35 prevents high_vol override, should be trending
        assert regime in (RegimeType.TRENDING_UP, RegimeType.TRENDING_DOWN)

    def test_deterministic_same_input_same_output(self):
        feat = self._feat(adx=30, atr=100, st=1)
        r1, c1 = _classify(feat, mean_atr=80)
        r2, c2 = _classify(feat, mean_atr=80)
        assert r1 == r2
        assert c1 == c2


# ──────────────────────────────────────────────────────────────────────
# _extract_features
# ──────────────────────────────────────────────────────────────────────

class TestExtractFeatures:
    def test_none_fields_become_zero(self):
        row = SimpleNamespace(
            adx_14=None, atr_14=None, supertrend_direction=None,
            ema20=None, ema50=None, ema200=None, bb_width=None,
        )
        feat = _extract_features(row)
        assert feat["adx"] == 0.0
        assert feat["atr"] == 0.0
        assert feat["supertrend_direction"] == 0

    def test_ema_bullish_aligned_detected(self):
        row = _row(ema20=120, ema50=100, ema200=80)
        feat = _extract_features(row)
        assert feat["ema_bullish_aligned"] is True
        assert feat["ema_bearish_aligned"] is False

    def test_ema_bearish_aligned_detected(self):
        row = _row(ema20=80, ema50=100, ema200=120)
        feat = _extract_features(row)
        assert feat["ema_bearish_aligned"] is True
        assert feat["ema_bullish_aligned"] is False

    def test_ema_not_aligned_flat(self):
        row = _row(ema20=100, ema50=100, ema200=100)
        feat = _extract_features(row)
        assert feat["ema_bullish_aligned"] is False
        assert feat["ema_bearish_aligned"] is False


# ──────────────────────────────────────────────────────────────────────
# RegimeDetector.detect_from_row
# ──────────────────────────────────────────────────────────────────────

class TestDetectFromRow:
    def setup_method(self):
        self.detector = RegimeDetector()

    def test_returns_market_regime(self):
        row = _row(adx=30, atr=100, supertrend_direction=1, ema20=120, ema50=100, ema200=80)
        regime = self.detector.detect_from_row(row, mean_atr=100)
        assert isinstance(regime, MarketRegime)

    def test_timestamp_from_candle_time(self):
        ts = datetime(2024, 3, 15)
        row = _row(candle_time=ts)
        regime = self.detector.detect_from_row(row)
        assert regime.timestamp == ts

    def test_explicit_timestamp_overrides(self):
        override_ts = datetime(2024, 6, 1)
        row = _row()
        regime = self.detector.detect_from_row(row, timestamp=override_ts)
        assert regime.timestamp == override_ts

    def test_supporting_features_populated(self):
        row = _row(adx=30, atr=100)
        regime = self.detector.detect_from_row(row, mean_atr=100)
        assert "adx" in regime.supporting_features
        assert "atr" in regime.supporting_features

    def test_trending_up_detection(self):
        row = _row(adx=35, atr=100, supertrend_direction=1, ema20=130, ema50=110, ema200=90)
        regime = self.detector.detect_from_row(row, mean_atr=100)
        assert regime.regime_type == RegimeType.TRENDING_UP

    def test_ranging_detection(self):
        row = _row(adx=12, atr=100)
        regime = self.detector.detect_from_row(row, mean_atr=100)
        assert regime.regime_type == RegimeType.RANGING

    def test_high_volatility_detection(self):
        row = _row(adx=20, atr=200)
        regime = self.detector.detect_from_row(row, mean_atr=100)
        assert regime.regime_type == RegimeType.HIGH_VOLATILITY


# ──────────────────────────────────────────────────────────────────────
# RegimeDetector.detect_from_series
# ──────────────────────────────────────────────────────────────────────

class TestDetectFromSeries:
    def setup_method(self):
        self.detector = RegimeDetector()

    def test_empty_returns_empty(self):
        assert self.detector.detect_from_series([]) == []

    def test_returns_one_per_row(self):
        rows = [_row(adx=30, atr=100) for _ in range(5)]
        regimes = self.detector.detect_from_series(rows)
        assert len(regimes) == 5

    def test_mean_atr_computed_internally(self):
        rows = [_row(adx=20, atr=float(100 + i * 10)) for i in range(10)]
        regimes = self.detector.detect_from_series(rows)
        assert all(isinstance(r, MarketRegime) for r in regimes)

    def test_skips_rows_with_none_atr(self):
        rows = [
            _row(adx=20, atr=100),
            SimpleNamespace(adx_14=20, atr_14=None, supertrend_direction=0,
                            ema20=100, ema50=100, ema200=100, bb_width=0.02,
                            candle_time=datetime(2024, 1, 1)),
            _row(adx=20, atr=100),
        ]
        regimes = self.detector.detect_from_series(rows)
        assert len(regimes) == 2


# ──────────────────────────────────────────────────────────────────────
# RegimeDetector.detect_latest
# ──────────────────────────────────────────────────────────────────────

class TestDetectLatest:
    def setup_method(self):
        self.detector = RegimeDetector()

    def test_empty_returns_none(self):
        assert self.detector.detect_latest([]) is None

    def test_returns_last_rows_regime(self):
        rows = [
            _row(adx=12, atr=100),  # ranging
            _row(adx=35, atr=100, supertrend_direction=1, ema20=130, ema50=110, ema200=90),
        ]
        latest = self.detector.detect_latest(rows)
        assert latest is not None
        assert latest.regime_type == RegimeType.TRENDING_UP

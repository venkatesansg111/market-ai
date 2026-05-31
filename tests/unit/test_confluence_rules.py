from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from confluence.confluence_rules import (
    AdxStrengthRule,
    BreakoutConfirmationRule,
    EmaAlignmentRule,
    MacdConfirmationRule,
    ObvConfirmationRule,
    RsiMomentumRule,
    SupertrendRule,
    VWAPConfirmationRule,
)
from indicators.indicator_models import IndicatorRecord

_T = datetime(2024, 1, 15, 10, 0)


def _rec(**kwargs) -> IndicatorRecord:
    return IndicatorRecord(instrument="TEST", candle_time=_T, timeframe="5min", **kwargs)


def _d(v) -> Decimal:
    return Decimal(str(v))


class TestEmaAlignmentRule:
    def setup_method(self):
        self.rule = EmaAlignmentRule()

    def test_bullish_stack(self):
        r = self.rule.evaluate(_rec(ema20=_d(220), ema50=_d(200), ema200=_d(180)))
        assert r.score == 20
        assert r.available is True

    def test_bearish_stack(self):
        r = self.rule.evaluate(_rec(ema20=_d(180), ema50=_d(200), ema200=_d(220)))
        assert r.score == -20
        assert r.available is True

    def test_mixed_returns_zero(self):
        r = self.rule.evaluate(_rec(ema20=_d(210), ema50=_d(180), ema200=_d(200)))
        assert r.score == 0
        assert r.available is True

    def test_missing_ema_returns_unavailable(self):
        r = self.rule.evaluate(_rec(ema20=_d(200), ema50=_d(180)))
        assert r.score == 0
        assert r.available is False

    def test_name_is_correct(self):
        assert self.rule.name == "ema_alignment"

    def test_max_score(self):
        assert self.rule.max_score == 20

    def test_callable_interface(self):
        r = self.rule(_rec(ema20=_d(220), ema50=_d(200), ema200=_d(180)))
        assert r.score == 20


class TestAdxStrengthRule:
    def setup_method(self):
        self.rule = AdxStrengthRule()

    def test_strong_trend_scores_15(self):
        r = self.rule.evaluate(_rec(adx_14=_d(30)))
        assert r.score == 15
        assert r.available is True

    def test_weak_trend_scores_zero(self):
        r = self.rule.evaluate(_rec(adx_14=_d(20)))
        assert r.score == 0
        assert r.available is True

    def test_exactly_25_scores_zero(self):
        r = self.rule.evaluate(_rec(adx_14=_d(25)))
        assert r.score == 0

    def test_missing_adx_unavailable(self):
        r = self.rule.evaluate(_rec())
        assert r.score == 0
        assert r.available is False

    def test_name_and_max_score(self):
        assert self.rule.name == "adx_strength"
        assert self.rule.max_score == 15


class TestVWAPConfirmationRule:
    def setup_method(self):
        self.rule = VWAPConfirmationRule()

    def test_price_above_vwap(self):
        r = self.rule.evaluate(_rec(vwap=_d(19500)), current_price=_d(19750))
        assert r.score == 15
        assert r.available is True

    def test_price_below_vwap(self):
        r = self.rule.evaluate(_rec(vwap=_d(19500)), current_price=_d(19200))
        assert r.score == -15
        assert r.available is True

    def test_price_equals_vwap(self):
        r = self.rule.evaluate(_rec(vwap=_d(19500)), current_price=_d(19500))
        assert r.score == 0
        assert r.available is True

    def test_missing_vwap_unavailable(self):
        r = self.rule.evaluate(_rec(), current_price=_d(19500))
        assert r.score == 0
        assert r.available is False

    def test_missing_price_unavailable(self):
        r = self.rule.evaluate(_rec(vwap=_d(19500)))
        assert r.score == 0
        assert r.available is False

    def test_name_and_max_score(self):
        assert self.rule.name == "vwap_confirmation"
        assert self.rule.max_score == 15


class TestSupertrendRule:
    def setup_method(self):
        self.rule = SupertrendRule()

    def test_bullish_direction(self):
        r = self.rule.evaluate(_rec(supertrend_direction=1))
        assert r.score == 20
        assert r.available is True

    def test_bearish_direction(self):
        r = self.rule.evaluate(_rec(supertrend_direction=-1))
        assert r.score == -20
        assert r.available is True

    def test_zero_direction_neutral(self):
        r = self.rule.evaluate(_rec(supertrend_direction=0))
        assert r.score == 0
        assert r.available is True

    def test_missing_direction_unavailable(self):
        r = self.rule.evaluate(_rec())
        assert r.score == 0
        assert r.available is False

    def test_name_and_max_score(self):
        assert self.rule.name == "supertrend"
        assert self.rule.max_score == 20


class TestRsiMomentumRule:
    def setup_method(self):
        self.rule = RsiMomentumRule()

    def test_strong_bull_above_60(self):
        r = self.rule.evaluate(_rec(rsi14=_d(65)))
        assert r.score == 15

    def test_mild_bull_55_to_60(self):
        r = self.rule.evaluate(_rec(rsi14=_d(57)))
        assert r.score == 7

    def test_neutral_45_to_55(self):
        r = self.rule.evaluate(_rec(rsi14=_d(50)))
        assert r.score == 0

    def test_mild_bear_40_to_45(self):
        r = self.rule.evaluate(_rec(rsi14=_d(42)))
        assert r.score == -7

    def test_strong_bear_below_40(self):
        r = self.rule.evaluate(_rec(rsi14=_d(35)))
        assert r.score == -15

    def test_missing_rsi_unavailable(self):
        r = self.rule.evaluate(_rec())
        assert r.score == 0
        assert r.available is False

    def test_name_and_max_score(self):
        assert self.rule.name == "rsi_momentum"
        assert self.rule.max_score == 15


class TestMacdConfirmationRule:
    def setup_method(self):
        self.rule = MacdConfirmationRule()

    def test_macd_above_signal_bullish(self):
        r = self.rule.evaluate(_rec(macd=_d("0.05"), macd_signal=_d("0.02")))
        assert r.score == 15
        assert r.available is True

    def test_macd_below_signal_bearish(self):
        r = self.rule.evaluate(_rec(macd=_d("0.01"), macd_signal=_d("0.04")))
        assert r.score == -15
        assert r.available is True

    def test_macd_equals_signal_neutral(self):
        r = self.rule.evaluate(_rec(macd=_d("0.03"), macd_signal=_d("0.03")))
        assert r.score == 0
        assert r.available is True

    def test_missing_macd_unavailable(self):
        r = self.rule.evaluate(_rec(macd_signal=_d("0.03")))
        assert r.score == 0
        assert r.available is False

    def test_missing_signal_unavailable(self):
        r = self.rule.evaluate(_rec(macd=_d("0.03")))
        assert r.score == 0
        assert r.available is False

    def test_name_and_max_score(self):
        assert self.rule.name == "macd_confirmation"
        assert self.rule.max_score == 15


class TestObvConfirmationRule:
    def setup_method(self):
        self.rule = ObvConfirmationRule()

    def test_obv_rising(self):
        curr = _rec(obv=_d(1_200_000))
        prev = _rec(obv=_d(1_000_000))
        r = self.rule.evaluate(curr, prev_indicators=prev)
        assert r.score == 15
        assert r.available is True

    def test_obv_falling(self):
        curr = _rec(obv=_d(900_000))
        prev = _rec(obv=_d(1_000_000))
        r = self.rule.evaluate(curr, prev_indicators=prev)
        assert r.score == -15
        assert r.available is True

    def test_obv_flat(self):
        curr = _rec(obv=_d(1_000_000))
        prev = _rec(obv=_d(1_000_000))
        r = self.rule.evaluate(curr, prev_indicators=prev)
        assert r.score == 0
        assert r.available is True

    def test_no_prev_indicators_unavailable(self):
        r = self.rule.evaluate(_rec(obv=_d(1_000_000)))
        assert r.score == 0
        assert r.available is False

    def test_missing_current_obv_unavailable(self):
        r = self.rule.evaluate(_rec(), prev_indicators=_rec(obv=_d(1_000_000)))
        assert r.score == 0
        assert r.available is False

    def test_name_and_max_score(self):
        assert self.rule.name == "obv_confirmation"
        assert self.rule.max_score == 15


class TestBreakoutConfirmationRule:
    def setup_method(self):
        self.rule = BreakoutConfirmationRule()

    def test_price_above_bb_upper_bullish(self):
        r = self.rule.evaluate(
            _rec(bb_upper=_d(19800), bb_lower=_d(19200)),
            current_price=_d(19900),
        )
        assert r.score == 15
        assert r.available is True

    def test_price_below_bb_lower_bearish(self):
        r = self.rule.evaluate(
            _rec(bb_upper=_d(19800), bb_lower=_d(19200)),
            current_price=_d(19100),
        )
        assert r.score == -15
        assert r.available is True

    def test_price_inside_bands_neutral(self):
        r = self.rule.evaluate(
            _rec(bb_upper=_d(19800), bb_lower=_d(19200)),
            current_price=_d(19500),
        )
        assert r.score == 0
        assert r.available is True

    def test_missing_bb_unavailable(self):
        r = self.rule.evaluate(_rec(), current_price=_d(19500))
        assert r.score == 0
        assert r.available is False

    def test_missing_price_unavailable(self):
        r = self.rule.evaluate(_rec(bb_upper=_d(19800), bb_lower=_d(19200)))
        assert r.score == 0
        assert r.available is False

    def test_name_and_max_score(self):
        assert self.rule.name == "breakout_confirmation"
        assert self.rule.max_score == 15

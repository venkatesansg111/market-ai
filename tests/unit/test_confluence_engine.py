from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from confluence.confluence_engine import ConfluenceEngineService
from indicators.indicator_models import IndicatorRecord
from signals.signal_models import SignalType

_T = datetime(2024, 1, 15, 10, 25)


def _rec(tf: str = "5min", **kwargs) -> IndicatorRecord:
    return IndicatorRecord(instrument="NIFTY 50", candle_time=_T, timeframe=tf, **kwargs)


def _d(v) -> Decimal:
    return Decimal(str(v))


# Full bullish record — every indicator maximally bullish
def _bull_rec(tf: str = "5min") -> IndicatorRecord:
    return _rec(
        tf=tf,
        ema20=_d(220), ema50=_d(200), ema200=_d(180),
        adx_14=_d(35),
        vwap=_d(19500),
        supertrend_direction=1,
        rsi14=_d(65),
        macd=_d("0.05"), macd_signal=_d("0.01"),
        obv=_d(1_500_000),
        bb_upper=_d(19800), bb_lower=_d(19200),
    )


# Full bearish record
def _bear_rec(tf: str = "5min") -> IndicatorRecord:
    return _rec(
        tf=tf,
        ema20=_d(180), ema50=_d(200), ema200=_d(220),
        adx_14=_d(35),
        vwap=_d(19500),
        supertrend_direction=-1,
        rsi14=_d(35),
        macd=_d("0.01"), macd_signal=_d("0.05"),
        obv=_d(500_000),
        bb_upper=_d(19800), bb_lower=_d(19200),
    )


class TestConfluenceEngineEvaluate:
    def setup_method(self):
        self.engine = ConfluenceEngineService()

    def _basic_rule_config(self, tf: str) -> dict[str, list[str]]:
        return {tf: ["ema_alignment", "adx_strength", "rsi_momentum"]}

    def test_full_bullish_produces_strong_buy(self):
        result = self.engine.evaluate(
            strategy_name="test",
            instrument="NIFTY 50",
            signal_time=_T,
            trend_tf="1day",
            setup_tf="15min",
            entry_tf="5min",
            aligned_records={"5min": _bull_rec()},
            rule_config={"5min": ["ema_alignment", "adx_strength", "rsi_momentum"]},
            current_price=_d(19750),
        )
        assert result.signal_type == SignalType.STRONG_BUY
        assert result.confidence >= 70

    def test_full_bearish_produces_strong_sell(self):
        # Use rules that produce a net negative score well below -40:
        # ema_alignment(-20) + supertrend(-20) + rsi_momentum(-15) + macd_confirmation(-15) = -70
        # → confidence = max(0, 50 + (-70)//2) = max(0, 15) = 15 → STRONG_SELL
        result = self.engine.evaluate(
            strategy_name="test",
            instrument="NIFTY 50",
            signal_time=_T,
            trend_tf="1day",
            setup_tf="15min",
            entry_tf="5min",
            aligned_records={"5min": _bear_rec()},
            rule_config={"5min": ["ema_alignment", "supertrend", "rsi_momentum", "macd_confirmation"]},
            current_price=_d(19100),
        )
        assert result.signal_type == SignalType.STRONG_SELL
        assert result.confidence <= 30

    def test_mixed_signals_produce_no_trade(self):
        mixed = _rec(
            ema20=_d(200), ema50=_d(200), ema200=_d(200),  # neutral EMA
            adx_14=_d(15),  # weak ADX
            rsi14=_d(50),   # neutral RSI
        )
        result = self.engine.evaluate(
            strategy_name="test",
            instrument="NIFTY 50",
            signal_time=_T,
            trend_tf="1day",
            setup_tf="15min",
            entry_tf="5min",
            aligned_records={"5min": mixed},
            rule_config={"5min": ["ema_alignment", "adx_strength", "rsi_momentum"]},
        )
        assert result.signal_type == SignalType.NO_TRADE

    def test_missing_record_for_tf_skips_gracefully(self):
        result = self.engine.evaluate(
            strategy_name="test",
            instrument="NIFTY 50",
            signal_time=_T,
            trend_tf="1day",
            setup_tf="15min",
            entry_tf="5min",
            aligned_records={"5min": None},
            rule_config={"5min": ["ema_alignment"]},
        )
        assert result.confidence == 50
        assert result.signal_type == SignalType.NO_TRADE

    def test_confidence_always_in_range(self):
        for rec in [_bull_rec(), _bear_rec()]:
            result = self.engine.evaluate(
                strategy_name="test",
                instrument="NIFTY 50",
                signal_time=_T,
                trend_tf="1day",
                setup_tf="15min",
                entry_tf="5min",
                aligned_records={"5min": rec, "1day": rec},
                rule_config={
                    "5min": ["ema_alignment", "adx_strength", "rsi_momentum",
                             "macd_confirmation", "supertrend"],
                    "1day": ["ema_alignment"],
                },
                current_price=_d(19750),
            )
            assert 0 <= result.confidence <= 100

    def test_components_count_matches_rule_config_keys(self):
        result = self.engine.evaluate(
            strategy_name="test",
            instrument="NIFTY 50",
            signal_time=_T,
            trend_tf="1day",
            setup_tf="15min",
            entry_tf="5min",
            aligned_records={"1day": _bull_rec("1day"), "15min": _bull_rec("15min")},
            rule_config={"1day": ["ema_alignment"], "15min": ["adx_strength", "rsi_momentum"]},
        )
        assert len(result.components) == 2

    def test_obv_rule_uses_prev_records(self):
        curr = _rec(obv=_d(1_200_000))
        prev = _rec(obv=_d(1_000_000))
        result = self.engine.evaluate(
            strategy_name="test",
            instrument="NIFTY 50",
            signal_time=_T,
            trend_tf="1day",
            setup_tf="15min",
            entry_tf="5min",
            aligned_records={"5min": curr},
            rule_config={"5min": ["obv_confirmation"]},
            prev_records={"5min": prev},
        )
        component = result.components[0]
        assert component.score == 15
        assert component.bullish is True

    def test_result_fields_populated(self):
        result = self.engine.evaluate(
            strategy_name="my_strategy",
            instrument="NIFTY 50",
            signal_time=_T,
            trend_tf="1day",
            setup_tf="15min",
            entry_tf="5min",
            aligned_records={"5min": _bull_rec()},
            rule_config={"5min": ["ema_alignment"]},
        )
        assert result.instrument == "NIFTY 50"
        assert result.strategy_name == "my_strategy"
        assert result.signal_time == _T
        assert result.trend_timeframe == "1day"
        assert result.setup_timeframe == "15min"
        assert result.entry_timeframe == "5min"

    def test_vwap_rule_uses_current_price(self):
        rec = _rec(vwap=_d(19500))
        result_above = self.engine.evaluate(
            strategy_name="test",
            instrument="NIFTY 50",
            signal_time=_T,
            trend_tf="1day",
            setup_tf="15min",
            entry_tf="5min",
            aligned_records={"5min": rec},
            rule_config={"5min": ["vwap_confirmation"]},
            current_price=_d(19750),
        )
        result_below = self.engine.evaluate(
            strategy_name="test",
            instrument="NIFTY 50",
            signal_time=_T,
            trend_tf="1day",
            setup_tf="15min",
            entry_tf="5min",
            aligned_records={"5min": rec},
            rule_config={"5min": ["vwap_confirmation"]},
            current_price=_d(19200),
        )
        assert result_above.score > 0
        assert result_below.score < 0


class TestSignalClassification:
    """Verify confidence → signal type mapping boundaries."""

    def setup_method(self):
        self.engine = ConfluenceEngineService()

    def _result_for_score(self, score: int):
        confidence = max(0, min(100, 50 + score // 2))
        return ConfluenceEngineService._classify_signal(confidence)

    def test_confidence_70_is_strong_buy(self):
        assert ConfluenceEngineService._classify_signal(70) == SignalType.STRONG_BUY

    def test_confidence_100_is_strong_buy(self):
        assert ConfluenceEngineService._classify_signal(100) == SignalType.STRONG_BUY

    def test_confidence_55_is_buy(self):
        assert ConfluenceEngineService._classify_signal(55) == SignalType.BUY

    def test_confidence_69_is_buy(self):
        assert ConfluenceEngineService._classify_signal(69) == SignalType.BUY

    def test_confidence_50_is_no_trade(self):
        assert ConfluenceEngineService._classify_signal(50) == SignalType.NO_TRADE

    def test_confidence_46_is_no_trade(self):
        assert ConfluenceEngineService._classify_signal(46) == SignalType.NO_TRADE

    def test_confidence_45_is_sell(self):
        assert ConfluenceEngineService._classify_signal(45) == SignalType.SELL

    def test_confidence_31_is_sell(self):
        assert ConfluenceEngineService._classify_signal(31) == SignalType.SELL

    def test_confidence_30_is_strong_sell(self):
        assert ConfluenceEngineService._classify_signal(30) == SignalType.STRONG_SELL

    def test_confidence_0_is_strong_sell(self):
        assert ConfluenceEngineService._classify_signal(0) == SignalType.STRONG_SELL

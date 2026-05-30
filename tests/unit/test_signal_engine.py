from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from indicators.indicator_models import IndicatorRecord
from signals.signal_engine import SignalEngineService
from signals.signal_models import SignalType


def make_rec(**overrides) -> IndicatorRecord:
    """Build a fully-populated IndicatorRecord; override any field as needed."""
    defaults = {
        "instrument": "NIFTY 50",
        "candle_time": datetime(2024, 1, 15, 15, 30),
        "timeframe": "1day",
        "ema20": Decimal("22600"),
        "ema50": Decimal("22400"),
        "ema200": Decimal("22000"),
        "rsi14": Decimal("65"),
        "vwap": Decimal("22500"),
        "macd": Decimal("50"),
        "macd_signal": Decimal("30"),
    }
    defaults.update(overrides)
    return IndicatorRecord(**defaults)


PRICE_ABOVE_VWAP = Decimal("22550")   # > 22500 VWAP
PRICE_BELOW_VWAP = Decimal("22450")   # < 22500 VWAP


class TestStrongBuySignal:
    def test_all_5_conditions_produces_strong_buy(self):
        engine = SignalEngineService()
        # EMA20>EMA50>EMA200, RSI=65>60, Price>VWAP, MACD>Signal
        result = engine.evaluate_signal(make_rec(), PRICE_ABOVE_VWAP)
        assert result.signal_type == SignalType.STRONG_BUY

    def test_strong_buy_confidence_above_80(self):
        engine = SignalEngineService()
        result = engine.evaluate_signal(make_rec(), PRICE_ABOVE_VWAP)
        assert result.confidence > 80

    def test_strong_buy_reason_is_non_empty(self):
        engine = SignalEngineService()
        result = engine.evaluate_signal(make_rec(), PRICE_ABOVE_VWAP)
        assert len(result.reason) > 0


class TestBuySignal:
    def test_buy_without_ema200(self):
        # Remove EMA200 → partial alignment only; RSI=58>55, price>VWAP
        engine = SignalEngineService()
        rec = make_rec(ema200=None, rsi14=Decimal("58"))
        result = engine.evaluate_signal(rec, PRICE_ABOVE_VWAP)
        assert result.signal_type == SignalType.BUY

    def test_buy_without_macd_data(self):
        engine = SignalEngineService()
        rec = make_rec(macd=None, macd_signal=None, rsi14=Decimal("57"))
        result = engine.evaluate_signal(rec, PRICE_ABOVE_VWAP)
        # Without MACD, STRONG_BUY is impossible but BUY (EMA20>50, RSI>55, Price>VWAP) works
        assert result.signal_type == SignalType.BUY


class TestStrongSellSignal:
    def test_all_5_bearish_conditions_produces_strong_sell(self):
        engine = SignalEngineService()
        rec = make_rec(
            ema20=Decimal("22000"),
            ema50=Decimal("22400"),
            ema200=Decimal("22600"),
            rsi14=Decimal("35"),
            macd=Decimal("-50"),
            macd_signal=Decimal("-30"),
        )
        result = engine.evaluate_signal(rec, PRICE_BELOW_VWAP)
        assert result.signal_type == SignalType.STRONG_SELL

    def test_strong_sell_confidence_above_80(self):
        engine = SignalEngineService()
        rec = make_rec(
            ema20=Decimal("22000"),
            ema50=Decimal("22400"),
            ema200=Decimal("22600"),
            rsi14=Decimal("35"),
            macd=Decimal("-50"),
            macd_signal=Decimal("-30"),
        )
        result = engine.evaluate_signal(rec, PRICE_BELOW_VWAP)
        assert result.confidence > 80


class TestSellSignal:
    def test_sell_three_bearish_conditions(self):
        engine = SignalEngineService()
        rec = make_rec(
            ema20=Decimal("22000"),
            ema50=Decimal("22400"),
            ema200=None,
            rsi14=Decimal("42"),
            macd=None,
            macd_signal=None,
        )
        result = engine.evaluate_signal(rec, PRICE_BELOW_VWAP)
        assert result.signal_type == SignalType.SELL


class TestNoTradeSignal:
    def test_neutral_rsi_produces_no_trade(self):
        engine = SignalEngineService()
        rec = make_rec(rsi14=Decimal("50"))
        result = engine.evaluate_signal(rec, PRICE_ABOVE_VWAP)
        assert result.signal_type == SignalType.NO_TRADE

    def test_rsi_45_boundary_is_no_trade(self):
        engine = SignalEngineService()
        rec = make_rec(rsi14=Decimal("45"))
        result = engine.evaluate_signal(rec, PRICE_ABOVE_VWAP)
        assert result.signal_type == SignalType.NO_TRADE

    def test_rsi_55_boundary_is_no_trade(self):
        engine = SignalEngineService()
        rec = make_rec(rsi14=Decimal("55"))
        result = engine.evaluate_signal(rec, PRICE_ABOVE_VWAP)
        assert result.signal_type == SignalType.NO_TRADE

    def test_conflicting_indicators_no_trade(self):
        # Bullish EMA but bearish MACD → conflict → NO_TRADE
        engine = SignalEngineService()
        rec = make_rec(
            rsi14=Decimal("58"),  # > 55 (bullish)
            macd=Decimal("-50"),   # bearish
            macd_signal=Decimal("-30"),
        )
        result = engine.evaluate_signal(rec, PRICE_ABOVE_VWAP)
        assert result.signal_type == SignalType.NO_TRADE

    def test_insufficient_data_produces_no_trade(self):
        engine = SignalEngineService()
        rec = make_rec(
            ema20=None,
            ema50=None,
            ema200=None,
            rsi14=None,
            vwap=None,
            macd=None,
            macd_signal=None,
        )
        result = engine.evaluate_signal(rec, Decimal("0"))
        assert result.signal_type == SignalType.NO_TRADE


class TestConfidenceScoring:
    def test_confidence_bounded_0_to_100(self):
        engine = SignalEngineService()
        for rsi_val, price in [
            ("65", PRICE_ABOVE_VWAP),
            ("35", PRICE_BELOW_VWAP),
            ("50", PRICE_ABOVE_VWAP),
        ]:
            result = engine.evaluate_signal(make_rec(rsi14=Decimal(rsi_val)), price)
            assert 0 <= result.confidence <= 100, (
                f"Confidence {result.confidence} out of bounds for RSI={rsi_val}"
            )

    def test_strong_buy_higher_confidence_than_buy(self):
        engine = SignalEngineService()
        # STRONG_BUY: full alignment
        strong = engine.evaluate_signal(make_rec(), PRICE_ABOVE_VWAP)
        # BUY: partial (no EMA200, weaker RSI)
        partial = engine.evaluate_signal(
            make_rec(ema200=None, rsi14=Decimal("57")), PRICE_ABOVE_VWAP
        )
        assert strong.confidence >= partial.confidence

    def test_components_sum_matches_total(self):
        engine = SignalEngineService()
        result = engine.evaluate_signal(make_rec(), PRICE_ABOVE_VWAP)
        c = result.components
        assert c.total == c.ema_score + c.rsi_score + c.vwap_score + c.macd_score

    def test_reason_contains_condition_descriptions(self):
        engine = SignalEngineService()
        result = engine.evaluate_signal(make_rec(), PRICE_ABOVE_VWAP)
        assert "EMA" in result.reason

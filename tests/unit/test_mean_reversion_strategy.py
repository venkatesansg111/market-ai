from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from indicators.indicator_models import IndicatorRecord
from signals.signal_models import SignalType
from strategies.mean_reversion import MeanReversionStrategy
from strategies.strategy_models import CandleSnapshot

_INSTRUMENT = "NIFTY 50"
_TIMEFRAME = "1day"
_NOW = datetime(2024, 5, 1)
_PRICE = Decimal("21500")


def make_candle(close: Decimal = _PRICE) -> CandleSnapshot:
    return CandleSnapshot(
        instrument=_INSTRUMENT,
        timeframe=_TIMEFRAME,
        candle_time=_NOW,
        open=close,
        high=close,
        low=close,
        close=close,
    )


def make_indicators(rsi14: Decimal | None = Decimal("50"), **overrides) -> IndicatorRecord:
    defaults: dict = {
        "instrument": _INSTRUMENT,
        "candle_time": _NOW,
        "timeframe": _TIMEFRAME,
        "ema20": Decimal("21600"),
        "ema50": Decimal("21400"),
        "ema200": Decimal("21000"),
        "rsi14": rsi14,
        "vwap": Decimal("21500"),
        "macd": Decimal("20"),
        "macd_signal": Decimal("10"),
    }
    defaults.update(overrides)
    return IndicatorRecord(**defaults)


class TestBuy:
    def test_rsi_below_30_is_buy(self):
        result = MeanReversionStrategy().generate_signal(
            make_candle(), make_indicators(rsi14=Decimal("25"))
        )
        assert result.signal_type == SignalType.BUY

    def test_buy_confidence_is_75(self):
        result = MeanReversionStrategy().generate_signal(
            make_candle(), make_indicators(rsi14=Decimal("25"))
        )
        assert result.confidence == 75

    def test_rsi_29_is_buy(self):
        result = MeanReversionStrategy().generate_signal(
            make_candle(), make_indicators(rsi14=Decimal("29"))
        )
        assert result.signal_type == SignalType.BUY

    def test_buy_reason_mentions_oversold(self):
        result = MeanReversionStrategy().generate_signal(
            make_candle(), make_indicators(rsi14=Decimal("25"))
        )
        assert "oversold" in result.reason.lower() or "30" in result.reason


class TestSell:
    def test_rsi_above_70_is_sell(self):
        result = MeanReversionStrategy().generate_signal(
            make_candle(), make_indicators(rsi14=Decimal("75"))
        )
        assert result.signal_type == SignalType.SELL

    def test_sell_confidence_is_25(self):
        result = MeanReversionStrategy().generate_signal(
            make_candle(), make_indicators(rsi14=Decimal("75"))
        )
        assert result.confidence == 25

    def test_rsi_71_is_sell(self):
        result = MeanReversionStrategy().generate_signal(
            make_candle(), make_indicators(rsi14=Decimal("71"))
        )
        assert result.signal_type == SignalType.SELL

    def test_sell_reason_mentions_overbought(self):
        result = MeanReversionStrategy().generate_signal(
            make_candle(), make_indicators(rsi14=Decimal("75"))
        )
        assert "overbought" in result.reason.lower() or "70" in result.reason


class TestNoTrade:
    def test_rsi_in_middle_range_is_no_trade(self):
        result = MeanReversionStrategy().generate_signal(
            make_candle(), make_indicators(rsi14=Decimal("50"))
        )
        assert result.signal_type == SignalType.NO_TRADE

    def test_rsi_exactly_30_is_not_buy(self):
        # strict: rsi_val < 30 required; rsi==30 is boundary → NO_TRADE
        result = MeanReversionStrategy().generate_signal(
            make_candle(), make_indicators(rsi14=Decimal("30"))
        )
        assert result.signal_type == SignalType.NO_TRADE

    def test_rsi_exactly_70_is_not_sell(self):
        # strict: rsi_val > 70 required; rsi==70 is boundary → NO_TRADE
        result = MeanReversionStrategy().generate_signal(
            make_candle(), make_indicators(rsi14=Decimal("70"))
        )
        assert result.signal_type == SignalType.NO_TRADE

    def test_rsi_31_is_no_trade(self):
        result = MeanReversionStrategy().generate_signal(
            make_candle(), make_indicators(rsi14=Decimal("31"))
        )
        assert result.signal_type == SignalType.NO_TRADE

    def test_rsi_69_is_no_trade(self):
        result = MeanReversionStrategy().generate_signal(
            make_candle(), make_indicators(rsi14=Decimal("69"))
        )
        assert result.signal_type == SignalType.NO_TRADE

    def test_missing_rsi_is_no_trade(self):
        result = MeanReversionStrategy().generate_signal(
            make_candle(), make_indicators(rsi14=None)
        )
        assert result.signal_type == SignalType.NO_TRADE

    def test_no_trade_confidence_is_50(self):
        result = MeanReversionStrategy().generate_signal(
            make_candle(), make_indicators(rsi14=Decimal("50"))
        )
        assert result.confidence == 50


class TestSignalMetadata:
    def test_strategy_name_is_mean_reversion(self):
        assert MeanReversionStrategy().strategy_name == "mean_reversion"

    def test_signal_strategy_name_in_output(self):
        result = MeanReversionStrategy().generate_signal(
            make_candle(), make_indicators(rsi14=Decimal("25"))
        )
        assert result.strategy_name == "mean_reversion"

    def test_signal_instrument_from_candle(self):
        result = MeanReversionStrategy().generate_signal(
            make_candle(), make_indicators(rsi14=Decimal("25"))
        )
        assert result.instrument == _INSTRUMENT

    def test_signal_time_matches_candle_time(self):
        result = MeanReversionStrategy().generate_signal(
            make_candle(), make_indicators(rsi14=Decimal("25"))
        )
        assert result.signal_time == _NOW

    def test_required_indicators_contains_rsi14(self):
        assert "rsi14" in MeanReversionStrategy().required_indicators

    def test_description_is_non_empty(self):
        assert len(MeanReversionStrategy().description) > 0

    def test_reason_mentions_rsi_value(self):
        result = MeanReversionStrategy().generate_signal(
            make_candle(), make_indicators(rsi14=Decimal("25"))
        )
        assert "RSI" in result.reason
        assert "25" in result.reason

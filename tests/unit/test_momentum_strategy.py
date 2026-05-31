from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from indicators.indicator_models import IndicatorRecord
from signals.signal_models import SignalType
from strategies.momentum import MomentumStrategy
from strategies.strategy_models import CandleSnapshot

_INSTRUMENT = "NIFTY 50"
_TIMEFRAME = "1day"
_NOW = datetime(2024, 4, 1)
_PRICE = Decimal("22000")


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


def make_indicators(**overrides) -> IndicatorRecord:
    defaults: dict = {
        "instrument": _INSTRUMENT,
        "candle_time": _NOW,
        "timeframe": _TIMEFRAME,
        "ema20": Decimal("22100"),
        "ema50": Decimal("21900"),
        "ema200": Decimal("21500"),
        "rsi14": Decimal("65"),       # > 60 = bullish
        "vwap": Decimal("22000"),
        "macd": Decimal("50"),        # > signal = bullish
        "macd_signal": Decimal("30"),
    }
    defaults.update(overrides)
    return IndicatorRecord(**defaults)


class TestBuy:
    def test_rsi_above_60_and_macd_bullish_is_buy(self):
        result = MomentumStrategy().generate_signal(make_candle(), make_indicators())
        assert result.signal_type == SignalType.BUY

    def test_buy_confidence_is_75(self):
        result = MomentumStrategy().generate_signal(make_candle(), make_indicators())
        assert result.confidence == 75

    def test_rsi_exactly_61_qualifies_as_buy(self):
        result = MomentumStrategy().generate_signal(
            make_candle(),
            make_indicators(rsi14=Decimal("61")),
        )
        assert result.signal_type == SignalType.BUY

    def test_buy_reason_mentions_rsi_and_macd(self):
        result = MomentumStrategy().generate_signal(make_candle(), make_indicators())
        assert "RSI" in result.reason
        assert "MACD" in result.reason


class TestSell:
    def test_rsi_below_40_and_macd_bearish_is_sell(self):
        result = MomentumStrategy().generate_signal(
            make_candle(),
            make_indicators(
                rsi14=Decimal("35"),
                macd=Decimal("-50"),
                macd_signal=Decimal("-30"),
            ),
        )
        assert result.signal_type == SignalType.SELL

    def test_sell_confidence_is_25(self):
        result = MomentumStrategy().generate_signal(
            make_candle(),
            make_indicators(
                rsi14=Decimal("35"),
                macd=Decimal("-50"),
                macd_signal=Decimal("-30"),
            ),
        )
        assert result.confidence == 25

    def test_rsi_exactly_39_qualifies_as_sell(self):
        result = MomentumStrategy().generate_signal(
            make_candle(),
            make_indicators(
                rsi14=Decimal("39"),
                macd=Decimal("-50"),
                macd_signal=Decimal("-30"),
            ),
        )
        assert result.signal_type == SignalType.SELL


class TestNoTrade:
    def test_rsi_bullish_but_macd_bearish_is_no_trade(self):
        result = MomentumStrategy().generate_signal(
            make_candle(),
            make_indicators(
                rsi14=Decimal("65"),      # bullish
                macd=Decimal("-50"),       # bearish — conflict
                macd_signal=Decimal("-30"),
            ),
        )
        assert result.signal_type == SignalType.NO_TRADE

    def test_macd_bullish_but_rsi_neutral_is_no_trade(self):
        result = MomentumStrategy().generate_signal(
            make_candle(),
            make_indicators(rsi14=Decimal("50")),  # neutral
        )
        assert result.signal_type == SignalType.NO_TRADE

    def test_rsi_bearish_but_macd_bullish_is_no_trade(self):
        result = MomentumStrategy().generate_signal(
            make_candle(),
            make_indicators(
                rsi14=Decimal("35"),      # bearish
                macd=Decimal("50"),        # bullish — conflict
                macd_signal=Decimal("30"),
            ),
        )
        assert result.signal_type == SignalType.NO_TRADE

    def test_rsi_exactly_60_is_not_buy(self):
        # rsi_val > 60 is required; rsi==60 is not strictly greater
        result = MomentumStrategy().generate_signal(
            make_candle(),
            make_indicators(rsi14=Decimal("60")),
        )
        assert result.signal_type == SignalType.NO_TRADE

    def test_rsi_exactly_40_is_not_sell(self):
        result = MomentumStrategy().generate_signal(
            make_candle(),
            make_indicators(
                rsi14=Decimal("40"),
                macd=Decimal("-50"),
                macd_signal=Decimal("-30"),
            ),
        )
        assert result.signal_type == SignalType.NO_TRADE

    def test_missing_rsi_is_no_trade(self):
        result = MomentumStrategy().generate_signal(
            make_candle(), make_indicators(rsi14=None)
        )
        assert result.signal_type == SignalType.NO_TRADE

    def test_missing_macd_is_no_trade(self):
        result = MomentumStrategy().generate_signal(
            make_candle(), make_indicators(macd=None)
        )
        assert result.signal_type == SignalType.NO_TRADE

    def test_missing_macd_signal_is_no_trade(self):
        result = MomentumStrategy().generate_signal(
            make_candle(), make_indicators(macd_signal=None)
        )
        assert result.signal_type == SignalType.NO_TRADE

    def test_no_trade_confidence_is_50(self):
        result = MomentumStrategy().generate_signal(
            make_candle(), make_indicators(rsi14=None)
        )
        assert result.confidence == 50


class TestSignalMetadata:
    def test_strategy_name_is_momentum(self):
        assert MomentumStrategy().strategy_name == "momentum"

    def test_signal_strategy_name_in_output(self):
        result = MomentumStrategy().generate_signal(make_candle(), make_indicators())
        assert result.strategy_name == "momentum"

    def test_required_indicators(self):
        strat = MomentumStrategy()
        assert "rsi14" in strat.required_indicators
        assert "macd" in strat.required_indicators
        assert "macd_signal" in strat.required_indicators

    def test_description_is_non_empty(self):
        assert len(MomentumStrategy().description) > 0

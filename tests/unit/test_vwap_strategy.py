from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from indicators.indicator_models import IndicatorRecord
from signals.signal_models import SignalType
from strategies.strategy_models import CandleSnapshot
from strategies.vwap_breakout import VWAPBreakoutStrategy

_INSTRUMENT = "NIFTY BANK"
_TIMEFRAME = "5min"
_NOW = datetime(2024, 3, 15, 10, 0)
_VWAP = Decimal("44500")
_PRICE_ABOVE = Decimal("44600")  # above VWAP
_PRICE_BELOW = Decimal("44400")  # below VWAP


def make_candle(close: Decimal) -> CandleSnapshot:
    return CandleSnapshot(
        instrument=_INSTRUMENT,
        timeframe=_TIMEFRAME,
        candle_time=_NOW,
        open=close,
        high=close,
        low=close,
        close=close,
    )


def make_indicators(
    vwap: Decimal | None = _VWAP,
    rsi14: Decimal | None = Decimal("60"),
    **overrides,
) -> IndicatorRecord:
    defaults: dict = {
        "instrument": _INSTRUMENT,
        "candle_time": _NOW,
        "timeframe": _TIMEFRAME,
        "ema20": Decimal("44600"),
        "ema50": Decimal("44400"),
        "ema200": Decimal("44000"),
        "vwap": vwap,
        "rsi14": rsi14,
        "macd": Decimal("50"),
        "macd_signal": Decimal("30"),
    }
    defaults.update(overrides)
    return IndicatorRecord(**defaults)


class TestBuy:
    def test_close_above_vwap_and_rsi_above_55_is_buy(self):
        result = VWAPBreakoutStrategy().generate_signal(
            make_candle(_PRICE_ABOVE),
            make_indicators(rsi14=Decimal("60")),
        )
        assert result.signal_type == SignalType.BUY

    def test_buy_confidence_is_70(self):
        result = VWAPBreakoutStrategy().generate_signal(
            make_candle(_PRICE_ABOVE),
            make_indicators(rsi14=Decimal("60")),
        )
        assert result.confidence == 70

    def test_rsi_exactly_56_is_buy(self):
        result = VWAPBreakoutStrategy().generate_signal(
            make_candle(_PRICE_ABOVE),
            make_indicators(rsi14=Decimal("56")),
        )
        assert result.signal_type == SignalType.BUY


class TestSell:
    def test_close_below_vwap_and_rsi_below_45_is_sell(self):
        result = VWAPBreakoutStrategy().generate_signal(
            make_candle(_PRICE_BELOW),
            make_indicators(rsi14=Decimal("40")),
        )
        assert result.signal_type == SignalType.SELL

    def test_sell_confidence_is_30(self):
        result = VWAPBreakoutStrategy().generate_signal(
            make_candle(_PRICE_BELOW),
            make_indicators(rsi14=Decimal("40")),
        )
        assert result.confidence == 30

    def test_rsi_exactly_44_is_sell(self):
        result = VWAPBreakoutStrategy().generate_signal(
            make_candle(_PRICE_BELOW),
            make_indicators(rsi14=Decimal("44")),
        )
        assert result.signal_type == SignalType.SELL


class TestNoTrade:
    def test_close_above_vwap_but_rsi_neutral_is_no_trade(self):
        result = VWAPBreakoutStrategy().generate_signal(
            make_candle(_PRICE_ABOVE),
            make_indicators(rsi14=Decimal("50")),
        )
        assert result.signal_type == SignalType.NO_TRADE

    def test_close_below_vwap_but_rsi_neutral_is_no_trade(self):
        result = VWAPBreakoutStrategy().generate_signal(
            make_candle(_PRICE_BELOW),
            make_indicators(rsi14=Decimal("50")),
        )
        assert result.signal_type == SignalType.NO_TRADE

    def test_close_above_vwap_but_rsi_below_55_is_no_trade(self):
        # RSI=54 is not > 55 → condition not met
        result = VWAPBreakoutStrategy().generate_signal(
            make_candle(_PRICE_ABOVE),
            make_indicators(rsi14=Decimal("54")),
        )
        assert result.signal_type == SignalType.NO_TRADE

    def test_close_below_vwap_but_rsi_above_45_is_no_trade(self):
        # RSI=46 is not < 45 → condition not met
        result = VWAPBreakoutStrategy().generate_signal(
            make_candle(_PRICE_BELOW),
            make_indicators(rsi14=Decimal("46")),
        )
        assert result.signal_type == SignalType.NO_TRADE

    def test_missing_vwap_is_no_trade(self):
        result = VWAPBreakoutStrategy().generate_signal(
            make_candle(_PRICE_ABOVE),
            make_indicators(vwap=None),
        )
        assert result.signal_type == SignalType.NO_TRADE

    def test_missing_rsi_is_no_trade(self):
        result = VWAPBreakoutStrategy().generate_signal(
            make_candle(_PRICE_ABOVE),
            make_indicators(rsi14=None),
        )
        assert result.signal_type == SignalType.NO_TRADE

    def test_both_missing_is_no_trade(self):
        result = VWAPBreakoutStrategy().generate_signal(
            make_candle(_PRICE_ABOVE),
            make_indicators(vwap=None, rsi14=None),
        )
        assert result.signal_type == SignalType.NO_TRADE

    def test_no_trade_confidence_is_50(self):
        result = VWAPBreakoutStrategy().generate_signal(
            make_candle(_PRICE_ABOVE),
            make_indicators(vwap=None),
        )
        assert result.confidence == 50


class TestSignalMetadata:
    def test_strategy_name_is_vwap(self):
        assert VWAPBreakoutStrategy().strategy_name == "vwap"

    def test_signal_instrument_from_candle(self):
        result = VWAPBreakoutStrategy().generate_signal(
            make_candle(_PRICE_ABOVE),
            make_indicators(rsi14=Decimal("60")),
        )
        assert result.instrument == _INSTRUMENT

    def test_signal_strategy_name_in_output(self):
        result = VWAPBreakoutStrategy().generate_signal(
            make_candle(_PRICE_ABOVE),
            make_indicators(rsi14=Decimal("60")),
        )
        assert result.strategy_name == "vwap"

    def test_required_indicators(self):
        strat = VWAPBreakoutStrategy()
        assert "vwap" in strat.required_indicators
        assert "rsi14" in strat.required_indicators

    def test_description_is_non_empty(self):
        assert len(VWAPBreakoutStrategy().description) > 0

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from indicators.indicator_models import IndicatorRecord
from signals.signal_models import SignalType
from strategies.supertrend_confluence import SupertrendConfluenceStrategy

_T = datetime(2024, 1, 15, 10, 25)


def _rec(tf: str = "5min", **kwargs) -> IndicatorRecord:
    return IndicatorRecord(instrument="NIFTY 50", candle_time=_T, timeframe=tf, **kwargs)


def _d(v) -> Decimal:
    return Decimal(str(v))


def _bull_aligned() -> dict:
    return {
        "1day": _rec("1day", supertrend_direction=1),
        "15min": _rec("15min", adx_14=_d(35)),
        "5min": _rec("5min", rsi14=_d(62)),
    }


def _bear_aligned() -> dict:
    return {
        "1day": _rec("1day", supertrend_direction=-1),
        "15min": _rec("15min", adx_14=_d(35)),
        "5min": _rec("5min", rsi14=_d(38)),
    }


class TestSupertrendConfluenceStrategyProperties:
    def setup_method(self):
        self.strat = SupertrendConfluenceStrategy()

    def test_strategy_name(self):
        assert self.strat.strategy_name == "supertrend_confluence"

    def test_default_trend_timeframe(self):
        assert self.strat.trend_timeframe == "1day"

    def test_default_setup_timeframe(self):
        assert self.strat.setup_timeframe == "15min"

    def test_default_entry_timeframe(self):
        assert self.strat.entry_timeframe == "5min"

    def test_required_indicators_present(self):
        indicators = self.strat.required_indicators
        assert "supertrend_direction" in indicators
        assert "adx_14" in indicators
        assert "rsi14" in indicators

    def test_description_is_non_empty(self):
        assert len(self.strat.description) > 0

    def test_custom_timeframes(self):
        strat = SupertrendConfluenceStrategy(trend_tf="15min", setup_tf="5min", entry_tf="1min")
        assert strat.trend_timeframe == "15min"
        assert strat.setup_timeframe == "5min"
        assert strat.entry_timeframe == "1min"


class TestSupertrendConfluenceBuySignal:
    def setup_method(self):
        self.strat = SupertrendConfluenceStrategy()

    def test_all_bullish_produces_buy(self):
        signal = self.strat.generate_multi_signal(_bull_aligned(), current_price=_d(19750))
        assert signal.signal_type == SignalType.BUY

    def test_buy_confidence_is_75(self):
        signal = self.strat.generate_multi_signal(_bull_aligned(), current_price=_d(19750))
        assert signal.confidence == 75

    def test_buy_strategy_name_correct(self):
        signal = self.strat.generate_multi_signal(_bull_aligned(), current_price=_d(19750))
        assert signal.strategy_name == "supertrend_confluence"


class TestSupertrendConfluenceSellSignal:
    def setup_method(self):
        self.strat = SupertrendConfluenceStrategy()

    def test_all_bearish_produces_sell(self):
        signal = self.strat.generate_multi_signal(_bear_aligned(), current_price=_d(19200))
        assert signal.signal_type == SignalType.SELL

    def test_sell_confidence_is_25(self):
        signal = self.strat.generate_multi_signal(_bear_aligned(), current_price=_d(19200))
        assert signal.confidence == 25


class TestSupertrendConfluenceNoTrade:
    def setup_method(self):
        self.strat = SupertrendConfluenceStrategy()

    def test_weak_adx_produces_no_trade(self):
        aligned = _bull_aligned()
        aligned["15min"] = _rec("15min", adx_14=_d(20))
        signal = self.strat.generate_multi_signal(aligned, current_price=_d(19750))
        assert signal.signal_type == SignalType.NO_TRADE

    def test_neutral_rsi_on_bullish_supertrend_produces_no_trade(self):
        aligned = _bull_aligned()
        aligned["5min"] = _rec("5min", rsi14=_d(50))
        signal = self.strat.generate_multi_signal(aligned, current_price=_d(19750))
        assert signal.signal_type == SignalType.NO_TRADE

    def test_missing_supertrend_produces_no_trade(self):
        aligned = _bull_aligned()
        aligned["1day"] = _rec("1day")  # no supertrend_direction
        signal = self.strat.generate_multi_signal(aligned, current_price=_d(19750))
        assert signal.signal_type == SignalType.NO_TRADE

    def test_missing_adx_produces_no_trade(self):
        aligned = _bull_aligned()
        aligned["15min"] = _rec("15min")  # no adx_14
        signal = self.strat.generate_multi_signal(aligned, current_price=_d(19750))
        assert signal.signal_type == SignalType.NO_TRADE

    def test_missing_rsi_produces_no_trade(self):
        aligned = _bull_aligned()
        aligned["5min"] = _rec("5min")  # no rsi14
        signal = self.strat.generate_multi_signal(aligned, current_price=_d(19750))
        assert signal.signal_type == SignalType.NO_TRADE

    def test_all_none_fallback_no_trade(self):
        signal = self.strat.generate_multi_signal(
            {"1day": None, "15min": None, "5min": None}, current_price=_d(19500)
        )
        assert signal.signal_type == SignalType.NO_TRADE

    def test_supertrend_direction_zero_no_trade(self):
        aligned = _bull_aligned()
        aligned["1day"] = _rec("1day", supertrend_direction=0)
        signal = self.strat.generate_multi_signal(aligned, current_price=_d(19750))
        assert signal.signal_type == SignalType.NO_TRADE

    def test_rsi_exactly_at_bull_threshold_no_trade(self):
        aligned = _bull_aligned()
        aligned["5min"] = _rec("5min", rsi14=_d(55))  # not > 55
        signal = self.strat.generate_multi_signal(aligned, current_price=_d(19750))
        assert signal.signal_type == SignalType.NO_TRADE

    def test_adx_exactly_at_threshold_no_trade(self):
        aligned = _bull_aligned()
        aligned["15min"] = _rec("15min", adx_14=_d(25))  # not > 25
        signal = self.strat.generate_multi_signal(aligned, current_price=_d(19750))
        assert signal.signal_type == SignalType.NO_TRADE

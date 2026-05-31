from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from indicators.indicator_models import IndicatorRecord
from signals.signal_models import SignalType
from strategies.trend_confluence import TrendConfluenceStrategy

_T = datetime(2024, 1, 15, 10, 25)


def _rec(tf: str = "5min", **kwargs) -> IndicatorRecord:
    return IndicatorRecord(instrument="NIFTY 50", candle_time=_T, timeframe=tf, **kwargs)


def _d(v) -> Decimal:
    return Decimal(str(v))


def _bull_aligned() -> dict:
    return {
        "1day": _rec("1day", ema20=_d(220), ema50=_d(200), ema200=_d(180)),
        "15min": _rec("15min", adx_14=_d(35)),
        "5min": _rec("5min", vwap=_d(19500)),
    }


def _bear_aligned() -> dict:
    return {
        "1day": _rec("1day", ema20=_d(180), ema50=_d(200), ema200=_d(220)),
        "15min": _rec("15min", adx_14=_d(35)),
        "5min": _rec("5min", vwap=_d(19500)),
    }


class TestTrendConfluenceStrategyProperties:
    def setup_method(self):
        self.strat = TrendConfluenceStrategy()

    def test_strategy_name(self):
        assert self.strat.strategy_name == "trend_confluence"

    def test_default_trend_timeframe(self):
        assert self.strat.trend_timeframe == "1day"

    def test_default_setup_timeframe(self):
        assert self.strat.setup_timeframe == "15min"

    def test_default_entry_timeframe(self):
        assert self.strat.entry_timeframe == "5min"

    def test_required_indicators_present(self):
        indicators = self.strat.required_indicators
        assert "ema20" in indicators
        assert "ema50" in indicators
        assert "ema200" in indicators
        assert "adx_14" in indicators
        assert "vwap" in indicators

    def test_description_is_non_empty_string(self):
        assert isinstance(self.strat.description, str)
        assert len(self.strat.description) > 0

    def test_custom_timeframes_via_constructor(self):
        strat = TrendConfluenceStrategy(trend_tf="15min", setup_tf="5min", entry_tf="1min")
        assert strat.trend_timeframe == "15min"
        assert strat.setup_timeframe == "5min"
        assert strat.entry_timeframe == "1min"


class TestTrendConfluenceBuySignal:
    def setup_method(self):
        self.strat = TrendConfluenceStrategy()

    def test_all_conditions_bullish_produces_buy(self):
        signal = self.strat.generate_multi_signal(
            _bull_aligned(), current_price=_d(19750)
        )
        assert signal.signal_type == SignalType.BUY

    def test_buy_confidence_is_75(self):
        signal = self.strat.generate_multi_signal(
            _bull_aligned(), current_price=_d(19750)
        )
        assert signal.confidence == 75

    def test_buy_strategy_name_correct(self):
        signal = self.strat.generate_multi_signal(
            _bull_aligned(), current_price=_d(19750)
        )
        assert signal.strategy_name == "trend_confluence"


class TestTrendConfluenceSellSignal:
    def setup_method(self):
        self.strat = TrendConfluenceStrategy()

    def test_all_conditions_bearish_produces_sell(self):
        signal = self.strat.generate_multi_signal(
            _bear_aligned(), current_price=_d(19200)
        )
        assert signal.signal_type == SignalType.SELL

    def test_sell_confidence_is_25(self):
        signal = self.strat.generate_multi_signal(
            _bear_aligned(), current_price=_d(19200)
        )
        assert signal.confidence == 25


class TestTrendConfluenceNoTradeConditions:
    def setup_method(self):
        self.strat = TrendConfluenceStrategy()

    def test_weak_adx_produces_no_trade(self):
        aligned = _bull_aligned()
        aligned["15min"] = _rec("15min", adx_14=_d(20))  # below threshold
        signal = self.strat.generate_multi_signal(aligned, current_price=_d(19750))
        assert signal.signal_type == SignalType.NO_TRADE

    def test_price_below_vwap_on_bull_ema_produces_no_trade(self):
        aligned = _bull_aligned()
        signal = self.strat.generate_multi_signal(aligned, current_price=_d(19200))
        assert signal.signal_type == SignalType.NO_TRADE

    def test_mixed_ema_produces_no_trade(self):
        aligned = _bull_aligned()
        aligned["1day"] = _rec("1day", ema20=_d(210), ema50=_d(180), ema200=_d(200))
        signal = self.strat.generate_multi_signal(aligned, current_price=_d(19750))
        assert signal.signal_type == SignalType.NO_TRADE

    def test_missing_trend_data_produces_no_trade(self):
        aligned = {"1day": None, "15min": _rec("15min", adx_14=_d(35)), "5min": _rec("5min", vwap=_d(19500))}
        signal = self.strat.generate_multi_signal(aligned, current_price=_d(19750))
        assert signal.signal_type == SignalType.NO_TRADE

    def test_all_none_produces_no_trade_fallback(self):
        signal = self.strat.generate_multi_signal(
            {"1day": None, "15min": None, "5min": None}, current_price=_d(19500)
        )
        assert signal.signal_type == SignalType.NO_TRADE

    def test_adx_exactly_25_produces_no_trade(self):
        aligned = _bull_aligned()
        aligned["15min"] = _rec("15min", adx_14=_d(25))
        signal = self.strat.generate_multi_signal(aligned, current_price=_d(19750))
        assert signal.signal_type == SignalType.NO_TRADE


class TestTrendConfluenceSingleTfFallback:
    """MultiTimeframeStrategy.generate_signal() provides single-TF fallback."""

    def test_single_tf_fallback_uses_generate_signal(self):
        from strategies.strategy_models import CandleSnapshot

        strat = TrendConfluenceStrategy()
        # Only entry_tf populated; higher TFs are None — strategy returns NO_TRADE
        indicators = _rec("5min", vwap=_d(19500))
        candle = CandleSnapshot(
            instrument="NIFTY 50",
            timeframe="5min",
            open=_d(19600), high=_d(19700), low=_d(19550),
            close=_d(19650), volume=10000,
            candle_time=_T,
        )
        signal = strat.generate_signal(candle, indicators)
        assert signal.signal_type == SignalType.NO_TRADE

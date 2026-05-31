from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from indicators.indicator_models import IndicatorRecord
from signals.signal_models import SignalType
from strategies.momentum_confluence import MomentumConfluenceStrategy

_T = datetime(2024, 1, 15, 10, 25)


def _rec(tf: str = "1min", **kwargs) -> IndicatorRecord:
    return IndicatorRecord(instrument="NIFTY 50", candle_time=_T, timeframe=tf, **kwargs)


def _d(v) -> Decimal:
    return Decimal(str(v))


# Bullish aligned records: MACD bullish on 15min, RSI>60 on 5min, OBV ready on 1min
def _bull_aligned(obv: float = 1_200_000) -> dict:
    return {
        "15min": _rec("15min", macd=_d("0.06"), macd_signal=_d("0.02")),
        "5min": _rec("5min", rsi14=_d(65)),
        "1min": _rec("1min", obv=_d(obv)),
    }


# Bearish aligned records
def _bear_aligned(obv: float = 800_000) -> dict:
    return {
        "15min": _rec("15min", macd=_d("0.01"), macd_signal=_d("0.05")),
        "5min": _rec("5min", rsi14=_d(35)),
        "1min": _rec("1min", obv=_d(obv)),
    }


class TestMomentumConfluenceStrategyProperties:
    def setup_method(self):
        self.strat = MomentumConfluenceStrategy()

    def test_strategy_name(self):
        assert self.strat.strategy_name == "momentum_confluence"

    def test_default_trend_timeframe(self):
        assert self.strat.trend_timeframe == "15min"

    def test_default_setup_timeframe(self):
        assert self.strat.setup_timeframe == "5min"

    def test_default_entry_timeframe(self):
        assert self.strat.entry_timeframe == "1min"

    def test_required_indicators_present(self):
        indicators = self.strat.required_indicators
        assert "macd" in indicators
        assert "macd_signal" in indicators
        assert "rsi14" in indicators
        assert "obv" in indicators

    def test_description_non_empty(self):
        assert len(self.strat.description) > 0

    def test_custom_timeframes(self):
        strat = MomentumConfluenceStrategy(trend_tf="5min", setup_tf="1min", entry_tf="1min")
        assert strat.trend_timeframe == "5min"


class TestMomentumConfluenceFullBuySignal:
    """All three conditions confirmed → confidence=75."""

    def setup_method(self):
        self.strat = MomentumConfluenceStrategy()

    def test_full_confluence_buy_signal(self):
        curr_obv = 1_200_000
        prev_obv = 1_000_000
        aligned = _bull_aligned(curr_obv)
        prev_aligned = {"1min": _rec("1min", obv=_d(prev_obv))}
        signal = self.strat.generate_multi_signal(
            aligned, current_price=_d(19750), prev_aligned_records=prev_aligned
        )
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence == 75

    def test_full_buy_strategy_name(self):
        prev_aligned = {"1min": _rec("1min", obv=_d(1_000_000))}
        signal = self.strat.generate_multi_signal(
            _bull_aligned(), current_price=_d(19750), prev_aligned_records=prev_aligned
        )
        assert signal.strategy_name == "momentum_confluence"


class TestMomentumConfluenceFullSellSignal:
    """All three conditions bearish → confidence=25."""

    def setup_method(self):
        self.strat = MomentumConfluenceStrategy()

    def test_full_confluence_sell_signal(self):
        aligned = _bear_aligned(800_000)
        prev_aligned = {"1min": _rec("1min", obv=_d(1_000_000))}
        signal = self.strat.generate_multi_signal(
            aligned, current_price=_d(19200), prev_aligned_records=prev_aligned
        )
        assert signal.signal_type == SignalType.SELL
        assert signal.confidence == 25


class TestMomentumConfluencePartialBuySignal:
    """MACD + RSI confirmed, OBV unavailable → confidence=65."""

    def setup_method(self):
        self.strat = MomentumConfluenceStrategy()

    def test_no_obv_data_partial_buy(self):
        aligned = {
            "15min": _rec("15min", macd=_d("0.06"), macd_signal=_d("0.02")),
            "5min": _rec("5min", rsi14=_d(65)),
            "1min": _rec("1min"),  # no OBV
        }
        signal = self.strat.generate_multi_signal(aligned, current_price=_d(19750))
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence == 65

    def test_no_prev_record_partial_buy(self):
        aligned = _bull_aligned()
        # no prev_aligned_records → OBV unavailable
        signal = self.strat.generate_multi_signal(aligned, current_price=_d(19750))
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence == 65


class TestMomentumConfluencePartialSellSignal:
    """MACD + RSI bearish, OBV unavailable → confidence=35."""

    def setup_method(self):
        self.strat = MomentumConfluenceStrategy()

    def test_no_obv_data_partial_sell(self):
        aligned = {
            "15min": _rec("15min", macd=_d("0.01"), macd_signal=_d("0.05")),
            "5min": _rec("5min", rsi14=_d(35)),
            "1min": _rec("1min"),  # no OBV
        }
        signal = self.strat.generate_multi_signal(aligned, current_price=_d(19200))
        assert signal.signal_type == SignalType.SELL
        assert signal.confidence == 35


class TestMomentumConfluenceNoTradeConditions:
    def setup_method(self):
        self.strat = MomentumConfluenceStrategy()

    def test_missing_macd_produces_no_trade(self):
        aligned = {
            "15min": _rec("15min"),  # no MACD
            "5min": _rec("5min", rsi14=_d(65)),
            "1min": _rec("1min", obv=_d(1_200_000)),
        }
        signal = self.strat.generate_multi_signal(aligned, current_price=_d(19750))
        assert signal.signal_type == SignalType.NO_TRADE

    def test_neutral_rsi_produces_no_trade(self):
        aligned = {
            "15min": _rec("15min", macd=_d("0.06"), macd_signal=_d("0.02")),
            "5min": _rec("5min", rsi14=_d(50)),  # neutral
            "1min": _rec("1min", obv=_d(1_200_000)),
        }
        prev_aligned = {"1min": _rec("1min", obv=_d(1_000_000))}
        signal = self.strat.generate_multi_signal(
            aligned, current_price=_d(19750), prev_aligned_records=prev_aligned
        )
        assert signal.signal_type == SignalType.NO_TRADE

    def test_obv_falling_against_bullish_macd_rsi_no_trade(self):
        aligned = _bull_aligned(900_000)  # OBV at 900k, prev will be 1M → falling
        prev_aligned = {"1min": _rec("1min", obv=_d(1_000_000))}
        signal = self.strat.generate_multi_signal(
            aligned, current_price=_d(19750), prev_aligned_records=prev_aligned
        )
        assert signal.signal_type == SignalType.NO_TRADE

    def test_all_none_records_no_trade(self):
        signal = self.strat.generate_multi_signal(
            {"15min": None, "5min": None, "1min": None}, current_price=_d(19500)
        )
        assert signal.signal_type == SignalType.NO_TRADE

    def test_macd_equal_to_signal_no_trade(self):
        aligned = {
            "15min": _rec("15min", macd=_d("0.03"), macd_signal=_d("0.03")),
            "5min": _rec("5min", rsi14=_d(65)),
            "1min": _rec("1min"),
        }
        signal = self.strat.generate_multi_signal(aligned, current_price=_d(19750))
        assert signal.signal_type == SignalType.NO_TRADE

    def test_rsi_exactly_60_is_not_bullish(self):
        aligned = {
            "15min": _rec("15min", macd=_d("0.06"), macd_signal=_d("0.02")),
            "5min": _rec("5min", rsi14=_d(60)),  # not > 60
            "1min": _rec("1min"),
        }
        signal = self.strat.generate_multi_signal(aligned, current_price=_d(19750))
        # RSI=60 is not > 60, so rsi_bullish=False → partial confluence fails
        assert signal.signal_type == SignalType.NO_TRADE

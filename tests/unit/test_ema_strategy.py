from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from indicators.indicator_models import IndicatorRecord
from signals.signal_models import SignalType
from strategies.ema_crossover import EmaCrossoverStrategy
from strategies.strategy_models import CandleSnapshot

_INSTRUMENT = "NIFTY 50"
_TIMEFRAME = "1day"
_NOW = datetime(2024, 3, 15)
_PRICE = Decimal("22550")


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
        "ema20": Decimal("22600"),
        "ema50": Decimal("22400"),
        "ema200": Decimal("22000"),
        "rsi14": Decimal("60"),
        "vwap": Decimal("22500"),
        "macd": Decimal("50"),
        "macd_signal": Decimal("30"),
    }
    defaults.update(overrides)
    return IndicatorRecord(**defaults)


class TestStrongBuy:
    def test_full_bullish_alignment_produces_strong_buy(self):
        # ema20=22600 > ema50=22400 > ema200=22000
        result = EmaCrossoverStrategy().generate_signal(make_candle(), make_indicators())
        assert result.signal_type == SignalType.STRONG_BUY

    def test_strong_buy_confidence_is_80(self):
        result = EmaCrossoverStrategy().generate_signal(make_candle(), make_indicators())
        assert result.confidence == 80

    def test_strong_buy_reason_mentions_all_three_emas(self):
        result = EmaCrossoverStrategy().generate_signal(make_candle(), make_indicators())
        assert "EMA20" in result.reason
        assert "EMA50" in result.reason
        assert "EMA200" in result.reason


class TestStrongSell:
    def test_full_bearish_alignment_produces_strong_sell(self):
        rec = make_indicators(
            ema20=Decimal("22000"),
            ema50=Decimal("22400"),
            ema200=Decimal("22600"),
        )
        result = EmaCrossoverStrategy().generate_signal(make_candle(), rec)
        assert result.signal_type == SignalType.STRONG_SELL

    def test_strong_sell_confidence_is_20(self):
        rec = make_indicators(
            ema20=Decimal("22000"),
            ema50=Decimal("22400"),
            ema200=Decimal("22600"),
        )
        result = EmaCrossoverStrategy().generate_signal(make_candle(), rec)
        assert result.confidence == 20


class TestNoTrade:
    def test_partial_alignment_ema50_not_above_ema200_is_no_trade(self):
        # ema20 > ema50 but ema50 < ema200 — not a full stack
        rec = make_indicators(
            ema20=Decimal("22600"),
            ema50=Decimal("22400"),
            ema200=Decimal("22500"),  # ema50 < ema200
        )
        result = EmaCrossoverStrategy().generate_signal(make_candle(), rec)
        assert result.signal_type == SignalType.NO_TRADE

    def test_missing_ema200_is_no_trade(self):
        rec = make_indicators(ema200=None)
        result = EmaCrossoverStrategy().generate_signal(make_candle(), rec)
        assert result.signal_type == SignalType.NO_TRADE

    def test_missing_ema20_is_no_trade(self):
        rec = make_indicators(ema20=None)
        result = EmaCrossoverStrategy().generate_signal(make_candle(), rec)
        assert result.signal_type == SignalType.NO_TRADE

    def test_all_emas_missing_is_no_trade(self):
        rec = make_indicators(ema20=None, ema50=None, ema200=None)
        result = EmaCrossoverStrategy().generate_signal(make_candle(), rec)
        assert result.signal_type == SignalType.NO_TRADE

    def test_flat_emas_equal_is_no_trade(self):
        price = Decimal("22500")
        rec = make_indicators(ema20=price, ema50=price, ema200=price)
        result = EmaCrossoverStrategy().generate_signal(make_candle(), rec)
        assert result.signal_type == SignalType.NO_TRADE

    def test_no_trade_confidence_is_50(self):
        rec = make_indicators(ema200=None)
        result = EmaCrossoverStrategy().generate_signal(make_candle(), rec)
        assert result.confidence == 50


class TestSignalMetadata:
    def test_strategy_name_is_ema(self):
        assert EmaCrossoverStrategy().strategy_name == "ema"

    def test_signal_instrument_matches_candle(self):
        result = EmaCrossoverStrategy().generate_signal(make_candle(), make_indicators())
        assert result.instrument == _INSTRUMENT

    def test_signal_timeframe_matches_candle(self):
        result = EmaCrossoverStrategy().generate_signal(make_candle(), make_indicators())
        assert result.timeframe == _TIMEFRAME

    def test_signal_strategy_name_is_ema(self):
        result = EmaCrossoverStrategy().generate_signal(make_candle(), make_indicators())
        assert result.strategy_name == "ema"

    def test_signal_time_matches_candle_time(self):
        result = EmaCrossoverStrategy().generate_signal(make_candle(), make_indicators())
        assert result.signal_time == _NOW

    def test_reason_is_non_empty_for_all_signal_types(self):
        strat = EmaCrossoverStrategy()
        for rec in [
            make_indicators(),                             # STRONG_BUY
            make_indicators(ema20=Decimal("22000"), ema50=Decimal("22400"), ema200=Decimal("22600")),  # STRONG_SELL
            make_indicators(ema200=None),                  # NO_TRADE
        ]:
            result = strat.generate_signal(make_candle(), rec)
            assert len(result.reason) > 0

    def test_required_indicators_contains_all_three_emas(self):
        strat = EmaCrossoverStrategy()
        assert "ema20" in strat.required_indicators
        assert "ema50" in strat.required_indicators
        assert "ema200" in strat.required_indicators

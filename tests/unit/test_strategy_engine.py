from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from indicators.indicator_models import IndicatorRecord
from signals.signal_models import SignalType
from strategies.ema_crossover import EmaCrossoverStrategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.momentum import MomentumStrategy
from strategies.registry import list_strategies
from strategies.strategy_engine import StrategyEngineService
from strategies.strategy_models import CandleSnapshot, StrategySignal
from strategies.vwap_breakout import VWAPBreakoutStrategy

_INSTRUMENT = "NIFTY 50"
_TIMEFRAME = "1day"
_NOW = datetime(2024, 6, 1)
_PRICE = Decimal("22000")


def make_indicators(**overrides) -> IndicatorRecord:
    defaults: dict = {
        "instrument": _INSTRUMENT,
        "candle_time": _NOW,
        "timeframe": _TIMEFRAME,
        "ema20": Decimal("22100"),
        "ema50": Decimal("21900"),
        "ema200": Decimal("21500"),
        "rsi14": Decimal("65"),
        "vwap": Decimal("21900"),   # price will be above VWAP
        "macd": Decimal("50"),
        "macd_signal": Decimal("30"),
    }
    defaults.update(overrides)
    return IndicatorRecord(**defaults)


class TestEvaluate:
    def test_returns_strategy_signal(self):
        engine = StrategyEngineService()
        result = engine.evaluate(EmaCrossoverStrategy(), make_indicators(), _PRICE)
        assert isinstance(result, StrategySignal)

    def test_candle_snapshot_close_equals_current_price(self):
        received_candles: list[CandleSnapshot] = []

        class CapturingStrategy(EmaCrossoverStrategy):
            def generate_signal(self, candle, indicators):
                received_candles.append(candle)
                return super().generate_signal(candle, indicators)

        engine = StrategyEngineService()
        engine.evaluate(CapturingStrategy(), make_indicators(), _PRICE)
        assert received_candles[0].close == _PRICE

    def test_candle_instrument_from_indicators(self):
        received_candles: list[CandleSnapshot] = []

        class CapturingStrategy(EmaCrossoverStrategy):
            def generate_signal(self, candle, indicators):
                received_candles.append(candle)
                return super().generate_signal(candle, indicators)

        StrategyEngineService().evaluate(CapturingStrategy(), make_indicators(), _PRICE)
        assert received_candles[0].instrument == _INSTRUMENT

    def test_ema_strategy_returns_strong_buy_on_bullish_indicators(self):
        engine = StrategyEngineService()
        result = engine.evaluate(EmaCrossoverStrategy(), make_indicators(), _PRICE)
        assert result.signal_type == SignalType.STRONG_BUY

    def test_mean_reversion_buy_on_oversold_rsi(self):
        engine = StrategyEngineService()
        result = engine.evaluate(
            MeanReversionStrategy(),
            make_indicators(rsi14=Decimal("25")),
            _PRICE,
        )
        assert result.signal_type == SignalType.BUY

    def test_vwap_buy_when_price_above_vwap_and_rsi_bullish(self):
        # price=22000 > vwap=21900, rsi=65>55 → BUY
        engine = StrategyEngineService()
        result = engine.evaluate(
            VWAPBreakoutStrategy(),
            make_indicators(vwap=Decimal("21900"), rsi14=Decimal("65")),
            _PRICE,
        )
        assert result.signal_type == SignalType.BUY

    def test_momentum_buy_on_strong_rsi_and_macd(self):
        engine = StrategyEngineService()
        result = engine.evaluate(
            MomentumStrategy(),
            make_indicators(rsi14=Decimal("65"), macd=Decimal("50"), macd_signal=Decimal("30")),
            _PRICE,
        )
        assert result.signal_type == SignalType.BUY

    def test_signal_carries_correct_strategy_name(self):
        for strat in [
            EmaCrossoverStrategy(),
            VWAPBreakoutStrategy(),
            MomentumStrategy(),
            MeanReversionStrategy(),
        ]:
            result = StrategyEngineService().evaluate(strat, make_indicators(), _PRICE)
            assert result.strategy_name == strat.strategy_name


class TestEvaluateAll:
    def test_returns_dict_with_all_strategies(self):
        engine = StrategyEngineService()
        results = engine.evaluate_all(make_indicators(), _PRICE)
        assert set(results.keys()) == set(list_strategies())

    def test_all_values_are_strategy_signals(self):
        results = StrategyEngineService().evaluate_all(make_indicators(), _PRICE)
        for sig in results.values():
            assert isinstance(sig, StrategySignal)

    def test_keys_match_registered_strategy_names(self):
        results = StrategyEngineService().evaluate_all(make_indicators(), _PRICE)
        for name, sig in results.items():
            assert sig.strategy_name == name

    def test_no_trade_when_all_indicators_missing(self):
        rec = make_indicators(
            ema20=None, ema50=None, ema200=None,
            rsi14=None, vwap=None, macd=None, macd_signal=None,
        )
        results = StrategyEngineService().evaluate_all(rec, _PRICE)
        for sig in results.values():
            assert sig.signal_type == SignalType.NO_TRADE

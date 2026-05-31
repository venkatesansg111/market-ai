from __future__ import annotations

import pytest

from strategies.ema_crossover import EmaCrossoverStrategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.momentum import MomentumStrategy
from strategies.momentum_confluence import MomentumConfluenceStrategy
from strategies.registry import STRATEGIES, get_strategy, list_strategies
from strategies.supertrend_confluence import SupertrendConfluenceStrategy
from strategies.trend_confluence import TrendConfluenceStrategy
from strategies.vwap_breakout import VWAPBreakoutStrategy


class TestGetStrategy:
    def test_ema_returns_ema_crossover(self):
        assert isinstance(get_strategy("ema"), EmaCrossoverStrategy)

    def test_vwap_returns_vwap_breakout(self):
        assert isinstance(get_strategy("vwap"), VWAPBreakoutStrategy)

    def test_momentum_returns_momentum(self):
        assert isinstance(get_strategy("momentum"), MomentumStrategy)

    def test_mean_reversion_returns_mean_reversion(self):
        assert isinstance(get_strategy("mean_reversion"), MeanReversionStrategy)

    def test_trend_confluence_returns_trend_confluence(self):
        assert isinstance(get_strategy("trend_confluence"), TrendConfluenceStrategy)

    def test_supertrend_confluence_returns_supertrend_confluence(self):
        assert isinstance(get_strategy("supertrend_confluence"), SupertrendConfluenceStrategy)

    def test_momentum_confluence_returns_momentum_confluence(self):
        assert isinstance(get_strategy("momentum_confluence"), MomentumConfluenceStrategy)

    def test_lookup_is_case_insensitive(self):
        assert get_strategy("EMA") is get_strategy("ema")
        assert get_strategy("VWAP") is get_strategy("vwap")
        assert get_strategy("Momentum") is get_strategy("momentum")

    def test_unknown_name_raises_key_error(self):
        with pytest.raises(KeyError, match="unknown_xyz"):
            get_strategy("unknown_xyz")

    def test_empty_string_raises_key_error(self):
        with pytest.raises(KeyError):
            get_strategy("")


class TestListStrategies:
    def test_returns_all_strategy_names(self):
        names = list_strategies()
        assert set(names) == {
            "ema", "vwap", "momentum", "mean_reversion",
            "trend_confluence", "supertrend_confluence", "momentum_confluence",
        }

    def test_returns_exactly_seven(self):
        assert len(list_strategies()) == 7

    def test_returns_list_type(self):
        assert isinstance(list_strategies(), list)


class TestStrategyAttributes:
    def test_strategy_names_match_registry_keys(self):
        for key, strat in STRATEGIES.items():
            assert strat.strategy_name == key

    def test_all_have_non_empty_description(self):
        for strat in STRATEGIES.values():
            assert isinstance(strat.description, str)
            assert len(strat.description) > 0

    def test_all_have_non_empty_required_indicators(self):
        for strat in STRATEGIES.values():
            assert isinstance(strat.required_indicators, list)
            assert len(strat.required_indicators) > 0

    def test_required_indicators_are_strings(self):
        for strat in STRATEGIES.values():
            for ind in strat.required_indicators:
                assert isinstance(ind, str)

    def test_registry_instances_are_singletons(self):
        # Same object returned on repeated lookups (module-level singletons)
        assert get_strategy("ema") is get_strategy("ema")

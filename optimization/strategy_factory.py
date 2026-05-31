"""Factory for creating parameterized strategy instances used during optimization."""
from __future__ import annotations

from typing import Any

from strategies.base import Strategy


def create_strategy(strategy_name: str, params: dict[str, Any]) -> Strategy:
    """Instantiate a strategy with the given parameter overrides.

    Falls back to the registry singleton (default parameters) for unknown names.

    Parameters are forwarded to the strategy constructor by name, so keys in
    *params* must match the constructor argument names exactly.
    """
    name = strategy_name.lower()

    if name == "momentum":
        from strategies.momentum import MomentumStrategy
        return MomentumStrategy(
            rsi_buy_threshold=params.get("rsi_buy_threshold", 60.0),
            rsi_sell_threshold=params.get("rsi_sell_threshold", 40.0),
        )

    if name == "vwap":
        from strategies.vwap_breakout import VWAPBreakoutStrategy
        return VWAPBreakoutStrategy(
            rsi_buy_threshold=params.get("rsi_buy_threshold", 55.0),
            rsi_sell_threshold=params.get("rsi_sell_threshold", 45.0),
        )

    if name == "ema":
        from strategies.ema_crossover import EmaCrossoverStrategy
        return EmaCrossoverStrategy(
            confidence_buy=params.get("confidence_buy", 80),
            confidence_sell=params.get("confidence_sell", 20),
        )

    if name == "mean_reversion":
        from strategies.mean_reversion import MeanReversionStrategy
        return MeanReversionStrategy(
            rsi_oversold=params.get("rsi_oversold", 30.0),
            rsi_overbought=params.get("rsi_overbought", 70.0),
        )

    if name == "trend_confluence":
        from strategies.trend_confluence import TrendConfluenceStrategy
        return TrendConfluenceStrategy(
            trend_tf=params.get("trend_tf", "1day"),
            setup_tf=params.get("setup_tf", "15min"),
            entry_tf=params.get("entry_tf", "5min"),
            adx_threshold=params.get("adx_threshold", 25.0),
        )

    if name == "supertrend_confluence":
        from strategies.supertrend_confluence import SupertrendConfluenceStrategy
        return SupertrendConfluenceStrategy(
            trend_tf=params.get("trend_tf", "1day"),
            setup_tf=params.get("setup_tf", "15min"),
            entry_tf=params.get("entry_tf", "5min"),
            adx_threshold=params.get("adx_threshold", 25.0),
            rsi_bull=params.get("rsi_bull", 55.0),
            rsi_bear=params.get("rsi_bear", 45.0),
        )

    if name == "momentum_confluence":
        from strategies.momentum_confluence import MomentumConfluenceStrategy
        return MomentumConfluenceStrategy(
            trend_tf=params.get("trend_tf", "15min"),
            setup_tf=params.get("setup_tf", "5min"),
            entry_tf=params.get("entry_tf", "1min"),
            rsi_bull=params.get("rsi_bull", 60.0),
            rsi_bear=params.get("rsi_bear", 40.0),
        )

    # Unknown name: return the registered singleton with default params
    from strategies.registry import get_strategy
    return get_strategy(name)

from __future__ import annotations

from strategies.base import Strategy
from strategies.ema_crossover import EmaCrossoverStrategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.momentum import MomentumStrategy
from strategies.vwap_breakout import VWAPBreakoutStrategy

# Module-level singletons — strategies are stateless so one instance per type is safe.
STRATEGIES: dict[str, Strategy] = {
    "ema": EmaCrossoverStrategy(),
    "vwap": VWAPBreakoutStrategy(),
    "momentum": MomentumStrategy(),
    "mean_reversion": MeanReversionStrategy(),
}


def get_strategy(name: str) -> Strategy:
    """Return the registered strategy for *name* (case-insensitive).

    Raises:
        KeyError: if *name* is not registered. Message includes available names.
    """
    key = name.lower()
    if key not in STRATEGIES:
        raise KeyError(
            f"Unknown strategy '{name}'. "
            f"Available: {list(STRATEGIES)}"
        )
    return STRATEGIES[key]


def list_strategies() -> list[str]:
    """Return all registered strategy names in registration order."""
    return list(STRATEGIES)

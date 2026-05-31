"""ParameterGridGenerator — generate valid parameter combinations for optimization."""
from __future__ import annotations

import itertools
from typing import Any


class ParameterGridGenerator:
    """Generates all valid parameter combinations from a grid specification.

    The spec maps parameter names to lists of candidate values::

        {"rsi_buy_threshold": [55, 60, 65], "rsi_sell_threshold": [35, 40, 45]}

    Built-in constraint rules (automatically enforced):

    * ``ema_fast`` must be strictly less than ``ema_slow``
    * ``rsi_sell_threshold`` must be strictly less than ``rsi_buy_threshold``
    """

    _LESS_THAN_CONSTRAINTS: list[tuple[str, str]] = [
        ("ema_fast", "ema_slow"),
        ("rsi_sell_threshold", "rsi_buy_threshold"),
    ]

    def generate(self, grid_spec: dict[str, list[Any]]) -> list[dict[str, Any]]:
        """Return all valid parameter dictionaries from the Cartesian product of *grid_spec*.

        Returns ``[{}]`` when *grid_spec* is empty (single no-op combination).
        """
        if not grid_spec:
            return [{}]

        keys = list(grid_spec.keys())
        value_lists = [grid_spec[k] for k in keys]

        valid: list[dict[str, Any]] = []
        for values in itertools.product(*value_lists):
            params = dict(zip(keys, values))
            if self.is_valid_combination(params):
                valid.append(params)
        return valid

    @classmethod
    def is_valid_combination(cls, params: dict[str, Any]) -> bool:
        """Return *True* if *params* satisfies all built-in constraints."""
        for less_key, greater_key in cls._LESS_THAN_CONSTRAINTS:
            if less_key in params and greater_key in params:
                if params[less_key] >= params[greater_key]:
                    return False
        return True

    @staticmethod
    def default_grid(strategy_name: str) -> dict[str, list[Any]]:
        """Return a sensible default parameter grid for a registered strategy name.

        Returns an empty dict for unknown strategy names so the optimizer can
        still run a single default-parameter backtest.
        """
        grids: dict[str, dict[str, list[Any]]] = {
            "ema": {
                "confidence_buy": [70, 80, 90],
                "confidence_sell": [10, 20, 30],
            },
            "momentum": {
                "rsi_buy_threshold": [55.0, 60.0, 65.0],
                "rsi_sell_threshold": [35.0, 40.0, 45.0],
            },
            "vwap": {
                "rsi_buy_threshold": [50.0, 55.0, 60.0],
                "rsi_sell_threshold": [40.0, 45.0, 50.0],
            },
            "mean_reversion": {
                "rsi_oversold": [25.0, 30.0, 35.0],
                "rsi_overbought": [65.0, 70.0, 75.0],
            },
            "trend_confluence": {
                "adx_threshold": [20.0, 25.0, 30.0],
            },
            "supertrend_confluence": {
                "adx_threshold": [20.0, 25.0, 30.0],
                "rsi_bull": [50.0, 55.0, 60.0],
                "rsi_bear": [40.0, 45.0, 50.0],
            },
            "momentum_confluence": {
                "rsi_bull": [55.0, 60.0, 65.0],
                "rsi_bear": [35.0, 40.0, 45.0],
            },
        }
        return grids.get(strategy_name, {})

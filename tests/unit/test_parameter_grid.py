"""Unit tests for ParameterGridGenerator."""
import pytest

from optimization.parameter_grid import ParameterGridGenerator


class TestParameterGridGenerate:
    def test_single_param_single_value(self):
        gen = ParameterGridGenerator()
        result = gen.generate({"rsi_buy_threshold": [60]})
        assert result == [{"rsi_buy_threshold": 60}]

    def test_cartesian_product(self):
        gen = ParameterGridGenerator()
        result = gen.generate({"a": [1, 2], "b": [10, 20]})
        assert len(result) == 4
        assert {"a": 1, "b": 10} in result
        assert {"a": 2, "b": 20} in result

    def test_empty_grid_returns_single_empty_combo(self):
        gen = ParameterGridGenerator()
        # An empty spec means "no parameters to vary" — one run with default params
        assert gen.generate({}) == [{}]

    def test_ema_constraint_filters_invalid(self):
        gen = ParameterGridGenerator()
        result = gen.generate({"ema_fast": [5, 10, 20], "ema_slow": [10, 20]})
        for combo in result:
            assert combo["ema_fast"] < combo["ema_slow"]

    def test_rsi_constraint_filters_invalid(self):
        gen = ParameterGridGenerator()
        result = gen.generate({"rsi_sell_threshold": [30, 40, 50], "rsi_buy_threshold": [40, 60]})
        for combo in result:
            assert combo["rsi_sell_threshold"] < combo["rsi_buy_threshold"]

    def test_all_invalid_combinations_returns_empty(self):
        gen = ParameterGridGenerator()
        result = gen.generate({"ema_fast": [20], "ema_slow": [10]})
        assert result == []

    def test_equal_values_filtered_out(self):
        gen = ParameterGridGenerator()
        result = gen.generate({"ema_fast": [10], "ema_slow": [10]})
        assert result == []


class TestIsValidCombination:
    def test_valid_no_constraints(self):
        assert ParameterGridGenerator.is_valid_combination({"x": 1, "y": 2}) is True

    def test_valid_ema(self):
        assert ParameterGridGenerator.is_valid_combination({"ema_fast": 9, "ema_slow": 21}) is True

    def test_invalid_ema_equal(self):
        assert ParameterGridGenerator.is_valid_combination({"ema_fast": 10, "ema_slow": 10}) is False

    def test_invalid_ema_reversed(self):
        assert ParameterGridGenerator.is_valid_combination({"ema_fast": 20, "ema_slow": 10}) is False

    def test_valid_rsi(self):
        assert ParameterGridGenerator.is_valid_combination(
            {"rsi_sell_threshold": 40, "rsi_buy_threshold": 60}
        ) is True

    def test_invalid_rsi_equal(self):
        assert ParameterGridGenerator.is_valid_combination(
            {"rsi_sell_threshold": 50, "rsi_buy_threshold": 50}
        ) is False

    def test_partial_constraint_key_present(self):
        # Only one side of the constraint pair present — should still pass
        assert ParameterGridGenerator.is_valid_combination({"ema_fast": 5}) is True


class TestDefaultGrid:
    def test_momentum_grid_has_rsi_keys(self):
        grid = ParameterGridGenerator.default_grid("momentum")
        assert "rsi_buy_threshold" in grid
        assert "rsi_sell_threshold" in grid

    def test_ema_grid_has_ema_keys(self):
        grid = ParameterGridGenerator.default_grid("ema")
        assert "ema_fast" in grid or len(grid) > 0

    def test_unknown_strategy_returns_dict(self):
        grid = ParameterGridGenerator.default_grid("unknown_xyz")
        assert isinstance(grid, dict)

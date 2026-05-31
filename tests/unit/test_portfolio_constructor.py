"""Unit tests for PortfolioConstructor and AllocationModels."""
from __future__ import annotations

from decimal import Decimal

import pytest

from risk.allocation_models import (
    EqualRiskContributionModel,
    EqualWeightModel,
    InverseVolatilityModel,
    StrategyPerformanceAllocationModel,
    get_allocation_model,
)
from risk.portfolio_constructor import PortfolioConstructor
from risk.portfolio_state import PortfolioStateEngine
from risk.risk_models import AllocationModelType, RiskParams, SignalInput


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _state(cash: str = "1000000") -> PortfolioStateEngine:
    return PortfolioStateEngine(initial_cash=Decimal(cash))


def _params(**kw) -> RiskParams:
    defaults = dict(max_position_pct=50.0)
    defaults.update(kw)
    return RiskParams(**defaults)


def _signal(symbol: str, price: str = "100", action: str = "BUY", strategy: str = "ema") -> SignalInput:
    return SignalInput(
        symbol=symbol,
        strategy_name=strategy,
        action=action,
        confidence=0.8,
        timeframe="5min",
        current_price=Decimal(price),
    )


# ──────────────────────────────────────────────────────────────────────
# EqualWeightModel
# ──────────────────────────────────────────────────────────────────────

class TestEqualWeightModel:
    def test_single_symbol_weight_is_one(self):
        m = EqualWeightModel()
        weights = m.allocate(["A"], ["s1"], {})
        assert abs(weights[0].weight - 1.0) < 1e-9

    def test_two_symbols_equal_weight(self):
        m = EqualWeightModel()
        weights = m.allocate(["A", "B"], ["s1", "s2"], {})
        assert abs(weights[0].weight - 0.5) < 1e-9
        assert abs(weights[1].weight - 0.5) < 1e-9

    def test_n_symbols_sum_to_one(self):
        m = EqualWeightModel()
        syms = [f"S{i}" for i in range(7)]
        weights = m.allocate(syms, syms, {})
        assert abs(sum(w.weight for w in weights) - 1.0) < 1e-9

    def test_empty_input_returns_empty(self):
        m = EqualWeightModel()
        assert m.allocate([], [], {}) == []


# ──────────────────────────────────────────────────────────────────────
# InverseVolatilityModel
# ──────────────────────────────────────────────────────────────────────

class TestInverseVolatilityModel:
    def test_weights_sum_to_one(self):
        m = InverseVolatilityModel()
        weights = m.allocate(["A", "B", "C"], ["s", "s", "s"],
                             {"A": 0.1, "B": 0.2, "C": 0.4})
        assert abs(sum(w.weight for w in weights) - 1.0) < 1e-9

    def test_lower_vol_gets_higher_weight(self):
        m = InverseVolatilityModel()
        weights = m.allocate(["A", "B"], ["s1", "s2"], {"A": 0.1, "B": 0.3})
        w_map = {w.symbol: w.weight for w in weights}
        assert w_map["A"] > w_map["B"]

    def test_equal_vol_gives_equal_weights(self):
        m = InverseVolatilityModel()
        weights = m.allocate(["A", "B"], ["s1", "s2"], {"A": 0.2, "B": 0.2})
        assert abs(weights[0].weight - weights[1].weight) < 1e-9

    def test_zero_vol_falls_back_to_equal(self):
        m = InverseVolatilityModel()
        weights = m.allocate(["A", "B"], ["s", "s"], {"A": 0.0, "B": 0.0})
        assert abs(sum(w.weight for w in weights) - 1.0) < 1e-9


# ──────────────────────────────────────────────────────────────────────
# EqualRiskContributionModel
# ──────────────────────────────────────────────────────────────────────

class TestEqualRiskContributionModel:
    def test_weights_sum_to_one(self):
        m = EqualRiskContributionModel()
        weights = m.allocate(["A", "B", "C"], ["s", "s", "s"],
                             {"A": 0.1, "B": 0.2, "C": 0.4})
        assert abs(sum(w.weight for w in weights) - 1.0) < 1e-6

    def test_equal_vol_gives_equal_weights(self):
        m = EqualRiskContributionModel()
        weights = m.allocate(["A", "B"], ["s1", "s2"], {"A": 0.2, "B": 0.2})
        assert abs(weights[0].weight - weights[1].weight) < 1e-6

    def test_higher_vol_gets_lower_weight(self):
        m = EqualRiskContributionModel()
        weights = m.allocate(["A", "B"], ["s", "s"], {"A": 0.1, "B": 0.4})
        w_map = {w.symbol: w.weight for w in weights}
        assert w_map["A"] > w_map["B"]

    def test_with_cov_matrix(self):
        m = EqualRiskContributionModel(max_iter=100)
        cov = [[0.01, 0.002], [0.002, 0.04]]
        weights = m.allocate(["A", "B"], ["s", "s"], {"A": 0.1, "B": 0.2},
                             cov_matrix=cov)
        assert abs(sum(w.weight for w in weights) - 1.0) < 1e-6

    def test_all_weights_positive(self):
        m = EqualRiskContributionModel()
        weights = m.allocate(["A", "B", "C", "D"], ["s"] * 4,
                             {"A": 0.05, "B": 0.15, "C": 0.25, "D": 0.10})
        assert all(w.weight > 0 for w in weights)


# ──────────────────────────────────────────────────────────────────────
# StrategyPerformanceAllocationModel
# ──────────────────────────────────────────────────────────────────────

class TestStrategyPerformanceAllocation:
    def test_weights_sum_to_one(self):
        m = StrategyPerformanceAllocationModel()
        weights = m.allocate(
            ["A", "B"], ["s1", "s2"], {},
            strategy_scores={"s1": 1.5, "s2": 0.5}
        )
        assert abs(sum(w.weight for w in weights) - 1.0) < 1e-9

    def test_higher_score_gets_higher_weight(self):
        m = StrategyPerformanceAllocationModel()
        weights = m.allocate(
            ["A", "B"], ["s1", "s2"], {},
            strategy_scores={"s1": 3.0, "s2": 1.0}
        )
        w_map = {w.symbol: w.weight for w in weights}
        assert w_map["A"] > w_map["B"]

    def test_negative_scores_clipped_to_zero_falls_back_equal(self):
        m = StrategyPerformanceAllocationModel()
        weights = m.allocate(
            ["A", "B"], ["s1", "s2"], {},
            strategy_scores={"s1": -1.0, "s2": -2.0}
        )
        assert abs(weights[0].weight - 0.5) < 1e-9

    def test_no_scores_falls_back_to_equal(self):
        m = StrategyPerformanceAllocationModel()
        weights = m.allocate(["A", "B", "C"], ["s1", "s2", "s3"], {})
        assert abs(sum(w.weight for w in weights) - 1.0) < 1e-9


# ──────────────────────────────────────────────────────────────────────
# get_allocation_model factory
# ──────────────────────────────────────────────────────────────────────

class TestGetAllocationModelFactory:
    def test_equal_weight(self):
        m = get_allocation_model(AllocationModelType.EQUAL_WEIGHT)
        assert isinstance(m, EqualWeightModel)

    def test_inverse_vol(self):
        m = get_allocation_model(AllocationModelType.INVERSE_VOLATILITY)
        assert isinstance(m, InverseVolatilityModel)

    def test_erc(self):
        m = get_allocation_model(AllocationModelType.EQUAL_RISK)
        assert isinstance(m, EqualRiskContributionModel)

    def test_strategy_performance(self):
        m = get_allocation_model(AllocationModelType.STRATEGY_PERFORMANCE)
        assert isinstance(m, StrategyPerformanceAllocationModel)


# ──────────────────────────────────────────────────────────────────────
# PortfolioConstructor
# ──────────────────────────────────────────────────────────────────────

class TestPortfolioConstructor:
    def test_empty_signals_returns_empty(self):
        pc = PortfolioConstructor()
        result = pc.build_portfolio([], _state(), _params())
        assert result == []

    def test_flat_signals_filtered_out(self):
        pc = PortfolioConstructor()
        signals = [_signal("A", action="FLAT"), _signal("B", action="FLAT")]
        result = pc.build_portfolio(signals, _state(), _params())
        assert result == []

    def test_single_signal_creates_order(self):
        pc = PortfolioConstructor()
        result = pc.build_portfolio([_signal("NIFTY 50", price="100")], _state(), _params())
        assert len(result) == 1

    def test_order_symbol_matches_signal(self):
        pc = PortfolioConstructor()
        result = pc.build_portfolio([_signal("NIFTY BANK", price="100")], _state(), _params())
        assert result[0].symbol == "NIFTY BANK"

    def test_order_action_matches_signal(self):
        pc = PortfolioConstructor()
        result = pc.build_portfolio([_signal("A", action="SELL", price="100")], _state(), _params())
        assert result[0].action == "SELL"

    def test_two_signals_two_orders(self):
        pc = PortfolioConstructor()
        signals = [_signal("A", price="100"), _signal("B", price="200")]
        result = pc.build_portfolio(signals, _state(), _params())
        assert len(result) == 2

    def test_multi_signal_qtys_sum_within_equity(self):
        pc = PortfolioConstructor()
        signals = [_signal("A", price="100"), _signal("B", price="100"), _signal("C", price="100")]
        result = pc.build_portfolio(signals, _state("300000"), _params(max_position_pct=100.0))
        total_notional = sum(Decimal("100") * o.quantity for o in result)
        assert total_notional <= Decimal("300000") * Decimal("1.01")  # 1% rounding tolerance

    def test_allocation_normalised_per_model_equal_weight(self):
        pc = PortfolioConstructor(model_type=AllocationModelType.EQUAL_WEIGHT)
        signals = [_signal("A", price="100"), _signal("B", price="100")]
        result = pc.build_portfolio(signals, _state("200000"), _params(max_position_pct=100.0))
        # Each gets 50% of 200000 = 100000 → qty=1000
        assert result[0].quantity == result[1].quantity

    def test_compute_rebalance_orders_buy_on_underweight(self):
        pc = PortfolioConstructor()
        state = _state("200000")
        from risk.risk_models import AllocationWeight
        targets = [
            AllocationWeight("A", "s", 0.5, AllocationModelType.EQUAL_WEIGHT),
            AllocationWeight("B", "s", 0.5, AllocationModelType.EQUAL_WEIGHT),
        ]
        prices = {"A": Decimal("100"), "B": Decimal("100")}
        orders = pc.compute_rebalance_orders(targets, state, _params(), prices)
        assert all(o.action == "BUY" for o in orders)

    def test_compute_rebalance_sell_on_overweight(self):
        pc = PortfolioConstructor()
        state = _state("200000")
        state.record_fill("A", 1500, Decimal("100"), "s")  # 150000/200000 = 75%
        state.update_price("A", Decimal("100"))
        from risk.risk_models import AllocationWeight
        targets = [AllocationWeight("A", "s", 0.5, AllocationModelType.EQUAL_WEIGHT)]
        prices = {"A": Decimal("100")}
        orders = pc.compute_rebalance_orders(targets, state, _params(), prices)
        sell_orders = [o for o in orders if o.action == "SELL"]
        assert len(sell_orders) >= 1

    def test_build_single_returns_order(self):
        pc = PortfolioConstructor()
        order = pc.build_single(_signal("A", price="100"), _state(), _params(), capital_fraction=0.1)
        assert order is not None
        assert order.quantity == 1000  # 10% of 1e6 / 100

    def test_build_single_zero_fraction_returns_none(self):
        pc = PortfolioConstructor()
        order = pc.build_single(_signal("A", price="100"), _state(), _params(), capital_fraction=0.0)
        assert order is None

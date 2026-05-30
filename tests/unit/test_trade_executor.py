from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from backtesting.backtest_models import BacktestConfig, TradeSide
from backtesting.trade_executor import TradeExecutor


def _config(**kwargs) -> BacktestConfig:
    defaults = dict(
        instrument="NIFTY 50",
        timeframe="1day",
        start_date=datetime(2023, 1, 1),
        end_date=datetime(2024, 1, 1),
        starting_capital=Decimal("1000000"),
        strategy_name="signal",
        commission_pct=Decimal("0.0003"),
        slippage_pct=Decimal("0.0005"),
        position_size_pct=Decimal("0.10"),
    )
    defaults.update(kwargs)
    return BacktestConfig(**defaults)


@pytest.fixture
def executor():
    return TradeExecutor(_config())


_NOW = datetime(2023, 6, 15, 10, 0, 0)
_PRICE = Decimal("18000")


class TestOpenLong:
    def test_entry_price_includes_slippage(self, executor):
        pos = executor.open_long("NIFTY 50", _PRICE, _NOW, Decimal("1000000"))
        expected_entry = _PRICE * (1 + Decimal("0.0005"))
        assert pos.average_price == expected_entry

    def test_quantity_calculated_from_position_size(self, executor):
        # capital=1_000_000, position_size=10% → 100_000 / entry_price
        pos = executor.open_long("NIFTY 50", _PRICE, _NOW, Decimal("1000000"))
        entry_price = _PRICE * (1 + Decimal("0.0005"))
        expected_qty = int(Decimal("100000") / entry_price)
        assert pos.quantity == expected_qty

    def test_commission_charged_on_actual_value(self, executor):
        pos = executor.open_long("NIFTY 50", _PRICE, _NOW, Decimal("1000000"))
        entry_price = _PRICE * (1 + Decimal("0.0005"))
        expected_commission = entry_price * pos.quantity * Decimal("0.0003")
        assert pos.entry_commission == pytest.approx(float(expected_commission), rel=1e-6)

    def test_slippage_cost_computed_separately(self, executor):
        pos = executor.open_long("NIFTY 50", _PRICE, _NOW, Decimal("1000000"))
        expected_slippage = _PRICE * pos.quantity * Decimal("0.0005")
        assert pos.entry_slippage == pytest.approx(float(expected_slippage), rel=1e-6)

    def test_returns_none_when_capital_too_small(self, executor):
        # price 18000, position_size 10% of 100 capital → qty < 1
        pos = executor.open_long("NIFTY 50", _PRICE, _NOW, Decimal("100"))
        assert pos is None

    def test_instrument_set_correctly(self, executor):
        pos = executor.open_long("NIFTY 50", _PRICE, _NOW, Decimal("1000000"))
        assert pos.instrument == "NIFTY 50"

    def test_entry_time_set_correctly(self, executor):
        pos = executor.open_long("NIFTY 50", _PRICE, _NOW, Decimal("1000000"))
        assert pos.entry_time == _NOW

    def test_side_is_long(self, executor):
        pos = executor.open_long("NIFTY 50", _PRICE, _NOW, Decimal("1000000"))
        assert pos.side == TradeSide.LONG


class TestCloseLong:
    def _open_position(self, executor):
        return executor.open_long("NIFTY 50", _PRICE, _NOW, Decimal("1000000"))

    def test_exit_price_adverse_fill(self, executor):
        pos = self._open_position(executor)
        exit_market = Decimal("19000")
        exit_time = datetime(2023, 7, 1)
        trade = executor.close_long(pos, exit_market, exit_time)
        expected_exit = exit_market * (1 - Decimal("0.0005"))
        assert trade.exit_price == expected_exit

    def test_winning_trade_when_price_rises(self, executor):
        pos = self._open_position(executor)
        trade = executor.close_long(pos, Decimal("20000"), datetime(2023, 7, 1))
        assert trade.is_winner is True

    def test_losing_trade_when_price_falls(self, executor):
        pos = self._open_position(executor)
        trade = executor.close_long(pos, Decimal("15000"), datetime(2023, 7, 1))
        assert trade.is_winner is False

    def test_holding_minutes_calculated(self, executor):
        pos = self._open_position(executor)
        exit_time = datetime(2023, 6, 16, 10, 0, 0)  # exactly 1440 min later
        trade = executor.close_long(pos, _PRICE, exit_time)
        assert trade.holding_minutes == 1440

    def test_gross_pnl_before_costs(self, executor):
        pos = self._open_position(executor)
        exit_market = Decimal("20000")
        trade = executor.close_long(pos, exit_market, datetime(2023, 7, 1))
        exit_price = exit_market * (1 - Decimal("0.0005"))
        expected_gross = (exit_price - pos.average_price) * pos.quantity
        assert trade.gross_pnl == pytest.approx(float(expected_gross), rel=1e-5)

    def test_net_pnl_deducts_all_costs(self, executor):
        pos = self._open_position(executor)
        exit_market = Decimal("19000")
        trade = executor.close_long(pos, exit_market, datetime(2023, 7, 1))
        total_commission = trade.commission
        total_slippage = trade.slippage
        assert trade.net_pnl == pytest.approx(
            float(trade.gross_pnl - total_commission - total_slippage), rel=1e-5
        )

    def test_return_pct_positive_for_winner(self, executor):
        pos = self._open_position(executor)
        trade = executor.close_long(pos, Decimal("20000"), datetime(2023, 7, 1))
        assert float(trade.return_pct) > 0

    def test_exit_time_set_correctly(self, executor):
        pos = self._open_position(executor)
        exit_time = datetime(2023, 8, 1)
        trade = executor.close_long(pos, _PRICE, exit_time)
        assert trade.exit_time == exit_time


class TestTotalEntryCost:
    def test_returns_cost_exceeding_capital_for_tiny_capital(self, executor):
        cost = executor.total_entry_cost(_PRICE, Decimal("100"))
        assert cost > Decimal("100")

    def test_returns_reasonable_cost_for_adequate_capital(self, executor):
        cost = executor.total_entry_cost(_PRICE, Decimal("1000000"))
        assert cost < Decimal("1000000")
        assert cost > Decimal("0")

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from backtesting.backtest_models import (
    BacktestConfig,
    OpenPosition,
    TradeSide,
)
from backtesting.portfolio import Portfolio
from backtesting.trade_executor import TradeExecutor


_CAPITAL = Decimal("1000000")
_INSTR = "NIFTY 50"
_PRICE = Decimal("18000")
_NOW = datetime(2023, 6, 15, 10, 0, 0)


def _config() -> BacktestConfig:
    return BacktestConfig(
        instrument=_INSTR,
        timeframe="1day",
        start_date=datetime(2023, 1, 1),
        end_date=datetime(2024, 1, 1),
        starting_capital=_CAPITAL,
        strategy_name="signal",
        commission_pct=Decimal("0.0003"),
        slippage_pct=Decimal("0.0005"),
        position_size_pct=Decimal("0.10"),
    )


def _make_position(price: Decimal = _PRICE, qty: int = 5) -> OpenPosition:
    return OpenPosition(
        trade_id="test-id",
        instrument=_INSTR,
        quantity=qty,
        average_price=price,
        entry_time=_NOW,
        side=TradeSide.LONG,
        entry_commission=price * qty * Decimal("0.0003"),
        entry_slippage=price * qty * Decimal("0.0005"),
    )


@pytest.fixture
def portfolio():
    return Portfolio(_CAPITAL)


@pytest.fixture
def executor():
    return TradeExecutor(_config())


class TestInitialState:
    def test_cash_equals_starting_capital(self, portfolio):
        assert portfolio.cash == _CAPITAL

    def test_equity_equals_starting_capital(self, portfolio):
        assert portfolio.equity == _CAPITAL

    def test_no_open_position(self, portfolio):
        assert portfolio.has_open_position is False

    def test_drawdown_is_zero(self, portfolio):
        assert portfolio.drawdown_pct == Decimal("0")

    def test_closed_trades_empty(self, portfolio):
        assert portfolio.closed_trades == []

    def test_equity_curve_empty(self, portfolio):
        assert portfolio.equity_curve == []


class TestEnterPosition:
    def test_cash_reduced_after_entry(self, portfolio):
        pos = _make_position()
        cash_before = portfolio.cash
        portfolio.enter_position(pos)
        cash_cost = pos.average_price * pos.quantity + pos.entry_commission + pos.entry_slippage
        assert portfolio.cash == cash_before - cash_cost

    def test_has_open_position_after_entry(self, portfolio):
        portfolio.enter_position(_make_position())
        assert portfolio.has_open_position is True

    def test_current_position_returns_entered_position(self, portfolio):
        pos = _make_position()
        portfolio.enter_position(pos)
        assert portfolio.current_position is pos

    def test_raises_on_insufficient_cash(self, portfolio):
        huge_pos = _make_position(qty=100000)
        with pytest.raises(ValueError, match="Insufficient cash"):
            portfolio.enter_position(huge_pos)


class TestExitPosition:
    def _enter_then_exit(self, portfolio, executor, exit_price=Decimal("19000")):
        pos = executor.open_long(_INSTR, _PRICE, _NOW, _CAPITAL)
        portfolio.enter_position(pos)
        trade = executor.close_long(pos, exit_price, datetime(2023, 7, 1))
        portfolio.exit_position(trade)
        return trade

    def test_no_open_position_after_exit(self, portfolio, executor):
        self._enter_then_exit(portfolio, executor)
        assert portfolio.has_open_position is False

    def test_trade_added_to_closed_trades(self, portfolio, executor):
        trade = self._enter_then_exit(portfolio, executor)
        assert trade in portfolio.closed_trades

    def test_realized_pnl_updated(self, portfolio, executor):
        trade = self._enter_then_exit(portfolio, executor)
        assert portfolio.realized_pnl == trade.net_pnl

    def test_cash_increased_by_exit_proceeds(self, portfolio, executor):
        pos = executor.open_long(_INSTR, _PRICE, _NOW, _CAPITAL)
        portfolio.enter_position(pos)
        cash_after_entry = portfolio.cash
        exit_price = Decimal("19000")
        trade = executor.close_long(pos, exit_price, datetime(2023, 7, 1))
        portfolio.exit_position(trade)
        exit_proceeds = (
            trade.exit_price * trade.quantity
            - trade.exit_commission
            - trade.exit_slippage
        )
        assert portfolio.cash == pytest.approx(
            float(cash_after_entry + exit_proceeds), rel=1e-8
        )

    def test_raises_if_no_open_position(self, portfolio, executor):
        pos = executor.open_long(_INSTR, _PRICE, _NOW, _CAPITAL)
        portfolio.enter_position(pos)
        trade = executor.close_long(pos, Decimal("19000"), datetime(2023, 7, 1))
        portfolio.exit_position(trade)
        with pytest.raises(ValueError):
            portfolio.exit_position(trade)


class TestMarkToMarket:
    def test_equity_equals_cash_plus_market_value(self, portfolio, executor):
        pos = executor.open_long(_INSTR, _PRICE, _NOW, _CAPITAL)
        portfolio.enter_position(pos)
        new_price = Decimal("20000")
        portfolio.mark_to_market({_INSTR: new_price})
        expected_equity = portfolio.cash + new_price * pos.quantity
        assert portfolio.equity == pytest.approx(float(expected_equity), rel=1e-8)

    def test_unrealized_pnl_reflects_price_change(self, portfolio, executor):
        pos = executor.open_long(_INSTR, _PRICE, _NOW, _CAPITAL)
        portfolio.enter_position(pos)
        new_price = pos.average_price * Decimal("1.1")
        portfolio.mark_to_market({_INSTR: new_price})
        expected_unrealized = (new_price - pos.average_price) * pos.quantity
        assert float(portfolio.unrealized_pnl) == pytest.approx(
            float(expected_unrealized), rel=1e-6
        )

    def test_peak_equity_updated_on_gain(self, portfolio, executor):
        pos = executor.open_long(_INSTR, _PRICE, _NOW, _CAPITAL)
        portfolio.enter_position(pos)
        portfolio.mark_to_market({_INSTR: Decimal("25000")})
        assert portfolio.drawdown_pct == Decimal("0")

    def test_drawdown_positive_after_loss(self, portfolio, executor):
        pos = executor.open_long(_INSTR, _PRICE, _NOW, _CAPITAL)
        portfolio.enter_position(pos)
        portfolio.mark_to_market({_INSTR: Decimal("20000")})  # peak set
        portfolio.mark_to_market({_INSTR: Decimal("15000")})  # price drops
        assert portfolio.drawdown_pct > Decimal("0")


class TestSnapshot:
    def test_snapshot_appended_to_equity_curve(self, portfolio):
        portfolio.snapshot(_NOW)
        assert len(portfolio.equity_curve) == 1

    def test_snapshot_time_set_correctly(self, portfolio):
        ep = portfolio.snapshot(_NOW)
        assert ep.snapshot_time == _NOW

    def test_snapshot_equity_equals_current_equity(self, portfolio):
        ep = portfolio.snapshot(_NOW)
        assert ep.equity == portfolio.equity

    def test_multiple_snapshots_accumulate(self, portfolio):
        for i in range(5):
            portfolio.snapshot(datetime(2023, 1, i + 1))
        assert len(portfolio.equity_curve) == 5


class TestForceCloseAll:
    def test_force_close_returns_trades(self, portfolio, executor):
        pos = executor.open_long(_INSTR, _PRICE, _NOW, _CAPITAL)
        portfolio.enter_position(pos)
        trades = portfolio.force_close_all(
            {_INSTR: Decimal("19000")}, datetime(2023, 12, 31), executor
        )
        assert len(trades) == 1

    def test_no_open_positions_after_force_close(self, portfolio, executor):
        pos = executor.open_long(_INSTR, _PRICE, _NOW, _CAPITAL)
        portfolio.enter_position(pos)
        portfolio.force_close_all(
            {_INSTR: Decimal("19000")}, datetime(2023, 12, 31), executor
        )
        assert portfolio.has_open_position is False

    def test_force_close_empty_portfolio(self, portfolio, executor):
        trades = portfolio.force_close_all({}, datetime(2023, 12, 31), executor)
        assert trades == []

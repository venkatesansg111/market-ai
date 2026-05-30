from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, PropertyMock

import pytest

from backtesting.backtest_models import BacktestConfig, TradeSide
from backtesting.risk_engine import RiskEngine


def _config(**kwargs) -> BacktestConfig:
    defaults = dict(
        instrument="NIFTY 50",
        timeframe="1day",
        start_date=datetime(2023, 1, 1),
        end_date=datetime(2024, 1, 1),
        starting_capital=Decimal("1000000"),
        strategy_name="signal",
        max_open_trades=1,
        max_drawdown_pct=Decimal("0.15"),
        max_daily_loss_pct=Decimal("0.02"),
    )
    defaults.update(kwargs)
    return BacktestConfig(**defaults)


def _mock_portfolio(
    n_open: int = 0,
    drawdown_pct: float = 0.0,
    cash: float = 1_000_000.0,
    equity: float = 1_000_000.0,
) -> MagicMock:
    p = MagicMock()
    type(p).open_positions = PropertyMock(
        return_value={f"pos{i}": MagicMock() for i in range(n_open)}
    )
    type(p).drawdown_pct = PropertyMock(return_value=Decimal(str(drawdown_pct)))
    type(p).cash = PropertyMock(return_value=Decimal(str(cash)))
    type(p).equity = PropertyMock(return_value=Decimal(str(equity)))
    return p


_CANDLE_TIME = datetime(2023, 6, 15, 10, 0, 0)
_CASH_REQ = Decimal("95000")


class TestCanOpenTrade:
    def test_allows_trade_under_all_conditions(self):
        risk = RiskEngine(_config())
        portfolio = _mock_portfolio(n_open=0, drawdown_pct=0.0, cash=1_000_000, equity=1_000_000)
        ok, reason = risk.can_open_trade(portfolio, _CANDLE_TIME, _CASH_REQ)
        assert ok is True
        assert reason == ""

    def test_blocks_when_max_open_trades_reached(self):
        risk = RiskEngine(_config(max_open_trades=1))
        portfolio = _mock_portfolio(n_open=1)
        ok, reason = risk.can_open_trade(portfolio, _CANDLE_TIME, _CASH_REQ)
        assert ok is False
        assert "max_open_trades" in reason

    def test_blocks_when_drawdown_exceeds_limit(self):
        risk = RiskEngine(_config(max_drawdown_pct=Decimal("0.15")))
        # drawdown 16% > 15% limit (limit stored as Decimal → multiplied by 100 internally)
        portfolio = _mock_portfolio(n_open=0, drawdown_pct=16.0, equity=840_000)
        ok, reason = risk.can_open_trade(portfolio, _CANDLE_TIME, _CASH_REQ)
        assert ok is False
        assert "max_drawdown" in reason

    def test_blocks_when_insufficient_cash(self):
        risk = RiskEngine(_config())
        portfolio = _mock_portfolio(n_open=0, cash=1000, equity=1000)
        ok, reason = risk.can_open_trade(portfolio, _CANDLE_TIME, Decimal("50000"))
        assert ok is False
        assert "insufficient cash" in reason

    def test_blocks_when_daily_loss_exceeded(self):
        risk = RiskEngine(_config(max_daily_loss_pct=Decimal("0.02")))
        # equity=1_000_000, max_daily_loss = 2% = 20_000
        portfolio = _mock_portfolio(n_open=0, cash=1_000_000, equity=1_000_000)

        # Record a trade loss of -25_000 on the same day
        trade = MagicMock()
        trade.exit_time = _CANDLE_TIME
        trade.net_pnl = Decimal("-25000")
        risk.record_trade_pnl(trade)

        ok, reason = risk.can_open_trade(portfolio, _CANDLE_TIME, _CASH_REQ)
        assert ok is False
        assert "max_daily_loss" in reason

    def test_allows_trade_after_daily_loss_on_different_day(self):
        risk = RiskEngine(_config(max_daily_loss_pct=Decimal("0.02")))
        portfolio = _mock_portfolio(n_open=0, cash=1_000_000, equity=1_000_000)

        # Loss recorded on a different day
        trade = MagicMock()
        trade.exit_time = datetime(2023, 6, 10)
        trade.net_pnl = Decimal("-25000")
        risk.record_trade_pnl(trade)

        ok, _ = risk.can_open_trade(portfolio, _CANDLE_TIME, _CASH_REQ)
        assert ok is True


class TestCanContinueTrading:
    def test_allows_when_drawdown_below_limit(self):
        risk = RiskEngine(_config(max_drawdown_pct=Decimal("0.15")))
        portfolio = _mock_portfolio(drawdown_pct=10.0)
        ok, _ = risk.can_continue_trading(portfolio)
        assert ok is True

    def test_blocks_when_drawdown_at_limit(self):
        risk = RiskEngine(_config(max_drawdown_pct=Decimal("0.15")))
        portfolio = _mock_portfolio(drawdown_pct=15.0)
        ok, reason = risk.can_continue_trading(portfolio)
        assert ok is False
        assert "max_drawdown" in reason

    def test_blocks_when_drawdown_exceeds_limit(self):
        risk = RiskEngine(_config(max_drawdown_pct=Decimal("0.15")))
        portfolio = _mock_portfolio(drawdown_pct=20.0)
        ok, _ = risk.can_continue_trading(portfolio)
        assert ok is False


class TestRecordTradePnl:
    def test_daily_pnl_accumulates(self):
        risk = RiskEngine(_config())
        t1 = MagicMock()
        t1.exit_time = datetime(2023, 6, 15)
        t1.net_pnl = Decimal("1000")
        t2 = MagicMock()
        t2.exit_time = datetime(2023, 6, 15)
        t2.net_pnl = Decimal("-500")
        risk.record_trade_pnl(t1)
        risk.record_trade_pnl(t2)
        summary = risk.daily_pnl_summary()
        assert summary["2023-06-15"] == pytest.approx(500.0)

    def test_separate_days_tracked_independently(self):
        risk = RiskEngine(_config())
        t1 = MagicMock()
        t1.exit_time = datetime(2023, 6, 15)
        t1.net_pnl = Decimal("1000")
        t2 = MagicMock()
        t2.exit_time = datetime(2023, 6, 16)
        t2.net_pnl = Decimal("-300")
        risk.record_trade_pnl(t1)
        risk.record_trade_pnl(t2)
        summary = risk.daily_pnl_summary()
        assert len(summary) == 2

    def test_reset_clears_daily_tracking(self):
        risk = RiskEngine(_config())
        t = MagicMock()
        t.exit_time = datetime(2023, 6, 15)
        t.net_pnl = Decimal("5000")
        risk.record_trade_pnl(t)
        risk.reset_daily_tracking()
        assert risk.daily_pnl_summary() == {}

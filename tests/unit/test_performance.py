from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from backtesting.backtest_models import (
    BacktestConfig,
    EquityPoint,
    Trade,
    TradeSide,
)
from backtesting.performance import PerformanceEngine


def _config(start: datetime = datetime(2022, 1, 1), end: datetime = datetime(2023, 1, 1)) -> BacktestConfig:
    return BacktestConfig(
        instrument="NIFTY 50",
        timeframe="1day",
        start_date=start,
        end_date=end,
        starting_capital=Decimal("1000000"),
        strategy_name="signal",
    )


def _trade(
    entry_price: float,
    exit_price: float,
    qty: int = 5,
    entry_time: datetime = datetime(2022, 3, 1),
    exit_time: datetime = datetime(2022, 3, 31),
    commission_pct: float = 0.0003,
    slippage_pct: float = 0.0005,
) -> Trade:
    ep = Decimal(str(entry_price))
    xp = Decimal(str(exit_price))
    q = qty
    entry_comm = ep * q * Decimal(str(commission_pct))
    exit_comm = xp * q * Decimal(str(commission_pct))
    entry_slip = ep * q * Decimal(str(slippage_pct))
    exit_slip = xp * q * Decimal(str(slippage_pct))
    return Trade(
        trade_id="t1",
        instrument="NIFTY 50",
        entry_time=entry_time,
        exit_time=exit_time,
        entry_price=ep,
        exit_price=xp,
        quantity=q,
        side=TradeSide.LONG,
        entry_commission=entry_comm,
        exit_commission=exit_comm,
        entry_slippage=entry_slip,
        exit_slippage=exit_slip,
    )


def _equity_curve(values: list[tuple[datetime, float]]) -> list[EquityPoint]:
    curve = []
    for t, eq in values:
        curve.append(EquityPoint(
            snapshot_time=t,
            cash=Decimal(str(eq)),
            equity=Decimal(str(eq)),
            unrealized_pnl=Decimal("0"),
            realized_pnl=Decimal("0"),
            drawdown_pct=Decimal("0"),
        ))
    return curve


@pytest.fixture
def engine():
    return PerformanceEngine()


# ──────────────────────────────────────────────────────────────────────
# Total return
# ──────────────────────────────────────────────────────────────────────

class TestTotalReturn:
    def test_positive_return(self, engine):
        config = _config()
        eq_curve = _equity_curve([
            (datetime(2022, 1, 3), 1_000_000),
            (datetime(2022, 12, 30), 1_200_000),
        ])
        result = engine.compute(config, [], eq_curve, "test")
        assert float(result.total_return_pct) == pytest.approx(20.0, rel=1e-3)

    def test_negative_return(self, engine):
        config = _config()
        eq_curve = _equity_curve([
            (datetime(2022, 1, 3), 1_000_000),
            (datetime(2022, 12, 30), 800_000),
        ])
        result = engine.compute(config, [], eq_curve, "test")
        assert float(result.total_return_pct) == pytest.approx(-20.0, rel=1e-3)

    def test_zero_return_on_flat_curve(self, engine):
        config = _config()
        eq_curve = _equity_curve([
            (datetime(2022, 1, 3), 1_000_000),
            (datetime(2022, 12, 30), 1_000_000),
        ])
        result = engine.compute(config, [], eq_curve, "test")
        assert float(result.total_return_pct) == pytest.approx(0.0, abs=1e-3)


# ──────────────────────────────────────────────────────────────────────
# Win rate and trade stats
# ──────────────────────────────────────────────────────────────────────

class TestTradeStats:
    def test_win_rate_50_percent_with_equal_wins_losses(self, engine):
        config = _config()
        trades = [
            _trade(18000, 19000, entry_time=datetime(2022, 2, 1), exit_time=datetime(2022, 2, 15)),
            _trade(19000, 18000, entry_time=datetime(2022, 3, 1), exit_time=datetime(2022, 3, 15)),
        ]
        eq_curve = _equity_curve([(datetime(2022, 1, 3), 1_000_000), (datetime(2022, 12, 30), 1_000_000)])
        result = engine.compute(config, trades, eq_curve, "test")
        assert float(result.win_rate_pct) == pytest.approx(50.0, rel=1e-2)

    def test_total_trades_count(self, engine):
        config = _config()
        trades = [
            _trade(18000, 19000, entry_time=datetime(2022, 2, 1), exit_time=datetime(2022, 2, 15)),
            _trade(19000, 20000, entry_time=datetime(2022, 3, 1), exit_time=datetime(2022, 3, 15)),
            _trade(20000, 19000, entry_time=datetime(2022, 4, 1), exit_time=datetime(2022, 4, 15)),
        ]
        eq_curve = _equity_curve([(datetime(2022, 1, 3), 1_000_000), (datetime(2022, 12, 30), 1_000_000)])
        result = engine.compute(config, trades, eq_curve, "test")
        assert result.total_trades == 3
        assert result.winning_trades == 2
        assert result.losing_trades == 1

    def test_no_trades_returns_zero_stats(self, engine):
        config = _config()
        eq_curve = _equity_curve([(datetime(2022, 1, 3), 1_000_000)])
        result = engine.compute(config, [], eq_curve, "test")
        assert result.total_trades == 0
        assert float(result.win_rate_pct) == 0.0
        assert float(result.profit_factor) == 0.0


# ──────────────────────────────────────────────────────────────────────
# Streaks
# ──────────────────────────────────────────────────────────────────────

class TestStreaks:
    def test_win_streak_detected(self, engine):
        config = _config()
        trades = [
            _trade(17000, 18000, entry_time=datetime(2022, 2, 1), exit_time=datetime(2022, 2, 10)),
            _trade(18000, 19000, entry_time=datetime(2022, 2, 11), exit_time=datetime(2022, 2, 20)),
            _trade(19000, 20000, entry_time=datetime(2022, 2, 21), exit_time=datetime(2022, 3, 1)),
            _trade(20000, 19000, entry_time=datetime(2022, 3, 2), exit_time=datetime(2022, 3, 10)),
        ]
        eq_curve = _equity_curve([(datetime(2022, 1, 3), 1_000_000), (datetime(2022, 12, 30), 1_000_000)])
        result = engine.compute(config, trades, eq_curve, "test")
        assert result.longest_win_streak == 3
        assert result.longest_loss_streak == 1

    def test_loss_streak_detected(self, engine):
        config = _config()
        trades = [
            _trade(18000, 17000, entry_time=datetime(2022, 2, 1), exit_time=datetime(2022, 2, 10)),
            _trade(17000, 16000, entry_time=datetime(2022, 2, 11), exit_time=datetime(2022, 2, 20)),
            _trade(16000, 17000, entry_time=datetime(2022, 2, 21), exit_time=datetime(2022, 3, 1)),
        ]
        eq_curve = _equity_curve([(datetime(2022, 1, 3), 1_000_000), (datetime(2022, 12, 30), 1_000_000)])
        result = engine.compute(config, trades, eq_curve, "test")
        assert result.longest_loss_streak == 2
        assert result.longest_win_streak == 1


# ──────────────────────────────────────────────────────────────────────
# Max drawdown
# ──────────────────────────────────────────────────────────────────────

class TestMaxDrawdown:
    def test_no_drawdown_on_rising_curve(self, engine):
        config = _config()
        eq_curve = _equity_curve([
            (datetime(2022, 1, 3), 1_000_000),
            (datetime(2022, 6, 30), 1_100_000),
            (datetime(2022, 12, 30), 1_200_000),
        ])
        result = engine.compute(config, [], eq_curve, "test")
        assert float(result.max_drawdown_pct) == pytest.approx(0.0, abs=0.001)

    def test_drawdown_calculated_correctly(self, engine):
        config = _config()
        # Peak 1_200_000, then drops to 960_000 → 20% drawdown
        eq_curve = _equity_curve([
            (datetime(2022, 1, 3), 1_000_000),
            (datetime(2022, 6, 30), 1_200_000),
            (datetime(2022, 12, 30), 960_000),
        ])
        result = engine.compute(config, [], eq_curve, "test")
        assert float(result.max_drawdown_pct) == pytest.approx(20.0, rel=0.01)


# ──────────────────────────────────────────────────────────────────────
# Monthly / yearly returns
# ──────────────────────────────────────────────────────────────────────

class TestPeriodReturns:
    def test_monthly_returns_populated(self, engine):
        config = _config()
        eq_curve = _equity_curve([
            (datetime(2022, 1, 3), 1_000_000),
            (datetime(2022, 1, 31), 1_010_000),
            (datetime(2022, 2, 28), 1_020_000),
        ])
        result = engine.compute(config, [], eq_curve, "test")
        assert len(result.monthly_returns) >= 1

    def test_yearly_returns_populated(self, engine):
        config = _config()
        eq_curve = _equity_curve([
            (datetime(2022, 1, 3), 1_000_000),
            (datetime(2022, 12, 30), 1_150_000),
        ])
        result = engine.compute(config, [], eq_curve, "test")
        assert "2022" in result.yearly_returns
        assert result.yearly_returns["2022"] == pytest.approx(15.0, rel=0.01)


# ──────────────────────────────────────────────────────────────────────
# Ratios — directional checks (exact values depend on equity curve shape)
# ──────────────────────────────────────────────────────────────────────

class TestRatios:
    def _trending_curve(self) -> list[EquityPoint]:
        import random
        random.seed(42)
        eq = 1_000_000.0
        curve = []
        for day in range(252):
            eq *= 1 + random.gauss(0.0004, 0.01)
            t = datetime(2022, 1, 1).replace(day=1) if day == 0 else datetime(2022, 1, 1)
            from datetime import timedelta
            t = datetime(2022, 1, 3) + timedelta(days=day)
            curve.append(EquityPoint(
                snapshot_time=t,
                cash=Decimal(str(round(eq, 2))),
                equity=Decimal(str(round(eq, 2))),
                unrealized_pnl=Decimal("0"),
                realized_pnl=Decimal("0"),
                drawdown_pct=Decimal("0"),
            ))
        return curve

    def test_sharpe_is_decimal(self, engine):
        config = _config()
        result = engine.compute(config, [], self._trending_curve(), "test")
        assert isinstance(result.sharpe_ratio, Decimal)

    def test_sortino_is_decimal(self, engine):
        config = _config()
        result = engine.compute(config, [], self._trending_curve(), "test")
        assert isinstance(result.sortino_ratio, Decimal)

    def test_profit_factor_positive_with_winners(self, engine):
        config = _config()
        trades = [
            _trade(18000, 20000, entry_time=datetime(2022, 2, 1), exit_time=datetime(2022, 2, 20)),
            _trade(20000, 21000, entry_time=datetime(2022, 3, 1), exit_time=datetime(2022, 3, 20)),
        ]
        eq_curve = _equity_curve([(datetime(2022, 1, 3), 1_000_000), (datetime(2022, 12, 30), 1_100_000)])
        result = engine.compute(config, trades, eq_curve, "test")
        assert float(result.profit_factor) > 0

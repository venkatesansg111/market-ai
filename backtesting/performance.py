from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

import numpy as np
import pandas as pd

from backtesting.backtest_models import (
    BacktestConfig,
    BacktestResult,
    EquityPoint,
    Trade,
)
from utils.logger import get_logger
from config import settings

logger = get_logger(__name__, settings.log_dir, settings.log_level)

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")
_ANNUALIZATION_FACTOR = 252  # trading days per year (NSE)
_RISK_FREE_RATE = 0.065      # 6.5% annual risk-free rate (India 10yr G-Sec proxy)
_DAILY_RF = _RISK_FREE_RATE / _ANNUALIZATION_FACTOR


def _d(v: float | int, prec: str = "0.0001") -> Decimal:
    """Convert float to Decimal with rounding."""
    if math.isnan(v) or math.isinf(v):
        return _ZERO
    return Decimal(str(round(v, 6))).quantize(Decimal(prec), rounding=ROUND_HALF_UP)


class PerformanceEngine:
    """Computes institutional-quality performance metrics from backtest output.

    All monetary results returned as Decimal.
    Statistical ratios use numpy/pandas float64 internally then convert.
    """

    def compute(
        self,
        config: BacktestConfig,
        trades: list[Trade],
        equity_curve: list[EquityPoint],
        run_name: str,
    ) -> BacktestResult:
        """Build the complete BacktestResult from trades and equity curve."""
        starting = config.starting_capital
        ending = equity_curve[-1].equity if equity_curve else starting

        total_return_pct = self._total_return(starting, ending)
        cagr_pct = self._cagr(starting, ending, config.start_date, config.end_date)
        max_dd = self._max_drawdown(equity_curve)
        sharpe = self._sharpe(equity_curve)
        sortino = self._sortino(equity_curve)
        calmar = _d(float(cagr_pct) / float(max_dd)) if max_dd > _ZERO else _ZERO
        recovery = _d(float(total_return_pct) / float(max_dd)) if max_dd > _ZERO else _ZERO

        winners = [t for t in trades if t.is_winner]
        losers = [t for t in trades if not t.is_winner]

        win_rate = _d(len(winners) / len(trades) * 100) if trades else _ZERO
        avg_winner = _d(float(sum(t.net_pnl for t in winners)) / len(winners)) if winners else _ZERO
        avg_loser = _d(float(sum(t.net_pnl for t in losers)) / len(losers)) if losers else _ZERO

        profit_factor = self._profit_factor(winners, losers)
        expectancy = self._expectancy(win_rate, avg_winner, avg_loser)

        avg_hold = _d(sum(t.holding_minutes for t in trades) / len(trades)) if trades else _ZERO
        win_streak, loss_streak = self._streaks(trades)

        monthly = self._monthly_returns(equity_curve)
        yearly = self._yearly_returns(equity_curve)

        return BacktestResult(
            run_name=run_name,
            strategy_name=config.strategy_name,
            instrument=config.instrument,
            timeframe=config.timeframe,
            start_date=config.start_date,
            end_date=config.end_date,
            starting_capital=starting,
            ending_capital=ending,
            total_return_pct=total_return_pct,
            cagr_pct=cagr_pct,
            win_rate_pct=win_rate,
            profit_factor=profit_factor,
            max_drawdown_pct=max_dd,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            expectancy=expectancy,
            total_trades=len(trades),
            winning_trades=len(winners),
            losing_trades=len(losers),
            avg_winner=avg_winner,
            avg_loser=avg_loser,
            avg_holding_minutes=avg_hold,
            longest_win_streak=win_streak,
            longest_loss_streak=loss_streak,
            recovery_factor=recovery,
            equity_curve=equity_curve,
            trades=trades,
            monthly_returns=monthly,
            yearly_returns=yearly,
        )

    # ------------------------------------------------------------------
    # Individual metric calculations
    # ------------------------------------------------------------------

    @staticmethod
    def _total_return(starting: Decimal, ending: Decimal) -> Decimal:
        if starting == _ZERO:
            return _ZERO
        return ((ending - starting) / starting * _HUNDRED).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )

    @staticmethod
    def _cagr(
        starting: Decimal,
        ending: Decimal,
        start_date: datetime,
        end_date: datetime,
    ) -> Decimal:
        years = (end_date - start_date).days / 365.25
        if years <= 0 or starting <= _ZERO:
            return _ZERO
        ratio = float(ending) / float(starting)
        if ratio <= 0:
            return _ZERO
        cagr = (ratio ** (1.0 / years) - 1.0) * 100.0
        return _d(cagr, "0.0001")

    @staticmethod
    def _max_drawdown(equity_curve: list[EquityPoint]) -> Decimal:
        if not equity_curve:
            return _ZERO
        equities = np.array([float(ep.equity) for ep in equity_curve])
        peak = np.maximum.accumulate(equities)
        dd = (peak - equities) / np.where(peak > 0, peak, 1) * 100
        return _d(float(dd.max()), "0.0001")

    @staticmethod
    def _daily_returns(equity_curve: list[EquityPoint]) -> np.ndarray:
        """Convert equity curve to daily percentage returns (float array)."""
        if len(equity_curve) < 2:
            return np.array([])
        df = pd.DataFrame(
            {"t": [ep.snapshot_time for ep in equity_curve],
             "eq": [float(ep.equity) for ep in equity_curve]}
        ).set_index("t")
        # Resample to daily — take the last equity value of each day
        daily = df.resample("D").last().dropna()
        return daily["eq"].pct_change().dropna().values

    def _sharpe(self, equity_curve: list[EquityPoint]) -> Decimal:
        returns = self._daily_returns(equity_curve)
        if len(returns) < 2:
            return _ZERO
        std = returns.std(ddof=1)
        if std == 0:
            return _ZERO
        excess = returns.mean() - _DAILY_RF
        sharpe = excess / std * math.sqrt(_ANNUALIZATION_FACTOR)
        return _d(sharpe, "0.0001")

    def _sortino(self, equity_curve: list[EquityPoint]) -> Decimal:
        returns = self._daily_returns(equity_curve)
        if len(returns) < 2:
            return _ZERO
        downside = returns[returns < 0]
        if len(downside) < 2:
            return _ZERO
        std_down = downside.std(ddof=1)
        if std_down == 0:
            return _ZERO
        excess = returns.mean() - _DAILY_RF
        sortino = excess / std_down * math.sqrt(_ANNUALIZATION_FACTOR)
        return _d(sortino, "0.0001")

    @staticmethod
    def _profit_factor(winners: list[Trade], losers: list[Trade]) -> Decimal:
        gross_wins = sum(t.gross_pnl for t in winners if t.gross_pnl > _ZERO)
        gross_loss = sum(abs(t.gross_pnl) for t in losers if t.gross_pnl < _ZERO)
        if gross_loss == _ZERO:
            return _d(float(gross_wins), "0.0001") if gross_wins > _ZERO else _ZERO
        return (gross_wins / gross_loss).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _expectancy(
        win_rate_pct: Decimal,
        avg_winner: Decimal,
        avg_loser: Decimal,
    ) -> Decimal:
        """Expectancy = win_rate × avg_winner + (1 - win_rate) × avg_loser."""
        wr = win_rate_pct / _HUNDRED
        lr = Decimal("1") - wr
        return (wr * avg_winner + lr * avg_loser).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )

    @staticmethod
    def _streaks(trades: list[Trade]) -> tuple[int, int]:
        """Return (longest_win_streak, longest_loss_streak)."""
        if not trades:
            return 0, 0
        max_wins = max_losses = cur_wins = cur_losses = 0
        for t in trades:
            if t.is_winner:
                cur_wins += 1
                cur_losses = 0
                max_wins = max(max_wins, cur_wins)
            else:
                cur_losses += 1
                cur_wins = 0
                max_losses = max(max_losses, cur_losses)
        return max_wins, max_losses

    @staticmethod
    def _monthly_returns(equity_curve: list[EquityPoint]) -> dict[str, float]:
        if not equity_curve:
            return {}
        df = pd.DataFrame(
            {"t": [ep.snapshot_time for ep in equity_curve],
             "eq": [float(ep.equity) for ep in equity_curve]}
        )
        df["ym"] = pd.to_datetime(df["t"]).dt.to_period("M")
        grp = df.groupby("ym")["eq"].agg(first_eq=("first"), last_eq=("last"))

        # For multi-row months, take first and last
        def _first(x):
            return x.iloc[0]
        def _last(x):
            return x.iloc[-1]

        monthly = df.groupby("ym").agg(first_eq=("eq", _first), last_eq=("eq", _last))
        ret = {}
        for period, row in monthly.iterrows():
            if row["first_eq"] > 0:
                r = (row["last_eq"] / row["first_eq"] - 1) * 100
                ret[str(period)] = round(r, 2)
        return ret

    @staticmethod
    def _yearly_returns(equity_curve: list[EquityPoint]) -> dict[str, float]:
        if not equity_curve:
            return {}
        df = pd.DataFrame(
            {"t": [ep.snapshot_time for ep in equity_curve],
             "eq": [float(ep.equity) for ep in equity_curve]}
        )
        df["year"] = pd.to_datetime(df["t"]).dt.year

        def _first(x):
            return x.iloc[0]
        def _last(x):
            return x.iloc[-1]

        yearly = df.groupby("year").agg(first_eq=("eq", _first), last_eq=("eq", _last))
        ret = {}
        for year, row in yearly.iterrows():
            if row["first_eq"] > 0:
                r = (row["last_eq"] / row["first_eq"] - 1) * 100
                ret[str(year)] = round(r, 2)
        return ret

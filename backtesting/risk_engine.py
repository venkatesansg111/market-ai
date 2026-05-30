from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from backtesting.backtest_models import BacktestConfig, Trade
from utils.logger import get_logger
from config import settings

if TYPE_CHECKING:
    from backtesting.portfolio import Portfolio

logger = get_logger(__name__, settings.log_dir, settings.log_level)

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")


class RiskEngine:
    """Enforces risk limits throughout a backtest run.

    Checks performed before opening a trade:
        1. Max open trades (default: 1 — one position at a time)
        2. Max drawdown: halt trading if portfolio DD exceeds threshold
        3. Sufficient capital to open the position
        4. Max daily loss: no new trades if daily P&L < -max_daily_loss

    All thresholds come from BacktestConfig (set once, immutable).
    Daily P&L is tracked internally; call record_trade_pnl() after each close.
    """

    def __init__(self, config: BacktestConfig) -> None:
        self._config = config
        self._daily_pnl: dict[date, Decimal] = {}

    # ------------------------------------------------------------------
    # Pre-trade checks
    # ------------------------------------------------------------------

    def can_open_trade(
        self,
        portfolio: "Portfolio",
        candle_time: datetime,
        cash_required: Decimal,
    ) -> tuple[bool, str]:
        """Return (True, "") if a new trade may be opened, else (False, reason)."""

        # 1. Max open trades
        n_open = len(portfolio.open_positions)
        if n_open >= self._config.max_open_trades:
            return False, f"max_open_trades={self._config.max_open_trades} reached"

        # 2. Max drawdown guard
        allowed, reason = self.can_continue_trading(portfolio)
        if not allowed:
            return False, reason

        # 3. Capital check
        if cash_required > portfolio.cash:
            return False, (
                f"insufficient cash: need {cash_required:.2f}, "
                f"have {portfolio.cash:.2f}"
            )

        # 4. Max daily loss
        today = candle_time.date()
        today_pnl = self._daily_pnl.get(today, _ZERO)
        max_loss = portfolio.equity * self._config.max_daily_loss_pct
        if today_pnl < -max_loss:
            return False, (
                f"max_daily_loss exceeded: today_pnl={float(today_pnl):.2f}, "
                f"limit={float(-max_loss):.2f}"
            )

        return True, ""

    def can_continue_trading(self, portfolio: "Portfolio") -> tuple[bool, str]:
        """Return (True, "") if the portfolio is within drawdown limits."""
        dd = portfolio.drawdown_pct
        limit = self._config.max_drawdown_pct * _HUNDRED
        if dd >= limit:
            return False, (
                f"max_drawdown exceeded: current={float(dd):.2f}%, "
                f"limit={float(limit):.2f}%"
            )
        return True, ""

    # ------------------------------------------------------------------
    # State updates
    # ------------------------------------------------------------------

    def record_trade_pnl(self, trade: Trade) -> None:
        """Accumulate realized P&L for daily loss tracking."""
        day = trade.exit_time.date()
        self._daily_pnl[day] = self._daily_pnl.get(day, _ZERO) + trade.net_pnl

    def reset_daily_tracking(self) -> None:
        """Clear daily P&L history (use between independent test runs)."""
        self._daily_pnl.clear()

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def daily_pnl_summary(self) -> dict[str, float]:
        return {str(k): float(v) for k, v in sorted(self._daily_pnl.items())}

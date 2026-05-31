from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


class TradeSide(str, Enum):
    LONG = "LONG"


class TradeAction(str, Enum):
    OPEN_LONG = "OPEN_LONG"
    CLOSE_LONG = "CLOSE_LONG"
    HOLD = "HOLD"


@dataclass(frozen=True)
class BacktestConfig:
    """Immutable configuration for a single backtest run."""

    instrument: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    starting_capital: Decimal
    strategy_name: str
    run_name: str = ""
    commission_pct: Decimal = field(default=Decimal("0.0003"))
    slippage_pct: Decimal = field(default=Decimal("0.0005"))
    position_size_pct: Decimal = field(default=Decimal("0.10"))
    max_drawdown_pct: Decimal = field(default=Decimal("0.15"))
    max_daily_loss_pct: Decimal = field(default=Decimal("0.02"))
    max_open_trades: int = 1
    # Phase 4C — multi-timeframe fields (empty string = not an MTF backtest)
    trend_timeframe: str = ""
    setup_timeframe: str = ""
    entry_timeframe: str = ""


@dataclass(frozen=True)
class Trade:
    """Immutable completed round-trip trade record."""

    trade_id: str
    instrument: str
    entry_time: datetime
    exit_time: datetime
    entry_price: Decimal
    exit_price: Decimal
    quantity: int
    side: TradeSide
    entry_commission: Decimal
    exit_commission: Decimal
    entry_slippage: Decimal
    exit_slippage: Decimal

    @property
    def commission(self) -> Decimal:
        return self.entry_commission + self.exit_commission

    @property
    def slippage(self) -> Decimal:
        return self.entry_slippage + self.exit_slippage

    @property
    def gross_pnl(self) -> Decimal:
        if self.side == TradeSide.LONG:
            return (self.exit_price - self.entry_price) * self.quantity
        return (self.entry_price - self.exit_price) * self.quantity

    @property
    def net_pnl(self) -> Decimal:
        return self.gross_pnl - self.commission - self.slippage

    @property
    def holding_minutes(self) -> int:
        return int((self.exit_time - self.entry_time).total_seconds() / 60)

    @property
    def is_winner(self) -> bool:
        return self.net_pnl > Decimal("0")

    @property
    def return_pct(self) -> Decimal:
        cost_basis = self.entry_price * self.quantity + self.commission + self.slippage
        if cost_basis == Decimal("0"):
            return Decimal("0")
        return self.net_pnl / cost_basis * Decimal("100")

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())


@dataclass
class OpenPosition:
    """Mutable in-flight position — updated until closed."""

    trade_id: str
    instrument: str
    quantity: int
    average_price: Decimal
    entry_time: datetime
    side: TradeSide
    entry_commission: Decimal
    entry_slippage: Decimal

    def unrealized_pnl(self, current_price: Decimal) -> Decimal:
        if self.side == TradeSide.LONG:
            return (current_price - self.average_price) * self.quantity
        return (self.average_price - current_price) * self.quantity

    def market_value(self, current_price: Decimal) -> Decimal:
        return current_price * self.quantity

    @property
    def cost_basis(self) -> Decimal:
        return self.average_price * self.quantity


@dataclass(frozen=True)
class EquityPoint:
    """Immutable point-in-time portfolio snapshot for equity curve."""

    snapshot_time: datetime
    cash: Decimal
    equity: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    drawdown_pct: Decimal


@dataclass(frozen=True)
class BacktestResult:
    """Immutable summary of a completed backtest run."""

    run_name: str
    strategy_name: str
    instrument: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    starting_capital: Decimal
    ending_capital: Decimal
    total_return_pct: Decimal
    cagr_pct: Decimal
    win_rate_pct: Decimal
    profit_factor: Decimal
    max_drawdown_pct: Decimal
    sharpe_ratio: Decimal
    sortino_ratio: Decimal
    calmar_ratio: Decimal
    expectancy: Decimal
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_winner: Decimal
    avg_loser: Decimal
    avg_holding_minutes: Decimal
    longest_win_streak: int
    longest_loss_streak: int
    recovery_factor: Decimal
    equity_curve: list[EquityPoint]
    trades: list[Trade]
    monthly_returns: dict[str, float]
    yearly_returns: dict[str, float]

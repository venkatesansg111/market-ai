from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from backtesting.backtest_models import EquityPoint, OpenPosition, Trade
from utils.logger import get_logger
from config import settings

logger = get_logger(__name__, settings.log_dir, settings.log_level)

_ZERO = Decimal("0")
_CENT = Decimal("0.01")


class Portfolio:
    """Tracks portfolio state throughout a backtest run.

    Equity accounting:
        When entering: cash -= (entry_price × qty + commission + slippage)
        Market value   = sum(current_price × qty) for all open positions
        Equity         = cash + market_value_of_open_positions
        Unrealized PnL = market_value - cost_basis (price delta only)
        Realized PnL   = cumulative net_pnl of all closed trades

    All arithmetic uses Decimal for exact monetary precision.
    """

    def __init__(self, starting_capital: Decimal) -> None:
        self._starting_capital: Decimal = starting_capital
        self._cash: Decimal = starting_capital
        self._positions_market_value: Decimal = _ZERO
        self._unrealized_pnl: Decimal = _ZERO
        self._realized_pnl: Decimal = _ZERO
        self._peak_equity: Decimal = starting_capital
        self._open_positions: dict[str, OpenPosition] = {}
        self._closed_trades: list[Trade] = []
        self._equity_curve: list[EquityPoint] = []

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def cash(self) -> Decimal:
        return self._cash

    @property
    def equity(self) -> Decimal:
        return self._cash + self._positions_market_value

    @property
    def unrealized_pnl(self) -> Decimal:
        return self._unrealized_pnl

    @property
    def realized_pnl(self) -> Decimal:
        return self._realized_pnl

    @property
    def drawdown_pct(self) -> Decimal:
        if self._peak_equity <= _ZERO:
            return _ZERO
        dd = (self._peak_equity - self.equity) / self._peak_equity * Decimal("100")
        return max(_ZERO, dd.quantize(Decimal("0.0001")))

    @property
    def has_open_position(self) -> bool:
        return bool(self._open_positions)

    @property
    def current_position(self) -> Optional[OpenPosition]:
        """Returns the first open position, or None."""
        if not self._open_positions:
            return None
        return next(iter(self._open_positions.values()))

    @property
    def open_positions(self) -> dict[str, OpenPosition]:
        return dict(self._open_positions)

    @property
    def closed_trades(self) -> list[Trade]:
        return list(self._closed_trades)

    @property
    def equity_curve(self) -> list[EquityPoint]:
        return list(self._equity_curve)

    @property
    def starting_capital(self) -> Decimal:
        return self._starting_capital

    # ------------------------------------------------------------------
    # Trade operations
    # ------------------------------------------------------------------

    def enter_position(self, position: OpenPosition) -> None:
        """Debit cash for the full entry cost (price + commission + slippage)."""
        cash_cost = (
            position.average_price * position.quantity
            + position.entry_commission
            + position.entry_slippage
        )
        if cash_cost > self._cash:
            raise ValueError(
                f"Insufficient cash to open {position.instrument}: "
                f"need {cash_cost:.2f}, have {self._cash:.2f}"
            )
        self._cash -= cash_cost
        self._open_positions[position.instrument] = position

        logger.debug(
            "[Portfolio] ENTER %s qty=%d avg=%.4f cash_remaining=%.2f",
            position.instrument, position.quantity,
            float(position.average_price), float(self._cash),
        )

    def exit_position(self, trade: Trade) -> None:
        """Credit cash from exit proceeds and record the closed trade."""
        if trade.instrument not in self._open_positions:
            raise ValueError(f"No open position for {trade.instrument}")

        cash_received = (
            trade.exit_price * trade.quantity
            - trade.exit_commission
            - trade.exit_slippage
        )
        self._cash += cash_received
        self._realized_pnl += trade.net_pnl
        del self._open_positions[trade.instrument]
        self._closed_trades.append(trade)

        logger.debug(
            "[Portfolio] EXIT %s qty=%d exit=%.4f net_pnl=%.2f equity=%.2f",
            trade.instrument, trade.quantity,
            float(trade.exit_price), float(trade.net_pnl), float(self.equity),
        )

    # ------------------------------------------------------------------
    # Mark to market
    # ------------------------------------------------------------------

    def mark_to_market(self, prices: dict[str, Decimal]) -> None:
        """Recompute market value and unrealized P&L from current prices."""
        total_market_value = _ZERO
        total_cost_basis = _ZERO

        for instrument, pos in self._open_positions.items():
            price = prices.get(instrument, pos.average_price)
            total_market_value += price * pos.quantity
            total_cost_basis += pos.average_price * pos.quantity

        self._positions_market_value = total_market_value
        self._unrealized_pnl = total_market_value - total_cost_basis

        current_equity = self.equity
        if current_equity > self._peak_equity:
            self._peak_equity = current_equity

    def snapshot(self, snapshot_time: datetime) -> EquityPoint:
        """Append an equity curve point and return it."""
        point = EquityPoint(
            snapshot_time=snapshot_time,
            cash=self._cash,
            equity=self.equity,
            unrealized_pnl=self._unrealized_pnl,
            realized_pnl=self._realized_pnl,
            drawdown_pct=self.drawdown_pct,
        )
        self._equity_curve.append(point)
        return point

    def force_close_all(
        self,
        market_prices: dict[str, Decimal],
        close_time: datetime,
        executor,
    ) -> list[Trade]:
        """Force-close all open positions at given prices (end-of-backtest cleanup)."""
        closed: list[Trade] = []
        for instrument in list(self._open_positions.keys()):
            position = self._open_positions[instrument]
            price = market_prices.get(instrument, position.average_price)
            trade = executor.close_long(position, price, close_time)
            self.exit_position(trade)
            closed.append(trade)
        return closed

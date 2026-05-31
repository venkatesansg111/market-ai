"""Phase 8 — Portfolio State Engine: real-time equity, exposure, drawdown tracking."""
from __future__ import annotations

import logging
from collections import defaultdict, deque
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from risk.risk_models import ExposureSnapshot, RiskMetrics

logger = logging.getLogger(__name__)


class PortfolioStateEngine:
    """
    Maintains the live state of the portfolio.

    Updated via:
      - record_fill()   — when an order is executed
      - mark_to_market()— when prices update
    """

    def __init__(
        self,
        initial_cash: Decimal = Decimal("1_000_000"),
        equity_history_maxlen: int = 252,
    ) -> None:
        self._cash = initial_cash
        self._initial_cash = initial_cash
        self._peak_equity = initial_cash
        self._day_start_equity = initial_cash
        self._today: date = datetime.utcnow().date()

        # symbol → (quantity, avg_cost)
        self._positions: dict[str, tuple[int, Decimal]] = {}

        # symbol → strategy_name (last fill that opened/added)
        self._position_strategy: dict[str, str] = {}

        # symbol → current market price
        self._prices: dict[str, Decimal] = {}

        # rolling equity history (for Sharpe / vol estimation)
        self._equity_history: deque[Decimal] = deque(maxlen=equity_history_maxlen)
        self._equity_history.append(initial_cash)

        # daily P&L accumulator  (reset at start of each trading day)
        self._realized_pnl_today: Decimal = Decimal("0")
        self._realized_pnl_total: Decimal = Decimal("0")

    # ──────────────────────────────────────────────────────────────────
    # Mutation helpers
    # ──────────────────────────────────────────────────────────────────

    def record_fill(
        self,
        symbol: str,
        quantity: int,           # positive = buy, negative = sell
        fill_price: Decimal,
        strategy_name: str,
        commission: Decimal = Decimal("0"),
    ) -> None:
        """Update cash, position, and realized P&L from an executed fill."""
        self._roll_day_if_needed()

        notional = fill_price * abs(quantity)
        if quantity > 0:
            self._cash -= notional + commission
        else:
            self._cash += notional - commission

        prev_qty, prev_avg = self._positions.get(symbol, (0, Decimal("0")))
        new_qty = prev_qty + quantity

        if new_qty == 0:
            # position fully closed
            realized = (fill_price - prev_avg) * prev_qty if prev_qty > 0 else (prev_avg - fill_price) * abs(prev_qty)
            self._realized_pnl_today += realized
            self._realized_pnl_total += realized
            self._positions.pop(symbol, None)
            self._position_strategy.pop(symbol, None)
        elif (prev_qty > 0 and quantity < 0) or (prev_qty < 0 and quantity > 0):
            # partial close
            closed_qty = min(abs(quantity), abs(prev_qty))
            realized: Decimal
            if prev_qty > 0:
                realized = (fill_price - prev_avg) * closed_qty
            else:
                realized = (prev_avg - fill_price) * closed_qty
            self._realized_pnl_today += realized
            self._realized_pnl_total += realized

            if abs(quantity) > abs(prev_qty):
                # reversal — new side at fill price
                new_avg = fill_price
            else:
                new_avg = prev_avg
            self._positions[symbol] = (new_qty, new_avg)
            self._position_strategy[symbol] = strategy_name
        else:
            # adding to position — weighted average cost
            if prev_qty == 0:
                new_avg = fill_price
            else:
                new_avg = (prev_avg * abs(prev_qty) + fill_price * abs(quantity)) / abs(new_qty)
            self._positions[symbol] = (new_qty, new_avg)
            self._position_strategy[symbol] = strategy_name

        if symbol in self._prices:
            pass  # price unchanged until next mark
        else:
            self._prices[symbol] = fill_price

        self._update_peak()
        logger.debug("fill recorded: %s qty=%d @ %s  cash=%s", symbol, quantity, fill_price, self._cash)

    def update_price(self, symbol: str, price: Decimal) -> None:
        self._prices[symbol] = price
        self._update_peak()

    def update_prices(self, price_map: dict[str, Decimal]) -> None:
        self._prices.update(price_map)
        self._update_peak()

    def reset_day(self) -> None:
        self._day_start_equity = self.equity
        self._realized_pnl_today = Decimal("0")
        self._today = datetime.utcnow().date()
        self._equity_history.append(self.equity)

    # ──────────────────────────────────────────────────────────────────
    # Read-only properties
    # ──────────────────────────────────────────────────────────────────

    @property
    def cash(self) -> Decimal:
        return self._cash

    @property
    def equity(self) -> Decimal:
        """Total equity = cash + mark-to-market value of all positions."""
        mtm = Decimal("0")
        for symbol, (qty, avg) in self._positions.items():
            price = self._prices.get(symbol, avg)
            mtm += price * qty
        return self._cash + mtm

    @property
    def unrealized_pnl(self) -> Decimal:
        total = Decimal("0")
        for symbol, (qty, avg) in self._positions.items():
            price = self._prices.get(symbol, avg)
            if qty > 0:
                total += (price - avg) * qty
            else:
                total += (avg - price) * abs(qty)
        return total

    @property
    def realized_pnl_total(self) -> Decimal:
        return self._realized_pnl_total

    @property
    def daily_pnl(self) -> Decimal:
        return self.equity - self._day_start_equity

    @property
    def daily_pnl_pct(self) -> float:
        if self._day_start_equity == 0:
            return 0.0
        return float(self.daily_pnl / self._day_start_equity * 100)

    @property
    def current_drawdown_pct(self) -> float:
        if self._peak_equity == 0:
            return 0.0
        return float((self._peak_equity - self.equity) / self._peak_equity * 100)

    @property
    def peak_equity(self) -> Decimal:
        return self._peak_equity

    @property
    def positions(self) -> dict[str, tuple[int, Decimal]]:
        """Returns {symbol: (quantity, avg_cost)}."""
        return dict(self._positions)

    @property
    def open_symbols(self) -> list[str]:
        return [s for s, (q, _) in self._positions.items() if q != 0]

    # ──────────────────────────────────────────────────────────────────
    # Exposure calculations
    # ──────────────────────────────────────────────────────────────────

    def exposure_snapshot(self) -> ExposureSnapshot:
        snap = ExposureSnapshot()
        eq = self.equity
        for symbol, (qty, avg) in self._positions.items():
            price = self._prices.get(symbol, avg)
            notional = price * qty
            snap.per_asset[symbol] = notional
            strategy = self._position_strategy.get(symbol, "unknown")
            snap.per_strategy[strategy] = snap.per_strategy.get(strategy, Decimal("0")) + abs(notional)
            if qty > 0:
                snap.total_long += notional
            else:
                snap.total_short += notional
        return snap

    def position_pct_of_equity(self, symbol: str) -> float:
        if symbol not in self._positions:
            return 0.0
        qty, avg = self._positions[symbol]
        price = self._prices.get(symbol, avg)
        notional = abs(price * qty)
        eq = self.equity
        if eq == 0:
            return 0.0
        return float(notional / eq * 100)

    def strategy_exposure_pct(self, strategy_name: str) -> float:
        snap = self.exposure_snapshot()
        notional = snap.per_strategy.get(strategy_name, Decimal("0"))
        eq = self.equity
        if eq == 0:
            return 0.0
        return float(notional / eq * 100)

    def gross_leverage(self) -> float:
        snap = self.exposure_snapshot()
        eq = self.equity
        if eq == 0:
            return 0.0
        return float(snap.gross_exposure / eq)

    # ──────────────────────────────────────────────────────────────────
    # Metrics snapshot
    # ──────────────────────────────────────────────────────────────────

    def risk_metrics(self) -> RiskMetrics:
        snap = self.exposure_snapshot()
        eq = self.equity

        vol: Optional[float] = None
        sharpe: Optional[float] = None
        hist = list(self._equity_history)
        if len(hist) >= 2:
            returns = [
                float((hist[i] - hist[i - 1]) / hist[i - 1])
                for i in range(1, len(hist))
                if hist[i - 1] != 0
            ]
            if returns:
                n = len(returns)
                mean_r = sum(returns) / n
                variance = sum((r - mean_r) ** 2 for r in returns) / n
                vol = variance ** 0.5
                if vol > 0:
                    sharpe = mean_r / vol * (252 ** 0.5)

        return RiskMetrics(
            equity=eq,
            cash=self._cash,
            gross_exposure=snap.gross_exposure,
            net_exposure=snap.net_exposure,
            leverage=self.gross_leverage(),
            current_drawdown_pct=self.current_drawdown_pct,
            daily_pnl=self.daily_pnl,
            daily_pnl_pct=self.daily_pnl_pct,
            peak_equity=self._peak_equity,
            sharpe_rolling=sharpe,
            volatility_rolling=vol,
        )

    # ──────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────

    def _update_peak(self) -> None:
        eq = self.equity
        if eq > self._peak_equity:
            self._peak_equity = eq

    def _roll_day_if_needed(self) -> None:
        today = datetime.utcnow().date()
        if today != self._today:
            self.reset_day()

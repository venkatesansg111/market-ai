"""Phase 10 — PnL Attribution Engine."""
from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from streaming.event_bus import EventBus
from streaming.event_models import FillEvent, PortfolioEvent


@dataclass
class TradePnL:
    trade_id: Optional[str]
    symbol: str
    strategy_name: str
    action: str
    quantity: int
    fill_price: Decimal
    commission: Decimal
    timestamp: datetime
    regime: str = "unknown"
    realized_pnl: Decimal = Decimal("0")


class PnLAttribution:
    """Tracks and attributes PnL by strategy, asset, regime, and time."""

    def __init__(self, bus: EventBus | None = None) -> None:
        self._trades: list[TradePnL] = []
        self._portfolio_snapshots: list[tuple[datetime, Decimal]] = []
        self._pending_buy: dict[tuple[str, str], TradePnL] = {}  # (symbol, strategy) -> open buy
        self._regime_context: dict[str, str] = {}  # symbol -> regime
        self._lock = threading.RLock()
        if bus is not None:
            self.attach(bus)

    def attach(self, bus: EventBus) -> None:
        bus.subscribe(FillEvent, self._on_fill)
        bus.subscribe(PortfolioEvent, self._on_portfolio)

    def set_regime(self, symbol: str, regime: str) -> None:
        with self._lock:
            self._regime_context[symbol] = regime

    def _on_fill(self, e: FillEvent) -> None:
        with self._lock:
            regime = self._regime_context.get(e.symbol, "unknown")
            key = (e.symbol, e.strategy_name)
            trade = TradePnL(
                trade_id=None,
                symbol=e.symbol,
                strategy_name=e.strategy_name,
                action=e.action,
                quantity=e.quantity,
                fill_price=e.price,
                commission=e.commission,
                timestamp=e.timestamp,
                regime=regime,
            )
            if e.action == "BUY":
                self._pending_buy[key] = trade
                self._trades.append(trade)
            elif e.action == "SELL":
                buy = self._pending_buy.pop(key, None)
                if buy is not None:
                    pnl = (e.price - buy.fill_price) * e.quantity - e.commission - buy.commission
                    trade.realized_pnl = pnl
                self._trades.append(trade)

    def _on_portfolio(self, e: PortfolioEvent) -> None:
        with self._lock:
            self._portfolio_snapshots.append((datetime.utcnow(), e.equity))

    def by_strategy(self) -> dict[str, Decimal]:
        result: dict[str, Decimal] = defaultdict(Decimal)
        with self._lock:
            for t in self._trades:
                if t.action == "SELL":
                    result[t.strategy_name] += t.realized_pnl
        return dict(result)

    def by_asset(self) -> dict[str, Decimal]:
        result: dict[str, Decimal] = defaultdict(Decimal)
        with self._lock:
            for t in self._trades:
                if t.action == "SELL":
                    result[t.symbol] += t.realized_pnl
        return dict(result)

    def by_regime(self) -> dict[str, Decimal]:
        result: dict[str, Decimal] = defaultdict(Decimal)
        with self._lock:
            for t in self._trades:
                if t.action == "SELL":
                    result[t.regime] += t.realized_pnl
        return dict(result)

    def by_day(self) -> dict[date, Decimal]:
        result: dict[date, Decimal] = defaultdict(Decimal)
        with self._lock:
            for t in self._trades:
                if t.action == "SELL":
                    result[t.timestamp.date()] += t.realized_pnl
        return dict(result)

    def total_pnl(self) -> Decimal:
        with self._lock:
            return sum((t.realized_pnl for t in self._trades if t.action == "SELL"), Decimal("0"))

    def trade_count(self) -> int:
        with self._lock:
            return sum(1 for t in self._trades if t.action == "SELL")

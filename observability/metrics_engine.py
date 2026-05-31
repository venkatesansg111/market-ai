"""Phase 10 — Metrics Engine: portfolio, performance, execution, strategy metrics."""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from streaming.event_bus import EventBus
from streaming.event_models import FillEvent, OrderEvent, PortfolioEvent, SignalEvent


@dataclass
class PortfolioMetrics:
    equity: Decimal
    cash: Decimal
    exposure: Decimal
    leverage: float
    drawdown_pct: float
    peak_equity: Decimal


@dataclass
class PerformanceMetrics:
    sharpe_ratio: Optional[float]
    sortino_ratio: Optional[float]
    calmar_ratio: Optional[float]
    win_rate: float
    profit_factor: float
    total_trades: int
    winning_trades: int
    losing_trades: int


@dataclass
class ExecutionMetrics:
    fill_count: int
    order_count: int
    fill_rate: float
    total_commission: Decimal
    avg_fill_price: Optional[Decimal]


@dataclass
class StrategyMetrics:
    signal_count: int
    flat_count: int
    buy_count: int
    sell_count: int
    avg_confidence: float


class MetricsEngine:
    """Real-time metrics computation engine."""

    RISK_FREE_RATE = 0.05  # annual

    def __init__(self, bus: EventBus | None = None) -> None:
        self._equity_series: list[tuple[datetime, Decimal]] = []
        self._fills: list[FillEvent] = []
        self._orders: list[OrderEvent] = []
        self._signals: list[SignalEvent] = []
        self._peak_equity = Decimal("0")
        self._current_portfolio: Optional[PortfolioEvent] = None
        self._lock = threading.RLock()
        if bus is not None:
            self.attach(bus)

    def attach(self, bus: EventBus) -> None:
        bus.subscribe(PortfolioEvent, self._on_portfolio)
        bus.subscribe(FillEvent, self._on_fill)
        bus.subscribe(OrderEvent, self._on_order)
        bus.subscribe(SignalEvent, self._on_signal)

    def _on_portfolio(self, e: PortfolioEvent) -> None:
        with self._lock:
            self._current_portfolio = e
            self._equity_series.append((datetime.utcnow(), e.equity))
            if e.equity > self._peak_equity:
                self._peak_equity = e.equity

    def _on_fill(self, e: FillEvent) -> None:
        with self._lock:
            self._fills.append(e)

    def _on_order(self, e: OrderEvent) -> None:
        with self._lock:
            self._orders.append(e)

    def _on_signal(self, e: SignalEvent) -> None:
        with self._lock:
            self._signals.append(e)

    def portfolio_metrics(self) -> Optional[PortfolioMetrics]:
        with self._lock:
            p = self._current_portfolio
            peak = self._peak_equity
        if p is None:
            return None
        return PortfolioMetrics(
            equity=p.equity,
            cash=p.cash,
            exposure=p.equity - p.cash,
            leverage=float(p.equity / p.cash) if p.cash > 0 else 0.0,
            drawdown_pct=p.current_drawdown_pct,
            peak_equity=peak,
        )

    def performance_metrics(self) -> PerformanceMetrics:
        with self._lock:
            equities = [float(e) for _, e in self._equity_series]

        returns = [
            (equities[i] - equities[i - 1]) / equities[i - 1]
            for i in range(1, len(equities))
            if equities[i - 1] != 0
        ]
        wins = [r for r in returns if r > 0]
        losses = [r for r in returns if r < 0]
        total = len(returns)
        win_rate = len(wins) / total if total > 0 else 0.0
        gross_win = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = (
            gross_win / gross_loss if gross_loss > 0
            else float("inf") if gross_win > 0
            else 0.0
        )

        return PerformanceMetrics(
            sharpe_ratio=self._sharpe(returns),
            sortino_ratio=self._sortino(returns),
            calmar_ratio=self._calmar(equities, returns),
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=total,
            winning_trades=len(wins),
            losing_trades=len(losses),
        )

    def execution_metrics(self) -> ExecutionMetrics:
        with self._lock:
            fills = list(self._fills)
            orders = list(self._orders)

        fill_count = len(fills)
        order_count = len(orders)
        fill_rate = fill_count / order_count if order_count > 0 else 0.0
        total_commission = sum((f.commission for f in fills), Decimal("0"))
        prices = [f.price for f in fills]
        avg_fill_price = sum(prices) / len(prices) if prices else None

        return ExecutionMetrics(
            fill_count=fill_count,
            order_count=order_count,
            fill_rate=fill_rate,
            total_commission=total_commission,
            avg_fill_price=avg_fill_price,
        )

    def strategy_metrics(self, strategy_name: str | None = None) -> StrategyMetrics:
        with self._lock:
            signals = [
                s for s in self._signals
                if strategy_name is None or s.strategy_name == strategy_name
            ]

        flat = sum(1 for s in signals if s.action == "FLAT")
        buys = sum(1 for s in signals if s.action == "BUY")
        sells = sum(1 for s in signals if s.action == "SELL")
        action_signals = [s for s in signals if s.action != "FLAT"]
        avg_conf = (
            sum(s.confidence for s in action_signals) / len(action_signals)
            if action_signals else 0.0
        )

        return StrategyMetrics(
            signal_count=len(signals),
            flat_count=flat,
            buy_count=buys,
            sell_count=sells,
            avg_confidence=avg_conf,
        )

    @staticmethod
    def _sharpe(returns: list[float]) -> Optional[float]:
        if len(returns) < 2:
            return None
        n = len(returns)
        mean = sum(returns) / n
        std = math.sqrt(sum((r - mean) ** 2 for r in returns) / (n - 1))
        if std == 0:
            return None
        return (mean - MetricsEngine.RISK_FREE_RATE / 252) / std * math.sqrt(252)

    @staticmethod
    def _sortino(returns: list[float]) -> Optional[float]:
        if len(returns) < 2:
            return None
        mean = sum(returns) / len(returns)
        downside = [r for r in returns if r < 0]
        if not downside:
            return None
        downside_std = math.sqrt(sum(r ** 2 for r in downside) / len(downside))
        if downside_std == 0:
            return None
        return (mean - MetricsEngine.RISK_FREE_RATE / 252) / downside_std * math.sqrt(252)

    @staticmethod
    def _calmar(equities: list[float], returns: list[float]) -> Optional[float]:
        if len(equities) < 2 or not returns:
            return None
        peak = equities[0]
        max_dd = 0.0
        for eq in equities:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
        if max_dd == 0:
            return None
        annualized_return = sum(returns) / len(returns) * 252
        return annualized_return / max_dd

"""Phase 10 — Research Analytics Engine."""
from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from streaming.event_bus import EventBus
from streaming.event_models import FillEvent, SignalEvent


@dataclass
class SignalAnalytics:
    strategy_name: str
    total_signals: int
    buy_signals: int
    sell_signals: int
    avg_confidence: float
    high_confidence_signals: int  # confidence >= 0.7


@dataclass
class StrategyAnalytics:
    strategy_name: str
    total_fills: int
    total_pnl: Decimal
    avg_fill_price: Optional[Decimal]
    symbols: list[str]


class ResearchAnalyticsEngine:
    """Quant research analytics: signal quality, strategy performance, execution analysis."""

    def __init__(self, bus: EventBus | None = None) -> None:
        self._signals: list[SignalEvent] = []
        self._fills: list[FillEvent] = []
        self._lock = threading.RLock()
        if bus is not None:
            self.attach(bus)

    def attach(self, bus: EventBus) -> None:
        bus.subscribe(SignalEvent, self._on_signal)
        bus.subscribe(FillEvent, self._on_fill)

    def _on_signal(self, e: SignalEvent) -> None:
        with self._lock:
            self._signals.append(e)

    def _on_fill(self, e: FillEvent) -> None:
        with self._lock:
            self._fills.append(e)

    def signal_analytics(self, strategy_name: str | None = None) -> list[SignalAnalytics]:
        with self._lock:
            signals = list(self._signals)

        by_strategy: dict[str, list[SignalEvent]] = defaultdict(list)
        for s in signals:
            if strategy_name is None or s.strategy_name == strategy_name:
                by_strategy[s.strategy_name].append(s)

        result = []
        for name, evs in by_strategy.items():
            buys = [s for s in evs if s.action == "BUY"]
            sells = [s for s in evs if s.action == "SELL"]
            action_evs = buys + sells
            avg_conf = (
                sum(s.confidence for s in action_evs) / len(action_evs)
                if action_evs else 0.0
            )
            high_conf = sum(1 for s in action_evs if s.confidence >= 0.7)
            result.append(SignalAnalytics(
                strategy_name=name,
                total_signals=len(evs),
                buy_signals=len(buys),
                sell_signals=len(sells),
                avg_confidence=avg_conf,
                high_confidence_signals=high_conf,
            ))
        return result

    def strategy_analytics(self) -> list[StrategyAnalytics]:
        with self._lock:
            fills = list(self._fills)

        by_strategy: dict[str, list[FillEvent]] = defaultdict(list)
        for f in fills:
            by_strategy[f.strategy_name].append(f)

        result = []
        for name, evs in by_strategy.items():
            buy_evs = [f for f in evs if f.action == "BUY"]
            sell_evs = [f for f in evs if f.action == "SELL"]
            prices = [f.price for f in evs]
            avg_price = sum(prices) / len(prices) if prices else None
            pnl = sum(
                (s.price - b.price) * s.quantity
                for s, b in zip(sell_evs, buy_evs)
            )
            symbols = list({f.symbol for f in evs})
            result.append(StrategyAnalytics(
                strategy_name=name,
                total_fills=len(evs),
                total_pnl=pnl,
                avg_fill_price=avg_price,
                symbols=symbols,
            ))
        return result

    def confidence_distribution(self) -> dict[str, int]:
        with self._lock:
            signals = [s for s in self._signals if s.action != "FLAT"]
        buckets = {"0.0-0.3": 0, "0.3-0.5": 0, "0.5-0.7": 0, "0.7-0.9": 0, "0.9-1.0": 0}
        for s in signals:
            c = s.confidence
            if c < 0.3:
                buckets["0.0-0.3"] += 1
            elif c < 0.5:
                buckets["0.3-0.5"] += 1
            elif c < 0.7:
                buckets["0.5-0.7"] += 1
            elif c < 0.9:
                buckets["0.7-0.9"] += 1
            else:
                buckets["0.9-1.0"] += 1
        return buckets

    def fill_price_distribution(self) -> dict[str, int]:
        with self._lock:
            fills = list(self._fills)
        if not fills:
            return {}
        prices = [float(f.price) for f in fills]
        mn, mx = min(prices), max(prices)
        if mn == mx:
            return {f"{mn:.2f}": len(prices)}
        step = (mx - mn) / 5
        buckets: dict[str, int] = {}
        for i in range(5):
            lo = mn + i * step
            hi = mn + (i + 1) * step
            key = f"{lo:.2f}-{hi:.2f}"
            if i < 4:
                buckets[key] = sum(1 for p in prices if lo <= p < hi)
            else:
                buckets[key] = sum(1 for p in prices if lo <= p <= hi)
        return buckets

    @property
    def signal_count(self) -> int:
        with self._lock:
            return len(self._signals)

    @property
    def fill_count(self) -> int:
        with self._lock:
            return len(self._fills)

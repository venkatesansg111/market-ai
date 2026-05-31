"""Phase 10 — Event Correlation Engine: traces the full event chain for a trade."""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from streaming.event_bus import EventBus
from streaming.event_models import (
    CandleEvent, FillEvent, IndicatorEvent, OrderEvent,
    PortfolioEvent, RiskEvent, SignalEvent, TickEvent,
)


@dataclass
class EventChain:
    chain_id: str
    symbol: str
    strategy_name: str
    tick: Optional[TickEvent] = None
    candle: Optional[CandleEvent] = None
    indicator: Optional[IndicatorEvent] = None
    signal: Optional[SignalEvent] = None
    risk: Optional[RiskEvent] = None
    order: Optional[OrderEvent] = None
    fills: list[FillEvent] = field(default_factory=list)
    portfolio: Optional[PortfolioEvent] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def steps(self) -> list[tuple[str, object]]:
        result = []
        if self.tick:
            result.append(("Tick Received", self.tick))
        if self.candle:
            result.append(("Candle Completed", self.candle))
        if self.indicator:
            result.append(("Indicator Updated", self.indicator))
        if self.signal:
            result.append(("Signal Generated", self.signal))
        if self.risk:
            result.append(("Risk Evaluated", self.risk))
        if self.order:
            result.append(("Order Submitted", self.order))
        for f in self.fills:
            result.append(("Order Filled", f))
        if self.portfolio:
            result.append(("Portfolio Updated", self.portfolio))
        return result

    def is_complete(self) -> bool:
        return len(self.fills) > 0 and self.portfolio is not None


class EventCorrelationEngine:
    """Correlates streaming events into complete trade chains."""

    def __init__(self, bus: EventBus | None = None) -> None:
        self._chains: dict[str, EventChain] = {}
        self._pending: dict[tuple[str, str], str] = {}  # (symbol, strategy) -> chain_id
        self._completed: list[EventChain] = []
        self._latest_tick: dict[str, TickEvent] = {}
        self._latest_candle: dict[str, CandleEvent] = {}
        self._latest_indicator: dict[str, IndicatorEvent] = {}
        self._lock = threading.RLock()
        if bus is not None:
            self.attach(bus)

    def attach(self, bus: EventBus) -> None:
        bus.subscribe(TickEvent, self._on_tick)
        bus.subscribe(CandleEvent, self._on_candle)
        bus.subscribe(IndicatorEvent, self._on_indicator)
        bus.subscribe(SignalEvent, self._on_signal)
        bus.subscribe(RiskEvent, self._on_risk)
        bus.subscribe(OrderEvent, self._on_order)
        bus.subscribe(FillEvent, self._on_fill)
        bus.subscribe(PortfolioEvent, self._on_portfolio)

    def _on_tick(self, e: TickEvent) -> None:
        with self._lock:
            self._latest_tick[e.symbol] = e

    def _on_candle(self, e: CandleEvent) -> None:
        if e.is_closed:
            with self._lock:
                self._latest_candle[e.symbol] = e

    def _on_indicator(self, e: IndicatorEvent) -> None:
        with self._lock:
            self._latest_indicator[e.symbol] = e

    def _on_signal(self, e: SignalEvent) -> None:
        if e.action == "FLAT":
            return
        chain_id = str(uuid.uuid4())
        with self._lock:
            chain = EventChain(
                chain_id=chain_id,
                symbol=e.symbol,
                strategy_name=e.strategy_name,
                tick=self._latest_tick.get(e.symbol),
                candle=self._latest_candle.get(e.symbol),
                indicator=self._latest_indicator.get(e.symbol),
                signal=e,
            )
            self._chains[chain_id] = chain
            self._pending[(e.symbol, e.strategy_name)] = chain_id

    def _on_risk(self, e: RiskEvent) -> None:
        with self._lock:
            chain_id = self._pending.get((e.symbol, e.strategy_name))
            if chain_id and chain_id in self._chains:
                self._chains[chain_id].risk = e

    def _on_order(self, e: OrderEvent) -> None:
        with self._lock:
            chain_id = self._pending.get((e.symbol, e.strategy_name))
            if chain_id and chain_id in self._chains:
                self._chains[chain_id].order = e

    def _on_fill(self, e: FillEvent) -> None:
        with self._lock:
            chain_id = self._pending.get((e.symbol, e.strategy_name))
            if chain_id and chain_id in self._chains:
                self._chains[chain_id].fills.append(e)

    def _on_portfolio(self, e: PortfolioEvent) -> None:
        with self._lock:
            for chain_id in list(self._pending.values()):
                chain = self._chains.get(chain_id)
                if chain and chain.fills and chain.portfolio is None:
                    chain.portfolio = e
                    self._completed.append(chain)

    def trace_trade(self, chain_id: str) -> Optional[EventChain]:
        with self._lock:
            return self._chains.get(chain_id)

    def get_completed_chains(self) -> list[EventChain]:
        with self._lock:
            return list(self._completed)

    def get_all_chains(self) -> list[EventChain]:
        with self._lock:
            return list(self._chains.values())

    def chain_count(self) -> int:
        with self._lock:
            return len(self._chains)

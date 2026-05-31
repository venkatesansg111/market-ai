"""Phase 10 — Decision Journal: central record of all trading decisions."""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from streaming.event_bus import EventBus
from streaming.event_models import (
    CandleEvent, FillEvent, IndicatorEvent, OrderEvent,
    PortfolioEvent, RiskEvent, SignalEvent, StreamEvent,
)


@dataclass
class DecisionRecord:
    decision_id: str
    decision_type: str  # "candle"|"indicator"|"signal"|"risk"|"order"|"fill"|"portfolio"
    timestamp: datetime
    symbol: str
    strategy_name: Optional[str]
    trade_id: Optional[str]
    event: StreamEvent
    metadata: dict = field(default_factory=dict)


class DecisionJournal:
    """Records all decision events and links them into trade chains."""

    def __init__(self, bus: EventBus | None = None) -> None:
        self._records: list[DecisionRecord] = []
        self._trade_index: dict[str, list[DecisionRecord]] = {}
        self._strategy_index: dict[str, list[DecisionRecord]] = {}
        self._pending_signals: dict[tuple[str, str], str] = {}  # (symbol, strategy) -> trade_id
        self._lock = threading.RLock()
        if bus is not None:
            self.attach(bus)

    def attach(self, bus: EventBus) -> None:
        bus.subscribe(CandleEvent, self._on_candle)
        bus.subscribe(IndicatorEvent, self._on_indicator)
        bus.subscribe(SignalEvent, self._on_signal)
        bus.subscribe(RiskEvent, self._on_risk)
        bus.subscribe(OrderEvent, self._on_order)
        bus.subscribe(FillEvent, self._on_fill)
        bus.subscribe(PortfolioEvent, self._on_portfolio)

    def record(
        self,
        decision_type: str,
        symbol: str,
        event: StreamEvent,
        strategy_name: Optional[str] = None,
        trade_id: Optional[str] = None,
        metadata: dict | None = None,
    ) -> DecisionRecord:
        rec = DecisionRecord(
            decision_id=str(uuid.uuid4()),
            decision_type=decision_type,
            timestamp=datetime.utcnow(),
            symbol=symbol,
            strategy_name=strategy_name,
            trade_id=trade_id,
            event=event,
            metadata=metadata or {},
        )
        with self._lock:
            self._records.append(rec)
            if trade_id:
                self._trade_index.setdefault(trade_id, []).append(rec)
            if strategy_name:
                self._strategy_index.setdefault(strategy_name, []).append(rec)
        return rec

    def _on_candle(self, e: CandleEvent) -> None:
        if e.is_closed:
            self.record("candle", e.symbol, e, metadata={"timeframe": e.timeframe})

    def _on_indicator(self, e: IndicatorEvent) -> None:
        self.record("indicator", e.symbol, e, metadata={"timeframe": e.timeframe, "is_warm": e.is_warm})

    def _on_signal(self, e: SignalEvent) -> None:
        if e.action == "FLAT":
            return
        trade_id = str(uuid.uuid4())
        with self._lock:
            self._pending_signals[(e.symbol, e.strategy_name)] = trade_id
        self.record(
            "signal", e.symbol, e, strategy_name=e.strategy_name, trade_id=trade_id,
            metadata={"action": e.action, "confidence": e.confidence, "regime": e.regime},
        )

    def _on_risk(self, e: RiskEvent) -> None:
        with self._lock:
            trade_id = self._pending_signals.get((e.symbol, e.strategy_name))
        self.record(
            "risk", e.symbol, e, strategy_name=e.strategy_name, trade_id=trade_id,
            metadata={"decision": e.decision, "reason": e.reason},
        )

    def _on_order(self, e: OrderEvent) -> None:
        with self._lock:
            trade_id = self._pending_signals.get((e.symbol, e.strategy_name))
        self.record(
            "order", e.symbol, e, strategy_name=e.strategy_name, trade_id=trade_id,
            metadata={"order_id": e.order_id, "action": e.action, "quantity": e.quantity},
        )

    def _on_fill(self, e: FillEvent) -> None:
        with self._lock:
            trade_id = self._pending_signals.pop((e.symbol, e.strategy_name), None)
        self.record(
            "fill", e.symbol, e, strategy_name=e.strategy_name, trade_id=trade_id,
            metadata={"order_id": e.order_id, "quantity": e.quantity, "price": str(e.price)},
        )

    def _on_portfolio(self, e: PortfolioEvent) -> None:
        self.record("portfolio", "", e, metadata={"equity": str(e.equity), "cash": str(e.cash)})

    def get_trade_history(self, trade_id: str) -> list[DecisionRecord]:
        with self._lock:
            return list(self._trade_index.get(trade_id, []))

    def get_strategy_decisions(self, strategy_name: str) -> list[DecisionRecord]:
        with self._lock:
            return list(self._strategy_index.get(strategy_name, []))

    def get_all_records(self, decision_type: str | None = None) -> list[DecisionRecord]:
        with self._lock:
            if decision_type is None:
                return list(self._records)
            return [r for r in self._records if r.decision_type == decision_type]

    @property
    def record_count(self) -> int:
        with self._lock:
            return len(self._records)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
            self._trade_index.clear()
            self._strategy_index.clear()
            self._pending_signals.clear()

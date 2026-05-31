"""Phase 10 — Trade Explainability Engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from observability.decision_journal import DecisionJournal, DecisionRecord
from streaming.event_models import FillEvent, RiskEvent, SignalEvent


@dataclass
class TradeExplanation:
    trade_id: str
    symbol: str
    strategy: str
    action: str
    regime: str
    signal_confidence: float
    risk_score: float
    risk_decision: str
    risk_reason: str
    position_size_reason: str
    execution_reason: str
    fill_price: Optional[float]
    fill_quantity: int
    timestamp: datetime
    raw_records: list[DecisionRecord] = field(default_factory=list)


class TradeExplainabilityEngine:
    """Reconstructs full trade lifecycle from the decision journal."""

    def __init__(self, journal: DecisionJournal) -> None:
        self._journal = journal

    def explain_trade(self, trade_id: str) -> Optional[TradeExplanation]:
        records = self._journal.get_trade_history(trade_id)
        if not records:
            return None

        signal_rec = next((r for r in records if r.decision_type == "signal"), None)
        risk_rec = next((r for r in records if r.decision_type == "risk"), None)
        fill_rec = next((r for r in records if r.decision_type == "fill"), None)

        if signal_rec is None:
            return None

        signal: SignalEvent = signal_rec.event

        risk_decision = "UNKNOWN"
        risk_reason = ""
        risk_score = 0.0
        approved_qty = 0
        original_qty = 0
        if risk_rec is not None:
            risk_ev: RiskEvent = risk_rec.event
            risk_decision = risk_ev.decision
            risk_reason = risk_ev.reason
            approved_qty = risk_ev.approved_quantity
            original_qty = risk_ev.original_quantity
            if original_qty > 0:
                risk_score = 1.0 - (approved_qty / original_qty)

        fill_price = None
        fill_quantity = 0
        execution_reason = "No fill recorded"
        if fill_rec is not None:
            fill_ev: FillEvent = fill_rec.event
            fill_price = float(fill_ev.price)
            fill_quantity = fill_ev.quantity
            execution_reason = f"Filled {fill_quantity} @ {fill_price}"

        position_size_reason = (
            f"Risk {risk_decision}: {approved_qty} units approved"
            f" (original request: {original_qty})"
        )

        return TradeExplanation(
            trade_id=trade_id,
            symbol=signal.symbol,
            strategy=signal.strategy_name,
            action=signal.action,
            regime=signal.regime,
            signal_confidence=signal.confidence,
            risk_score=risk_score,
            risk_decision=risk_decision,
            risk_reason=risk_reason,
            position_size_reason=position_size_reason,
            execution_reason=execution_reason,
            fill_price=fill_price,
            fill_quantity=fill_quantity,
            timestamp=signal_rec.timestamp,
            raw_records=records,
        )

    def explain_all_trades(self) -> list[TradeExplanation]:
        all_trade_ids = {r.trade_id for r in self._journal.get_all_records() if r.trade_id}
        explanations = []
        for tid in all_trade_ids:
            exp = self.explain_trade(tid)
            if exp is not None:
                explanations.append(exp)
        return explanations

"""Unit tests for observability.explainability — TradeExplainabilityEngine."""
from __future__ import annotations

from decimal import Decimal

import pytest

from observability.decision_journal import DecisionJournal
from observability.explainability import TradeExplainabilityEngine, TradeExplanation
from streaming.event_bus import EventBus
from streaming.event_models import FillEvent, OrderEvent, RiskEvent, SignalEvent


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _signal(action: str = "BUY", confidence: float = 0.85) -> SignalEvent:
    return SignalEvent(
        symbol="AAPL", strategy_name="momentum",
        action=action, confidence=confidence,
        timeframe="1m", current_price=Decimal("150"),
        atr=Decimal("2"), stop_price=Decimal("145"),
        regime="bullish", regime_strength=0.8,
    )


def _risk(decision: str = "APPROVED", approved: int = 10, original: int = 10) -> RiskEvent:
    return RiskEvent(
        symbol="AAPL", strategy_name="momentum",
        decision=decision, approved_quantity=approved,
        original_quantity=original, reason="within limits",
    )


def _order() -> OrderEvent:
    return OrderEvent(
        order_id="ord-1", symbol="AAPL", action="BUY",
        quantity=10, order_type="MARKET", strategy_name="momentum",
    )


def _fill(qty: int = 10, price: float = 150.0) -> FillEvent:
    return FillEvent(
        order_id="ord-1", symbol="AAPL", quantity=qty,
        price=Decimal(str(price)), strategy_name="momentum",
        action="BUY", commission=Decimal("0.5"),
    )


def _build_full_trade(bus: EventBus) -> str:
    """Publish a complete trade cycle and return the trade_id."""
    bus.publish(_signal())
    bus.publish(_risk())
    bus.publish(_order())
    bus.publish(_fill())
    return None  # caller gets trade_id from journal


# ──────────────────────────────────────────────────────────────────────
# explain_trade
# ──────────────────────────────────────────────────────────────────────

class TestExplainTrade:
    def setup_method(self):
        self.bus = EventBus()
        self.journal = DecisionJournal(self.bus)
        self.engine = TradeExplainabilityEngine(self.journal)

    def _get_trade_id(self) -> str:
        return self.journal.get_all_records("signal")[0].trade_id

    def test_returns_none_for_unknown_trade(self):
        result = self.engine.explain_trade("no-such-id")
        assert result is None

    def test_returns_explanation_for_known_trade(self):
        self.bus.publish(_signal())
        self.bus.publish(_risk())
        self.bus.publish(_fill())
        tid = self._get_trade_id()
        exp = self.engine.explain_trade(tid)
        assert isinstance(exp, TradeExplanation)

    def test_explanation_symbol_correct(self):
        self.bus.publish(_signal())
        tid = self._get_trade_id()
        exp = self.engine.explain_trade(tid)
        assert exp.symbol == "AAPL"

    def test_explanation_strategy_correct(self):
        self.bus.publish(_signal())
        tid = self._get_trade_id()
        exp = self.engine.explain_trade(tid)
        assert exp.strategy == "momentum"

    def test_explanation_action_correct(self):
        self.bus.publish(_signal(action="BUY"))
        tid = self._get_trade_id()
        exp = self.engine.explain_trade(tid)
        assert exp.action == "BUY"

    def test_explanation_regime_correct(self):
        self.bus.publish(_signal())
        tid = self._get_trade_id()
        exp = self.engine.explain_trade(tid)
        assert exp.regime == "bullish"

    def test_explanation_confidence_correct(self):
        self.bus.publish(_signal(confidence=0.92))
        tid = self._get_trade_id()
        exp = self.engine.explain_trade(tid)
        assert exp.signal_confidence == pytest.approx(0.92)

    def test_explanation_risk_decision_approved(self):
        self.bus.publish(_signal())
        self.bus.publish(_risk(decision="APPROVED"))
        tid = self._get_trade_id()
        exp = self.engine.explain_trade(tid)
        assert exp.risk_decision == "APPROVED"

    def test_explanation_risk_decision_blocked(self):
        self.bus.publish(_signal())
        self.bus.publish(_risk(decision="BLOCKED", approved=0))
        tid = self._get_trade_id()
        exp = self.engine.explain_trade(tid)
        assert exp.risk_decision == "BLOCKED"

    def test_explanation_risk_score_zero_when_fully_approved(self):
        self.bus.publish(_signal())
        self.bus.publish(_risk(approved=10, original=10))
        tid = self._get_trade_id()
        exp = self.engine.explain_trade(tid)
        assert exp.risk_score == pytest.approx(0.0)

    def test_explanation_risk_score_half_when_reduced(self):
        self.bus.publish(_signal())
        self.bus.publish(_risk(approved=5, original=10))
        tid = self._get_trade_id()
        exp = self.engine.explain_trade(tid)
        assert exp.risk_score == pytest.approx(0.5)

    def test_explanation_fill_price_correct(self):
        self.bus.publish(_signal())
        self.bus.publish(_fill(price=151.5))
        tid = self._get_trade_id()
        exp = self.engine.explain_trade(tid)
        assert exp.fill_price == pytest.approx(151.5)

    def test_explanation_fill_quantity_correct(self):
        self.bus.publish(_signal())
        self.bus.publish(_fill(qty=7))
        tid = self._get_trade_id()
        exp = self.engine.explain_trade(tid)
        assert exp.fill_quantity == 7

    def test_explanation_no_fill_when_blocked(self):
        self.bus.publish(_signal())
        self.bus.publish(_risk(decision="BLOCKED", approved=0))
        tid = self._get_trade_id()
        exp = self.engine.explain_trade(tid)
        assert exp.fill_price is None
        assert exp.fill_quantity == 0

    def test_explanation_raw_records_populated(self):
        self.bus.publish(_signal())
        self.bus.publish(_risk())
        self.bus.publish(_fill())
        tid = self._get_trade_id()
        exp = self.engine.explain_trade(tid)
        assert len(exp.raw_records) >= 3

    def test_execution_reason_contains_fill_info(self):
        self.bus.publish(_signal())
        self.bus.publish(_fill(qty=10, price=150.0))
        tid = self._get_trade_id()
        exp = self.engine.explain_trade(tid)
        assert "10" in exp.execution_reason
        assert "150" in exp.execution_reason


# ──────────────────────────────────────────────────────────────────────
# explain_all_trades
# ──────────────────────────────────────────────────────────────────────

class TestExplainAllTrades:
    def test_empty_journal_returns_empty_list(self):
        journal = DecisionJournal()
        engine = TradeExplainabilityEngine(journal)
        assert engine.explain_all_trades() == []

    def test_returns_one_explanation_per_trade(self):
        bus = EventBus()
        journal = DecisionJournal(bus)
        engine = TradeExplainabilityEngine(journal)

        # Trade 1 (strategy s1)
        bus.publish(SignalEvent(
            symbol="AAPL", strategy_name="s1", action="BUY",
            confidence=0.8, timeframe="1m", current_price=Decimal("150"),
            atr=Decimal("2"), stop_price=Decimal("145"),
            regime="bull", regime_strength=0.7,
        ))
        # Trade 2 (strategy s2)
        bus.publish(SignalEvent(
            symbol="GOOG", strategy_name="s2", action="SELL",
            confidence=0.7, timeframe="1m", current_price=Decimal("2000"),
            atr=Decimal("10"), stop_price=Decimal("2010"),
            regime="bear", regime_strength=0.6,
        ))
        explanations = engine.explain_all_trades()
        assert len(explanations) == 2

    def test_flat_signals_excluded(self):
        bus = EventBus()
        journal = DecisionJournal(bus)
        engine = TradeExplainabilityEngine(journal)
        bus.publish(_signal(action="FLAT"))
        assert engine.explain_all_trades() == []

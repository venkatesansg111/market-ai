"""Unit tests for observability.decision_journal — DecisionJournal."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from observability.decision_journal import DecisionJournal, DecisionRecord
from streaming.event_bus import EventBus
from streaming.event_models import (
    CandleEvent, FillEvent, IndicatorEvent, OrderEvent,
    PortfolioEvent, RiskEvent, SignalEvent, TickEvent,
)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

_TS = datetime(2024, 1, 15, 9, 30, 0)


def _signal(action: str = "BUY", strategy: str = "strat_a") -> SignalEvent:
    return SignalEvent(
        symbol="AAPL", strategy_name=strategy, action=action,
        confidence=0.8, timeframe="1m", current_price=Decimal("150"),
        atr=Decimal("2"), stop_price=Decimal("145"),
        regime="bullish", regime_strength=0.7,
    )


def _risk(decision: str = "APPROVED", strategy: str = "strat_a") -> RiskEvent:
    return RiskEvent(
        symbol="AAPL", strategy_name=strategy,
        decision=decision, approved_quantity=10, original_quantity=10,
        reason="ok",
    )


def _order(strategy: str = "strat_a") -> OrderEvent:
    return OrderEvent(
        order_id="ord-1", symbol="AAPL", action="BUY",
        quantity=10, order_type="MARKET", strategy_name=strategy,
    )


def _fill(action: str = "BUY", strategy: str = "strat_a") -> FillEvent:
    return FillEvent(
        order_id="ord-1", symbol="AAPL", quantity=10,
        price=Decimal("150"), strategy_name=strategy,
        action=action, commission=Decimal("0.5"),
    )


def _portfolio() -> PortfolioEvent:
    return PortfolioEvent(
        equity=Decimal("100000"), cash=Decimal("98500"),
        unrealized_pnl=Decimal("0"), realized_pnl=Decimal("0"),
        daily_pnl=Decimal("0"), current_drawdown_pct=0.0,
    )


def _candle() -> CandleEvent:
    return CandleEvent(
        symbol="AAPL", timeframe="1m",
        open=Decimal("150"), high=Decimal("151"), low=Decimal("149"), close=Decimal("150"),
        volume=1000, is_closed=True,
    )


def _indicator() -> IndicatorEvent:
    return IndicatorEvent(
        symbol="AAPL", timeframe="1m", close=150.0, high=151.0, low=149.0,
        volume=1000, is_warm=True,
    )


# ──────────────────────────────────────────────────────────────────────
# Manual record()
# ──────────────────────────────────────────────────────────────────────

class TestManualRecord:
    def test_record_appends_entry(self):
        journal = DecisionJournal()
        sig = _signal()
        rec = journal.record("signal", "AAPL", sig)
        assert isinstance(rec, DecisionRecord)
        assert journal.record_count == 1

    def test_record_type_stored(self):
        journal = DecisionJournal()
        sig = _signal()
        rec = journal.record("signal", "AAPL", sig)
        assert rec.decision_type == "signal"

    def test_record_with_trade_id_indexed(self):
        journal = DecisionJournal()
        sig = _signal()
        journal.record("signal", "AAPL", sig, trade_id="t-1")
        history = journal.get_trade_history("t-1")
        assert len(history) == 1

    def test_record_with_strategy_indexed(self):
        journal = DecisionJournal()
        sig = _signal(strategy="mom")
        journal.record("signal", "AAPL", sig, strategy_name="mom")
        decisions = journal.get_strategy_decisions("mom")
        assert len(decisions) == 1

    def test_record_count_increments(self):
        journal = DecisionJournal()
        for _ in range(5):
            journal.record("signal", "AAPL", _signal())
        assert journal.record_count == 5

    def test_get_all_records_no_filter(self):
        journal = DecisionJournal()
        journal.record("signal", "AAPL", _signal())
        journal.record("risk", "AAPL", _risk())
        assert len(journal.get_all_records()) == 2

    def test_get_all_records_filtered(self):
        journal = DecisionJournal()
        journal.record("signal", "AAPL", _signal())
        journal.record("risk", "AAPL", _risk())
        recs = journal.get_all_records("signal")
        assert len(recs) == 1
        assert recs[0].decision_type == "signal"


# ──────────────────────────────────────────────────────────────────────
# Event-bus wiring
# ──────────────────────────────────────────────────────────────────────

class TestEventBusWiring:
    def setup_method(self):
        self.bus = EventBus()
        self.journal = DecisionJournal(self.bus)

    def test_closed_candle_recorded(self):
        self.bus.publish(_candle())
        recs = self.journal.get_all_records("candle")
        assert len(recs) == 1

    def test_open_candle_not_recorded(self):
        c = CandleEvent(
            symbol="AAPL", timeframe="1m",
            open=Decimal("150"), high=Decimal("151"), low=Decimal("149"), close=Decimal("150"),
            volume=1000, is_closed=False,
        )
        self.bus.publish(c)
        assert self.journal.get_all_records("candle") == []

    def test_indicator_recorded(self):
        self.bus.publish(_indicator())
        recs = self.journal.get_all_records("indicator")
        assert len(recs) == 1

    def test_buy_signal_creates_trade_id(self):
        self.bus.publish(_signal(action="BUY"))
        recs = self.journal.get_all_records("signal")
        assert len(recs) == 1
        assert recs[0].trade_id is not None

    def test_flat_signal_not_recorded(self):
        self.bus.publish(_signal(action="FLAT"))
        assert self.journal.get_all_records("signal") == []

    def test_risk_event_recorded(self):
        self.bus.publish(_signal(action="BUY"))
        self.bus.publish(_risk())
        recs = self.journal.get_all_records("risk")
        assert len(recs) == 1

    def test_order_event_recorded(self):
        self.bus.publish(_signal(action="BUY"))
        self.bus.publish(_order())
        recs = self.journal.get_all_records("order")
        assert len(recs) == 1

    def test_fill_event_recorded(self):
        self.bus.publish(_signal(action="BUY"))
        self.bus.publish(_fill())
        recs = self.journal.get_all_records("fill")
        assert len(recs) == 1

    def test_portfolio_event_recorded(self):
        self.bus.publish(_portfolio())
        recs = self.journal.get_all_records("portfolio")
        assert len(recs) == 1

    def test_sell_signal_creates_trade_id(self):
        self.bus.publish(_signal(action="SELL"))
        recs = self.journal.get_all_records("signal")
        assert recs[0].trade_id is not None


# ──────────────────────────────────────────────────────────────────────
# Trade chain linkage
# ──────────────────────────────────────────────────────────────────────

class TestTradeChainLinkage:
    def test_signal_risk_fill_share_trade_id(self):
        bus = EventBus()
        journal = DecisionJournal(bus)
        bus.publish(_signal(action="BUY"))
        bus.publish(_risk())
        bus.publish(_fill())
        sig_rec = journal.get_all_records("signal")[0]
        risk_rec = journal.get_all_records("risk")[0]
        fill_rec = journal.get_all_records("fill")[0]
        assert sig_rec.trade_id == risk_rec.trade_id == fill_rec.trade_id

    def test_get_trade_history_returns_all_linked_records(self):
        bus = EventBus()
        journal = DecisionJournal(bus)
        bus.publish(_signal(action="BUY"))
        bus.publish(_risk())
        bus.publish(_order())
        bus.publish(_fill())
        sig_rec = journal.get_all_records("signal")[0]
        history = journal.get_trade_history(sig_rec.trade_id)
        types = {r.decision_type for r in history}
        assert {"signal", "risk", "order", "fill"} == types

    def test_two_signals_generate_two_trade_ids(self):
        bus = EventBus()
        journal = DecisionJournal(bus)
        bus.publish(_signal(action="BUY", strategy="s1"))
        bus.publish(_fill(strategy="s1"))
        bus.publish(_signal(action="BUY", strategy="s2"))
        bus.publish(_fill(strategy="s2"))
        recs = journal.get_all_records("signal")
        assert recs[0].trade_id != recs[1].trade_id

    def test_strategy_index_groups_by_strategy(self):
        bus = EventBus()
        journal = DecisionJournal(bus)
        bus.publish(_signal(action="BUY", strategy="mom"))
        bus.publish(_signal(action="SELL", strategy="mean_rev"))
        assert len(journal.get_strategy_decisions("mom")) == 1
        assert len(journal.get_strategy_decisions("mean_rev")) == 1

    def test_unknown_trade_id_returns_empty(self):
        journal = DecisionJournal()
        assert journal.get_trade_history("no-such-id") == []

    def test_unknown_strategy_returns_empty(self):
        journal = DecisionJournal()
        assert journal.get_strategy_decisions("ghost") == []


# ──────────────────────────────────────────────────────────────────────
# Clear
# ──────────────────────────────────────────────────────────────────────

class TestClear:
    def test_clear_resets_record_count(self):
        journal = DecisionJournal()
        journal.record("signal", "AAPL", _signal())
        journal.clear()
        assert journal.record_count == 0

    def test_clear_resets_trade_index(self):
        bus = EventBus()
        journal = DecisionJournal(bus)
        bus.publish(_signal(action="BUY"))
        tid = journal.get_all_records("signal")[0].trade_id
        journal.clear()
        assert journal.get_trade_history(tid) == []

"""Unit tests for streaming.execution_pipeline — ExecutionPipeline."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from execution.execution_engine import ExecutionEngine
from execution.execution_models import ExecutionResult, Fill, OrderSide, OrderStatus, OrderType
from risk.portfolio_state import PortfolioStateEngine
from risk.risk_gate import RiskGate
from risk.risk_models import (
    RiskDecision,
    RiskDecisionType,
    RiskParams,
    SizingMethod,
)
from streaming.event_bus import EventBus
from streaming.event_models import (
    FillEvent, OrderEvent, PortfolioEvent, RiskEvent, SignalEvent,
)
from streaming.execution_pipeline import ExecutionPipeline


# ──────────────────────────────────────────────────────────────────────
# Helpers / Fixtures
# ──────────────────────────────────────────────────────────────────────

def _params() -> RiskParams:
    return RiskParams(
        sizing_method=SizingMethod.FIXED_FRACTIONAL,
        risk_per_trade_pct=1.0,
        max_drawdown_pct=15.0,
        daily_loss_limit_pct=3.0,
        max_per_asset_pct=20.0,
        max_per_strategy_pct=50.0,
        max_leverage=1.0,
    )


def _signal(
    symbol: str = "AAPL",
    action: str = "BUY",
    confidence: float = 0.8,
    price: float = 150.0,
    qty: int = 10,
) -> SignalEvent:
    return SignalEvent(
        symbol=symbol,
        strategy_name="test_strat",
        action=action,
        confidence=confidence,
        timeframe="1m",
        current_price=Decimal(str(price)),
        atr=Decimal("2.00"),
        stop_price=Decimal(str(price - 5)),
        regime="trending",
        regime_strength=0.7,
    )


def _approved_decision(qty: int = 10) -> RiskDecision:
    return RiskDecision(
        symbol="AAPL",
        strategy_name="test_strat",
        decision=RiskDecisionType.APPROVED,
        approved_quantity=qty,
        original_quantity=qty,
        reason="approved",
    )


def _blocked_decision() -> RiskDecision:
    return RiskDecision(
        symbol="AAPL",
        strategy_name="test_strat",
        decision=RiskDecisionType.BLOCKED,
        approved_quantity=0,
        original_quantity=10,
        reason="max drawdown exceeded",
    )


def _execution_result(qty: int = 10, price: float = 150.0) -> ExecutionResult:
    order_id = "ord-001"
    fill = Fill(
        fill_id="fill-001",
        order_id=order_id,
        quantity=qty,
        price=Decimal(str(price)),
        commission=Decimal("0.50"),
        timestamp=datetime.utcnow(),
    )
    return ExecutionResult(
        order_id=order_id,
        symbol="AAPL",
        status=OrderStatus.FILLED,
        fills=[fill],
    )


def _build_pipeline(
    risk_decision: RiskDecision | None = None,
    exec_result: ExecutionResult | None = None,
    initial_cash: float = 100_000.0,
) -> tuple[EventBus, ExecutionPipeline]:
    bus = EventBus()
    params = _params()

    # Mock risk gate
    risk_gate = MagicMock(spec=RiskGate)
    risk_gate.evaluate.return_value = risk_decision or _approved_decision()

    # Mock execution engine
    exec_engine = MagicMock(spec=ExecutionEngine)
    exec_engine.execute.return_value = exec_result or _execution_result()

    # Real portfolio state
    portfolio = PortfolioStateEngine(initial_cash=Decimal(str(initial_cash)))

    pipeline = ExecutionPipeline(
        event_bus=bus,
        execution_engine=exec_engine,
        risk_gate=risk_gate,
        portfolio_state=portfolio,
        params=params,
    )
    return bus, pipeline


# ──────────────────────────────────────────────────────────────────────
# BUY signal flows through
# ──────────────────────────────────────────────────────────────────────

class TestBuySignalFlow:
    def setup_method(self):
        self.bus, self.pipeline = _build_pipeline()
        self.risk_events: list[RiskEvent] = []
        self.order_events: list[OrderEvent] = []
        self.fill_events: list[FillEvent] = []
        self.portfolio_events: list[PortfolioEvent] = []
        self.bus.subscribe(RiskEvent, self.risk_events.append)
        self.bus.subscribe(OrderEvent, self.order_events.append)
        self.bus.subscribe(FillEvent, self.fill_events.append)
        self.bus.subscribe(PortfolioEvent, self.portfolio_events.append)
        self.bus.publish(_signal(action="BUY"))

    def test_risk_event_emitted(self):
        assert len(self.risk_events) == 1

    def test_risk_event_approved(self):
        assert self.risk_events[0].decision == "APPROVED"

    def test_order_event_emitted(self):
        assert len(self.order_events) == 1

    def test_order_event_action_is_buy(self):
        assert self.order_events[0].action == "BUY"

    def test_fill_event_emitted(self):
        assert len(self.fill_events) == 1

    def test_fill_event_quantity(self):
        assert self.fill_events[0].quantity == 10

    def test_portfolio_event_emitted(self):
        assert len(self.portfolio_events) == 1

    def test_portfolio_event_equity_is_positive(self):
        assert self.portfolio_events[0].equity > 0

    def test_pipeline_filled_count(self):
        assert self.pipeline.filled == 1

    def test_pipeline_processed_count(self):
        assert self.pipeline.processed == 1


# ──────────────────────────────────────────────────────────────────────
# FLAT signals are skipped
# ──────────────────────────────────────────────────────────────────────

class TestFlatSignalSkipped:
    def setup_method(self):
        self.bus, self.pipeline = _build_pipeline()
        self.all_events: list = []
        self.bus.subscribe(RiskEvent, self.all_events.append)
        self.bus.subscribe(OrderEvent, self.all_events.append)
        self.bus.subscribe(FillEvent, self.all_events.append)
        self.bus.subscribe(PortfolioEvent, self.all_events.append)
        self.bus.publish(_signal(action="FLAT"))

    def test_no_events_emitted_for_flat(self):
        assert self.all_events == []

    def test_processed_but_not_filled(self):
        assert self.pipeline.processed == 1
        assert self.pipeline.filled == 0

    def test_not_blocked_either(self):
        assert self.pipeline.blocked == 0


# ──────────────────────────────────────────────────────────────────────
# Blocked by risk gate
# ──────────────────────────────────────────────────────────────────────

class TestBlockedSignal:
    def setup_method(self):
        self.bus, self.pipeline = _build_pipeline(risk_decision=_blocked_decision())
        self.risk_events: list[RiskEvent] = []
        self.order_events: list[OrderEvent] = []
        self.bus.subscribe(RiskEvent, self.risk_events.append)
        self.bus.subscribe(OrderEvent, self.order_events.append)
        self.bus.publish(_signal(action="BUY"))

    def test_risk_event_emitted_with_blocked_decision(self):
        assert len(self.risk_events) == 1
        assert self.risk_events[0].decision == "BLOCKED"

    def test_no_order_event_when_blocked(self):
        assert self.order_events == []

    def test_blocked_count_increments(self):
        assert self.pipeline.blocked == 1

    def test_filled_count_stays_zero(self):
        assert self.pipeline.filled == 0


# ──────────────────────────────────────────────────────────────────────
# SELL signal
# ──────────────────────────────────────────────────────────────────────

class TestSellSignalFlow:
    def test_sell_signal_produces_fill_event_with_sell_action(self):
        bus, pipeline = _build_pipeline()
        fills: list[FillEvent] = []
        bus.subscribe(FillEvent, fills.append)
        bus.publish(_signal(action="SELL"))
        assert len(fills) == 1
        assert fills[0].action == "SELL"


# ──────────────────────────────────────────────────────────────────────
# Execution failure handling
# ──────────────────────────────────────────────────────────────────────

class TestExecutionFailure:
    def test_execution_exception_does_not_propagate(self):
        bus = EventBus()
        params = _params()

        risk_gate = MagicMock(spec=RiskGate)
        risk_gate.evaluate.return_value = _approved_decision()

        exec_engine = MagicMock(spec=ExecutionEngine)
        exec_engine.execute.side_effect = RuntimeError("broker down")

        portfolio = PortfolioStateEngine(initial_cash=Decimal("100000"))
        pipeline = ExecutionPipeline(
            event_bus=bus,
            execution_engine=exec_engine,
            risk_gate=risk_gate,
            portfolio_state=portfolio,
            params=params,
        )
        # Should not raise
        bus.publish(_signal(action="BUY"))
        assert pipeline.filled == 0


# ──────────────────────────────────────────────────────────────────────
# No fills in execution result
# ──────────────────────────────────────────────────────────────────────

class TestNoFills:
    def test_no_fill_events_when_result_has_no_fills(self):
        empty_result = ExecutionResult(
            order_id="ord-empty",
            symbol="AAPL",
            status=OrderStatus.SUBMITTED,
            fills=[],
        )
        bus, pipeline = _build_pipeline(exec_result=empty_result)
        fill_events: list[FillEvent] = []
        port_events: list[PortfolioEvent] = []
        bus.subscribe(FillEvent, fill_events.append)
        bus.subscribe(PortfolioEvent, port_events.append)
        bus.publish(_signal(action="BUY"))
        assert fill_events == []
        assert port_events == []

    def test_filled_count_stays_zero_when_no_fills(self):
        empty_result = ExecutionResult(
            order_id="ord-empty",
            symbol="AAPL",
            status=OrderStatus.SUBMITTED,
            fills=[],
        )
        bus, pipeline = _build_pipeline(exec_result=empty_result)
        bus.publish(_signal(action="BUY"))
        assert pipeline.filled == 0


# ──────────────────────────────────────────────────────────────────────
# Multiple signals
# ──────────────────────────────────────────────────────────────────────

class TestMultipleSignals:
    def test_multiple_signals_processed_in_order(self):
        bus, pipeline = _build_pipeline()
        fills: list[FillEvent] = []
        bus.subscribe(FillEvent, fills.append)
        for _ in range(5):
            bus.publish(_signal(action="BUY"))
        assert pipeline.processed == 5
        assert len(fills) == 5

    def test_portfolio_event_emitted_after_each_fill(self):
        bus, pipeline = _build_pipeline()
        port_events: list[PortfolioEvent] = []
        bus.subscribe(PortfolioEvent, port_events.append)
        for _ in range(3):
            bus.publish(_signal(action="BUY"))
        assert len(port_events) == 3

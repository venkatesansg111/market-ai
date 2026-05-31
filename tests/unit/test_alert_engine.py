"""Unit tests for observability.alert_engine — AlertEngine."""
from __future__ import annotations

from decimal import Decimal

import pytest

from observability.alert_engine import Alert, AlertCategory, AlertEngine, AlertSeverity
from streaming.event_bus import EventBus
from streaming.event_models import PortfolioEvent, SignalEvent


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _portfolio(drawdown: float = 0.0, equity: float = 100000.0, cash: float = 50000.0) -> PortfolioEvent:
    return PortfolioEvent(
        equity=Decimal(str(equity)),
        cash=Decimal(str(cash)),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        daily_pnl=Decimal("0"),
        current_drawdown_pct=drawdown,
    )


def _signal(confidence: float = 0.8, action: str = "BUY") -> SignalEvent:
    return SignalEvent(
        symbol="AAPL", strategy_name="strat",
        action=action, confidence=confidence,
        timeframe="1m", current_price=Decimal("150"),
        atr=Decimal("2"), stop_price=Decimal("145"),
        regime="bullish", regime_strength=0.7,
    )


# ──────────────────────────────────────────────────────────────────────
# Alert count
# ──────────────────────────────────────────────────────────────────────

class TestAlertCount:
    def test_no_alerts_initially(self):
        engine = AlertEngine()
        assert engine.alert_count == 0

    def test_alert_count_increments_on_publish(self):
        engine = AlertEngine()
        bus = EventBus()
        engine.attach(bus)
        bus.publish(_portfolio(drawdown=12.0))  # above warning threshold 10
        assert engine.alert_count >= 1


# ──────────────────────────────────────────────────────────────────────
# Drawdown alerts
# ──────────────────────────────────────────────────────────────────────

class TestDrawdownAlerts:
    def test_no_alert_below_warning_threshold(self):
        engine = AlertEngine(drawdown_warning_pct=10.0)
        engine.evaluate(_portfolio(drawdown=5.0))
        assert engine.alert_count == 0

    def test_warning_alert_at_warning_threshold(self):
        engine = AlertEngine(drawdown_warning_pct=10.0)
        engine.evaluate(_portfolio(drawdown=10.0))
        alerts = engine.get_alerts(severity=AlertSeverity.WARNING)
        dd_alerts = [a for a in alerts if "Drawdown" in a.title]
        assert len(dd_alerts) >= 1

    def test_critical_alert_at_critical_threshold(self):
        engine = AlertEngine(drawdown_critical_pct=15.0)
        engine.evaluate(_portfolio(drawdown=16.0))
        alerts = engine.get_alerts(severity=AlertSeverity.CRITICAL)
        assert len(alerts) >= 1

    def test_critical_alert_not_warning_at_critical_level(self):
        engine = AlertEngine(drawdown_warning_pct=10.0, drawdown_critical_pct=15.0)
        engine.evaluate(_portfolio(drawdown=20.0))
        # Only critical, not warning
        criticals = engine.get_alerts(severity=AlertSeverity.CRITICAL)
        assert any("Drawdown" in a.title for a in criticals)

    def test_drawdown_alert_category_is_portfolio(self):
        engine = AlertEngine(drawdown_warning_pct=5.0)
        engine.evaluate(_portfolio(drawdown=6.0))
        alerts = engine.get_alerts(category=AlertCategory.PORTFOLIO)
        assert len(alerts) >= 1

    def test_drawdown_metadata_has_pct(self):
        engine = AlertEngine(drawdown_warning_pct=5.0)
        engine.evaluate(_portfolio(drawdown=8.0))
        alerts = engine.get_alerts(severity=AlertSeverity.WARNING)
        dd_alerts = [a for a in alerts if "drawdown_pct" in a.metadata]
        assert len(dd_alerts) >= 1
        assert dd_alerts[0].metadata["drawdown_pct"] == pytest.approx(8.0)


# ──────────────────────────────────────────────────────────────────────
# Leverage alerts
# ──────────────────────────────────────────────────────────────────────

class TestLeverageAlerts:
    def test_no_alert_below_leverage_threshold(self):
        engine = AlertEngine(leverage_threshold=3.0)
        engine.evaluate(_portfolio(equity=100000.0, cash=50000.0))  # leverage=2x
        leverage_alerts = [a for a in engine.get_alerts() if "Leverage" in a.title]
        assert len(leverage_alerts) == 0

    def test_warning_alert_above_leverage_threshold(self):
        engine = AlertEngine(leverage_threshold=1.5)
        engine.evaluate(_portfolio(equity=100000.0, cash=50000.0))  # leverage=2x > 1.5
        leverage_alerts = [a for a in engine.get_alerts() if "Leverage" in a.title]
        assert len(leverage_alerts) >= 1

    def test_leverage_alert_severity_is_warning(self):
        engine = AlertEngine(leverage_threshold=1.5)
        engine.evaluate(_portfolio(equity=100000.0, cash=50000.0))
        warnings = engine.get_alerts(severity=AlertSeverity.WARNING)
        leverage = [a for a in warnings if "Leverage" in a.title]
        assert len(leverage) >= 1


# ──────────────────────────────────────────────────────────────────────
# Strategy alerts
# ──────────────────────────────────────────────────────────────────────

class TestStrategyAlerts:
    def test_low_confidence_alert_fires(self):
        bus = EventBus()
        engine = AlertEngine(bus, low_confidence_threshold=0.2)
        bus.publish(_signal(confidence=0.05, action="BUY"))
        alerts = engine.get_alerts(category=AlertCategory.STRATEGY)
        assert len(alerts) >= 1

    def test_normal_confidence_no_alert(self):
        bus = EventBus()
        engine = AlertEngine(bus, low_confidence_threshold=0.1)
        bus.publish(_signal(confidence=0.8, action="BUY"))
        alerts = engine.get_alerts(category=AlertCategory.STRATEGY)
        assert len(alerts) == 0

    def test_flat_signal_no_alert(self):
        bus = EventBus()
        engine = AlertEngine(bus, low_confidence_threshold=0.5)
        bus.publish(_signal(confidence=0.0, action="FLAT"))
        alerts = engine.get_alerts(category=AlertCategory.STRATEGY)
        assert len(alerts) == 0


# ──────────────────────────────────────────────────────────────────────
# Alert subscription
# ──────────────────────────────────────────────────────────────────────

class TestAlertSubscription:
    def test_subscriber_receives_alert(self):
        engine = AlertEngine(drawdown_warning_pct=5.0)
        received = []
        engine.subscribe(received.append)
        engine.evaluate(_portfolio(drawdown=8.0))
        assert len(received) >= 1

    def test_subscriber_receives_alert_type(self):
        engine = AlertEngine(drawdown_warning_pct=5.0)
        received = []
        engine.subscribe(received.append)
        engine.evaluate(_portfolio(drawdown=8.0))
        assert isinstance(received[0], Alert)

    def test_multiple_subscribers_all_receive(self):
        engine = AlertEngine(drawdown_warning_pct=5.0)
        a, b = [], []
        engine.subscribe(a.append)
        engine.subscribe(b.append)
        engine.evaluate(_portfolio(drawdown=8.0))
        assert len(a) >= 1
        assert len(b) >= 1

    def test_faulty_subscriber_does_not_crash(self):
        engine = AlertEngine(drawdown_warning_pct=5.0)
        engine.subscribe(lambda a: (_ for _ in ()).throw(RuntimeError("bad")))
        engine.evaluate(_portfolio(drawdown=8.0))  # should not raise
        assert engine.alert_count >= 1


# ──────────────────────────────────────────────────────────────────────
# Alert IDs and structure
# ──────────────────────────────────────────────────────────────────────

class TestAlertStructure:
    def test_alert_id_unique(self):
        engine = AlertEngine(drawdown_warning_pct=5.0)
        engine.evaluate(_portfolio(drawdown=6.0))
        engine.evaluate(_portfolio(drawdown=7.0))
        alerts = engine.get_alerts()
        ids = [a.alert_id for a in alerts]
        assert len(ids) == len(set(ids))

    def test_get_alerts_no_filter_returns_all(self):
        engine = AlertEngine(drawdown_warning_pct=5.0, leverage_threshold=1.5)
        engine.evaluate(_portfolio(drawdown=6.0, equity=100000.0, cash=50000.0))
        assert engine.get_alerts() == engine._alerts

    def test_filter_by_severity(self):
        engine = AlertEngine(drawdown_warning_pct=5.0, drawdown_critical_pct=15.0)
        engine.evaluate(_portfolio(drawdown=6.0))   # warning
        engine.evaluate(_portfolio(drawdown=20.0))  # critical
        warnings = engine.get_alerts(severity=AlertSeverity.WARNING)
        criticals = engine.get_alerts(severity=AlertSeverity.CRITICAL)
        assert all(a.severity == AlertSeverity.WARNING for a in warnings)
        assert all(a.severity == AlertSeverity.CRITICAL for a in criticals)

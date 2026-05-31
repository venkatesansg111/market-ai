"""Phase 10 — Alerting Engine."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Optional

from streaming.event_bus import EventBus
from streaming.event_models import FillEvent, PortfolioEvent, SignalEvent


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertCategory(str, Enum):
    PORTFOLIO = "portfolio"
    STRATEGY = "strategy"
    EXECUTION = "execution"
    INFRASTRUCTURE = "infrastructure"


@dataclass
class Alert:
    alert_id: str
    severity: AlertSeverity
    category: AlertCategory
    title: str
    message: str
    timestamp: datetime
    metadata: dict = field(default_factory=dict)


AlertHandler = Callable[[Alert], None]


class AlertEngine:
    """Evaluates threshold rules and publishes alerts."""

    def __init__(
        self,
        bus: EventBus | None = None,
        drawdown_warning_pct: float = 10.0,
        drawdown_critical_pct: float = 15.0,
        daily_loss_pct: float = 3.0,
        leverage_threshold: float = 2.0,
        low_confidence_threshold: float = 0.1,
    ) -> None:
        self._drawdown_warning = drawdown_warning_pct
        self._drawdown_critical = drawdown_critical_pct
        self._daily_loss = daily_loss_pct
        self._leverage_threshold = leverage_threshold
        self._low_confidence_threshold = low_confidence_threshold
        self._alerts: list[Alert] = []
        self._handlers: list[AlertHandler] = []
        self._lock = threading.RLock()
        self._alert_seq = 0
        if bus is not None:
            self.attach(bus)

    def attach(self, bus: EventBus) -> None:
        bus.subscribe(PortfolioEvent, self._on_portfolio)
        bus.subscribe(FillEvent, self._on_fill)
        bus.subscribe(SignalEvent, self._on_signal)

    def subscribe(self, handler: AlertHandler) -> None:
        with self._lock:
            self._handlers.append(handler)

    def publish_alert(self, alert: Alert) -> None:
        with self._lock:
            self._alerts.append(alert)
            handlers = list(self._handlers)
        for h in handlers:
            try:
                h(alert)
            except Exception:
                pass

    def _make_alert(
        self,
        severity: AlertSeverity,
        category: AlertCategory,
        title: str,
        message: str,
        metadata: dict | None = None,
    ) -> Alert:
        with self._lock:
            seq = self._alert_seq
            self._alert_seq += 1
        return Alert(
            alert_id=f"alert-{seq:06d}",
            severity=severity,
            category=category,
            title=title,
            message=message,
            timestamp=datetime.utcnow(),
            metadata=metadata or {},
        )

    def _on_portfolio(self, e: PortfolioEvent) -> None:
        dd = e.current_drawdown_pct
        if dd >= self._drawdown_critical:
            self.publish_alert(self._make_alert(
                AlertSeverity.CRITICAL, AlertCategory.PORTFOLIO,
                "Drawdown Critical",
                f"Portfolio drawdown {dd:.2f}% exceeded critical threshold {self._drawdown_critical:.2f}%",
                {"drawdown_pct": dd},
            ))
        elif dd >= self._drawdown_warning:
            self.publish_alert(self._make_alert(
                AlertSeverity.WARNING, AlertCategory.PORTFOLIO,
                "Drawdown Warning",
                f"Portfolio drawdown {dd:.2f}% exceeded warning threshold {self._drawdown_warning:.2f}%",
                {"drawdown_pct": dd},
            ))

        if e.cash > 0:
            leverage = float(e.equity / e.cash)
            if leverage > self._leverage_threshold:
                self.publish_alert(self._make_alert(
                    AlertSeverity.WARNING, AlertCategory.PORTFOLIO,
                    "High Leverage",
                    f"Leverage {leverage:.2f}x exceeds threshold {self._leverage_threshold:.2f}x",
                    {"leverage": leverage},
                ))

    def _on_fill(self, e: FillEvent) -> None:
        pass  # slippage alerts require expected-price context not available here

    def _on_signal(self, e: SignalEvent) -> None:
        if e.action != "FLAT" and e.confidence < self._low_confidence_threshold:
            self.publish_alert(self._make_alert(
                AlertSeverity.INFO, AlertCategory.STRATEGY,
                "Low Confidence Signal",
                f"Signal from {e.strategy_name} for {e.symbol} has low confidence {e.confidence:.3f}",
                {"symbol": e.symbol, "strategy": e.strategy_name, "confidence": e.confidence},
            ))

    def evaluate(self, portfolio: Optional[PortfolioEvent] = None) -> list[Alert]:
        if portfolio is not None:
            self._on_portfolio(portfolio)
        with self._lock:
            return list(self._alerts)

    def get_alerts(
        self,
        severity: Optional[AlertSeverity] = None,
        category: Optional[AlertCategory] = None,
    ) -> list[Alert]:
        with self._lock:
            result = list(self._alerts)
        if severity:
            result = [a for a in result if a.severity == severity]
        if category:
            result = [a for a in result if a.category == category]
        return result

    @property
    def alert_count(self) -> int:
        with self._lock:
            return len(self._alerts)

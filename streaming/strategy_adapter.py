"""Phase 9 — Strategy engine in event-driven mode."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional

from streaming.event_bus import EventBus
from streaming.event_models import IndicatorEvent, SignalEvent

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Strategy handler interface
# ──────────────────────────────────────────────────────────────────────

class StrategyHandler(ABC):
    """
    Single-responsibility unit that converts indicator data into a signal.

    Each implementation is isolated and stateless (or carries only its own
    state), enabling multiple strategies to run concurrently on the same
    IndicatorEvent stream.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def on_indicators(self, event: IndicatorEvent) -> Optional[SignalEvent]:
        """Return a SignalEvent or None if no signal."""
        ...

    def reset(self) -> None:
        """Override to reset internal state (e.g. at session start)."""
        pass


# ──────────────────────────────────────────────────────────────────────
# Built-in strategy: EMA crossover
# ──────────────────────────────────────────────────────────────────────

class EMACrossoverStrategy(StrategyHandler):
    """
    Buy when fast EMA crosses above slow EMA; sell on reverse.

    - Only acts on warm IndicatorEvents (is_warm=True).
    - Emits FLAT when EMAs are equal or neither cross has occurred yet.
    - Carries prev_signal state to avoid re-firing on unchanged trend.
    """

    def __init__(self, strategy_name: str = "ema_crossover") -> None:
        self._name = strategy_name
        self._prev_action: Optional[str] = None

    @property
    def name(self) -> str:
        return self._name

    def on_indicators(self, event: IndicatorEvent) -> Optional[SignalEvent]:
        if not event.is_warm:
            return None
        if event.ema_fast is None or event.ema_slow is None:
            return None

        if event.ema_fast > event.ema_slow:
            action = "BUY"
        elif event.ema_fast < event.ema_slow:
            action = "SELL"
        else:
            action = "FLAT"

        # Only emit when action changes (suppress repeated identical signals)
        if action == self._prev_action:
            return None

        self._prev_action = action
        confidence = abs(event.ema_fast - event.ema_slow) / max(event.ema_slow, 1e-9)
        confidence = min(1.0, confidence * 10)  # normalise to 0-1

        return SignalEvent(
            symbol=event.symbol,
            strategy_name=self._name,
            action=action,
            confidence=confidence,
            timeframe=event.timeframe,
            timestamp=event.timestamp,
            current_price=Decimal(str(round(event.close, 4))),
            atr=Decimal(str(round(event.atr, 4))) if event.atr else None,
        )

    def reset(self) -> None:
        self._prev_action = None


# ──────────────────────────────────────────────────────────────────────
# Built-in strategy: RSI mean-reversion
# ──────────────────────────────────────────────────────────────────────

class RSIMeanReversionStrategy(StrategyHandler):
    """
    Buy when RSI < oversold_threshold; sell when RSI > overbought_threshold.
    Emits FLAT when RSI is in the neutral zone.
    """

    def __init__(
        self,
        strategy_name: str = "rsi_mean_reversion",
        oversold: float = 30.0,
        overbought: float = 70.0,
    ) -> None:
        self._name = strategy_name
        self._oversold = oversold
        self._overbought = overbought
        self._prev_action: Optional[str] = None

    @property
    def name(self) -> str:
        return self._name

    def on_indicators(self, event: IndicatorEvent) -> Optional[SignalEvent]:
        if not event.is_warm or event.rsi is None:
            return None

        if event.rsi < self._oversold:
            action = "BUY"
        elif event.rsi > self._overbought:
            action = "SELL"
        else:
            action = "FLAT"

        if action == self._prev_action:
            return None

        self._prev_action = action
        confidence = 0.0
        if action == "BUY":
            confidence = (self._oversold - event.rsi) / self._oversold
        elif action == "SELL":
            confidence = (event.rsi - self._overbought) / (100.0 - self._overbought)
        confidence = max(0.0, min(1.0, confidence))

        return SignalEvent(
            symbol=event.symbol,
            strategy_name=self._name,
            action=action,
            confidence=confidence,
            timeframe=event.timeframe,
            timestamp=event.timestamp,
            current_price=Decimal(str(round(event.close, 4))),
            atr=Decimal(str(round(event.atr, 4))) if event.atr else None,
        )

    def reset(self) -> None:
        self._prev_action = None


# ──────────────────────────────────────────────────────────────────────
# Streaming strategy engine — orchestrator
# ──────────────────────────────────────────────────────────────────────

class StreamingStrategyEngine:
    """
    Subscribes to IndicatorEvent and fans out to all registered strategies.

    Each strategy runs independently (per-strategy isolation).  Signals from
    all strategies are published to the bus as SignalEvents.
    """

    def __init__(
        self,
        event_bus: EventBus,
        strategies: list[StrategyHandler] | None = None,
    ) -> None:
        self._bus = event_bus
        self._strategies: dict[str, StrategyHandler] = {}
        self._signal_count: int = 0

        if strategies:
            for strat in strategies:
                self.register(strat)

        event_bus.subscribe(IndicatorEvent, self.on_indicators)

    # ──────────────────────────────────────────────────────────────────
    # Strategy registry
    # ──────────────────────────────────────────────────────────────────

    def register(self, strategy: StrategyHandler) -> None:
        self._strategies[strategy.name] = strategy
        logger.debug("StreamingStrategyEngine: registered strategy %r", strategy.name)

    def unregister(self, name: str) -> None:
        self._strategies.pop(name, None)

    def strategy_names(self) -> list[str]:
        return list(self._strategies.keys())

    # ──────────────────────────────────────────────────────────────────
    # Handler
    # ──────────────────────────────────────────────────────────────────

    def on_indicators(self, event: IndicatorEvent) -> None:
        for strategy in list(self._strategies.values()):
            try:
                signal = strategy.on_indicators(event)
                if signal is not None:
                    self._bus.publish(signal)
                    self._signal_count += 1
                    logger.debug(
                        "StreamingStrategyEngine: %s → %s %s @ %s",
                        strategy.name, signal.action, signal.symbol, signal.current_price,
                    )
            except Exception as exc:
                logger.error(
                    "StreamingStrategyEngine: strategy %r raised: %s",
                    strategy.name, exc, exc_info=True,
                )

    def reset_all(self) -> None:
        for s in self._strategies.values():
            s.reset()

    @property
    def signal_count(self) -> int:
        return self._signal_count

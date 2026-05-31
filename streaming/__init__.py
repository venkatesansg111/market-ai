"""Phase 9 — Real-Time Streaming + Event-Driven Trading Architecture."""
from streaming.event_models import (
    StreamEvent,
    TickEvent,
    CandleEvent,
    IndicatorEvent,
    SignalEvent,
    RiskEvent,
    OrderEvent,
    FillEvent,
    PortfolioEvent,
    SystemEvent,
)
from streaming.event_bus import EventBus
from streaming.market_data_feed import MarketDataFeed, RawTick, SimulatedTickProducer
from streaming.candle_builder import CandleBuilderEngine
from streaming.streaming_indicators import StreamingIndicatorEngine, IndicatorConfig
from streaming.strategy_adapter import (
    StrategyHandler,
    StreamingStrategyEngine,
    EMACrossoverStrategy,
    RSIMeanReversionStrategy,
)
from streaming.execution_pipeline import ExecutionPipeline
from streaming.event_replay import EventLog, ReplayEngine, DeterminismVerifier
from streaming.backpressure import (
    BoundedQueue,
    DropPolicy,
    CircuitBreaker,
    CircuitState,
    BackpressureAwareEventBus,
)

__all__ = [
    "StreamEvent", "TickEvent", "CandleEvent", "IndicatorEvent",
    "SignalEvent", "RiskEvent", "OrderEvent", "FillEvent",
    "PortfolioEvent", "SystemEvent",
    "EventBus",
    "MarketDataFeed", "RawTick", "SimulatedTickProducer",
    "CandleBuilderEngine",
    "StreamingIndicatorEngine", "IndicatorConfig",
    "StrategyHandler", "StreamingStrategyEngine",
    "EMACrossoverStrategy", "RSIMeanReversionStrategy",
    "ExecutionPipeline",
    "EventLog", "ReplayEngine", "DeterminismVerifier",
    "BoundedQueue", "DropPolicy",
    "CircuitBreaker", "CircuitState",
    "BackpressureAwareEventBus",
]

"""Phase 8 — Risk Management data models."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


# ──────────────────────────────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────────────────────────────

class SizingMethod(str, Enum):
    FIXED_FRACTIONAL = "fixed_fractional"
    VOLATILITY_BASED = "volatility_based"
    KELLY = "kelly"
    CONFIDENCE_SCALED = "confidence_scaled"


class RiskDecisionType(str, Enum):
    APPROVED = "approved"
    REDUCED = "reduced"
    BLOCKED = "blocked"


class RebalanceTrigger(str, Enum):
    TIME = "time"
    DRIFT = "drift"
    THRESHOLD = "threshold"


class AllocationModelType(str, Enum):
    EQUAL_WEIGHT = "equal_weight"
    EQUAL_RISK = "equal_risk"
    INVERSE_VOLATILITY = "inverse_volatility"
    STRATEGY_PERFORMANCE = "strategy_performance"


# ──────────────────────────────────────────────────────────────────────
# Risk Parameters
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RiskParams:
    """Immutable risk configuration passed into all risk engines."""

    # Position sizing
    sizing_method: SizingMethod = SizingMethod.FIXED_FRACTIONAL
    risk_per_trade_pct: float = 1.0        # % of equity to risk per trade
    kelly_fraction: float = 0.25           # fractional Kelly multiplier
    max_position_pct: float = 10.0         # max single position as % of equity

    # Portfolio limits
    max_total_exposure_pct: float = 100.0  # max gross exposure % of equity
    max_per_asset_pct: float = 15.0        # max allocation to any single asset
    max_per_strategy_pct: float = 40.0     # max capital allocated to one strategy
    max_leverage: float = 1.0              # portfolio leverage cap

    # Drawdown / loss controls
    max_drawdown_pct: float = 15.0         # halt if portfolio DD exceeds this
    daily_loss_limit_pct: float = 3.0      # halt if daily loss exceeds this

    # Volatility shock
    volatility_lookback: int = 20          # rolling window for vol measurement
    volatility_shock_multiplier: float = 2.0  # trigger if vol > multiplier * baseline

    # Correlation risk
    correlation_threshold: float = 0.80   # block if new position corr > this
    correlation_lookback: int = 60         # days for correlation calculation

    # Rebalancing
    rebalance_drift_threshold_pct: float = 5.0   # rebalance if weight drifts by this
    rebalance_frequency_days: int = 7            # time-based rebalance interval


# ──────────────────────────────────────────────────────────────────────
# Signal input to risk engine
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SignalInput:
    """Normalised signal that the risk engine accepts from Phase 6."""

    symbol: str
    strategy_name: str
    action: str                         # "BUY" | "SELL" | "FLAT"
    confidence: float                   # 0-1 from MetaSignal
    timeframe: str
    current_price: Decimal
    atr: Optional[Decimal] = None       # for volatility-based sizing
    stop_price: Optional[Decimal] = None
    regime_strength: float = 0.5        # 0-1; default neutral
    run_id: str = ""


# ──────────────────────────────────────────────────────────────────────
# Sizing result
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SizingResult:
    symbol: str
    strategy_name: str
    raw_quantity: int                   # before risk gate adjustments
    adjusted_quantity: int              # after cap enforcement
    method: SizingMethod
    notional_value: Decimal
    equity_fraction: float              # fraction of equity this represents
    reasoning: str = ""


# ──────────────────────────────────────────────────────────────────────
# Risk decision
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RiskDecision:
    symbol: str
    strategy_name: str
    decision: RiskDecisionType
    approved_quantity: int              # 0 if BLOCKED
    original_quantity: int
    reason: str
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_approved(self) -> bool:
        return self.decision != RiskDecisionType.BLOCKED

    @property
    def was_reduced(self) -> bool:
        return self.decision == RiskDecisionType.REDUCED


# ──────────────────────────────────────────────────────────────────────
# Portfolio exposure snapshot
# ──────────────────────────────────────────────────────────────────────

@dataclass
class ExposureSnapshot:
    per_asset: dict[str, Decimal] = field(default_factory=dict)     # symbol → notional
    per_strategy: dict[str, Decimal] = field(default_factory=dict)  # strategy → notional
    total_long: Decimal = Decimal("0")
    total_short: Decimal = Decimal("0")

    @property
    def gross_exposure(self) -> Decimal:
        return self.total_long + abs(self.total_short)

    @property
    def net_exposure(self) -> Decimal:
        return self.total_long - abs(self.total_short)


# ──────────────────────────────────────────────────────────────────────
# Allocation weight
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AllocationWeight:
    symbol: str
    strategy_name: str
    weight: float           # 0-1, sum across all = 1.0
    model: AllocationModelType
    volatility: Optional[float] = None   # annualised vol used in calculation


# ──────────────────────────────────────────────────────────────────────
# Portfolio order — output of portfolio constructor
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PortfolioOrder:
    symbol: str
    action: str                  # "BUY" | "SELL" | "FLAT"
    quantity: int
    order_type: str              # "MARKET" | "LIMIT"
    strategy_name: str
    confidence: float
    current_price: Decimal
    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    timeframe: str = ""
    run_id: str = ""


# ──────────────────────────────────────────────────────────────────────
# Rebalance action
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RebalanceAction:
    symbol: str
    strategy_name: str
    current_weight: float
    target_weight: float
    delta_weight: float           # target - current
    trigger: RebalanceTrigger
    action: str                   # "BUY" | "SELL" | "HOLD"
    quantity: int = 0
    reason: str = ""


# ──────────────────────────────────────────────────────────────────────
# Risk metrics snapshot
# ──────────────────────────────────────────────────────────────────────

@dataclass
class RiskMetrics:
    equity: Decimal
    cash: Decimal
    gross_exposure: Decimal
    net_exposure: Decimal
    leverage: float
    current_drawdown_pct: float
    daily_pnl: Decimal
    daily_pnl_pct: float
    peak_equity: Decimal
    sharpe_rolling: Optional[float] = None
    volatility_rolling: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_drawdown_breached(self) -> bool:
        return False  # checked against RiskParams externally

    @property
    def summary(self) -> str:
        return (
            f"equity={self.equity:.2f} dd={self.current_drawdown_pct:.2f}% "
            f"daily_pnl={self.daily_pnl:.2f} leverage={self.leverage:.2f}x"
        )

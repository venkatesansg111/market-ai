"""Phase 8 — Risk Controls Engine: hard safety constraints."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from risk.portfolio_state import PortfolioStateEngine
from risk.risk_models import RiskParams, SignalInput

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ControlResult:
    passed: bool
    reason: str
    reduced_quantity: Optional[int] = None  # set when rule reduces (not blocks)


class RiskControlBase:
    """Abstract base; subclasses implement check()."""

    def check(
        self,
        signal: SignalInput,
        quantity: int,
        state: PortfolioStateEngine,
        params: RiskParams,
    ) -> ControlResult:
        raise NotImplementedError


# ──────────────────────────────────────────────────────────────────────
# 1. Max Drawdown Guard
# ──────────────────────────────────────────────────────────────────────

class MaxDrawdownGuard(RiskControlBase):
    """Block ALL new positions when portfolio drawdown exceeds threshold."""

    def check(
        self,
        signal: SignalInput,
        quantity: int,
        state: PortfolioStateEngine,
        params: RiskParams,
    ) -> ControlResult:
        dd = state.current_drawdown_pct
        if dd >= params.max_drawdown_pct:
            logger.warning(
                "MaxDrawdownGuard BLOCKED %s: drawdown=%.2f%% >= limit=%.2f%%",
                signal.symbol, dd, params.max_drawdown_pct,
            )
            return ControlResult(
                passed=False,
                reason=f"portfolio drawdown {dd:.2f}% exceeds limit {params.max_drawdown_pct:.2f}%",
            )
        return ControlResult(passed=True, reason="drawdown ok")


# ──────────────────────────────────────────────────────────────────────
# 2. Daily Loss Limit
# ──────────────────────────────────────────────────────────────────────

class DailyLossLimiter(RiskControlBase):
    """Block all new trades once daily loss exceeds configured threshold."""

    def check(
        self,
        signal: SignalInput,
        quantity: int,
        state: PortfolioStateEngine,
        params: RiskParams,
    ) -> ControlResult:
        daily_pnl_pct = state.daily_pnl_pct
        # daily_pnl_pct is negative when losing
        if daily_pnl_pct <= -params.daily_loss_limit_pct:
            logger.warning(
                "DailyLossLimiter BLOCKED %s: daily_pnl=%.2f%% <= -%.2f%%",
                signal.symbol, daily_pnl_pct, params.daily_loss_limit_pct,
            )
            return ControlResult(
                passed=False,
                reason=f"daily loss {daily_pnl_pct:.2f}% exceeds -{params.daily_loss_limit_pct:.2f}% limit",
            )
        return ControlResult(passed=True, reason="daily loss ok")


# ──────────────────────────────────────────────────────────────────────
# 3. Per-Asset Exposure Limit
# ──────────────────────────────────────────────────────────────────────

class AssetExposureLimit(RiskControlBase):
    """
    Ensure a single asset's notional (existing + new) stays within
    max_per_asset_pct of equity.

    If the new quantity would exceed the limit, it is *reduced* to the
    maximum allowable quantity rather than blocked outright.
    """

    def check(
        self,
        signal: SignalInput,
        quantity: int,
        state: PortfolioStateEngine,
        params: RiskParams,
    ) -> ControlResult:
        equity = state.equity
        if equity <= 0:
            return ControlResult(passed=False, reason="zero equity")

        current_pct = state.position_pct_of_equity(signal.symbol)
        max_pct = params.max_per_asset_pct

        # headroom available for this asset (could be 0 if already at cap)
        headroom_pct = max(0.0, max_pct - current_pct)
        headroom_notional = equity * Decimal(str(headroom_pct / 100))
        max_qty = int(headroom_notional / signal.current_price) if signal.current_price > 0 else 0

        if max_qty <= 0:
            return ControlResult(
                passed=False,
                reason=f"asset {signal.symbol} already at {current_pct:.2f}% >= {max_pct:.2f}% limit",
            )

        if quantity > max_qty:
            logger.info(
                "AssetExposureLimit REDUCED %s qty %d→%d (asset exposure limit %.1f%%)",
                signal.symbol, quantity, max_qty, max_pct,
            )
            return ControlResult(
                passed=True,
                reason=f"qty reduced to fit {max_pct:.1f}% asset cap",
                reduced_quantity=max_qty,
            )

        return ControlResult(passed=True, reason="asset exposure ok")


# ──────────────────────────────────────────────────────────────────────
# 4. Strategy Exposure Limit
# ──────────────────────────────────────────────────────────────────────

class StrategyExposureLimit(RiskControlBase):
    """Keep each strategy's total notional ≤ max_per_strategy_pct of equity."""

    def check(
        self,
        signal: SignalInput,
        quantity: int,
        state: PortfolioStateEngine,
        params: RiskParams,
    ) -> ControlResult:
        equity = state.equity
        if equity <= 0:
            return ControlResult(passed=False, reason="zero equity")

        current_pct = state.strategy_exposure_pct(signal.strategy_name)
        max_pct = params.max_per_strategy_pct
        headroom_pct = max(0.0, max_pct - current_pct)
        headroom_notional = equity * Decimal(str(headroom_pct / 100))
        max_qty = int(headroom_notional / signal.current_price) if signal.current_price > 0 else 0

        if max_qty <= 0:
            return ControlResult(
                passed=False,
                reason=f"strategy {signal.strategy_name} already at {current_pct:.2f}% >= {max_pct:.2f}% limit",
            )

        if quantity > max_qty:
            logger.info(
                "StrategyExposureLimit REDUCED %s qty %d→%d (strategy limit %.1f%%)",
                signal.symbol, quantity, max_qty, max_pct,
            )
            return ControlResult(
                passed=True,
                reason=f"qty reduced to fit {max_pct:.1f}% strategy cap",
                reduced_quantity=max_qty,
            )

        return ControlResult(passed=True, reason="strategy exposure ok")


# ──────────────────────────────────────────────────────────────────────
# 5. Total Portfolio Leverage Cap
# ──────────────────────────────────────────────────────────────────────

class LeverageCapControl(RiskControlBase):
    """Block if adding this position would push gross leverage above max_leverage."""

    def check(
        self,
        signal: SignalInput,
        quantity: int,
        state: PortfolioStateEngine,
        params: RiskParams,
    ) -> ControlResult:
        equity = state.equity
        if equity <= 0:
            return ControlResult(passed=False, reason="zero equity")

        snap = state.exposure_snapshot()
        new_notional = signal.current_price * quantity
        projected_gross = snap.gross_exposure + new_notional
        projected_leverage = float(projected_gross / equity)

        if projected_leverage > params.max_leverage:
            # Calculate max allowed additional notional
            remaining = equity * Decimal(str(params.max_leverage)) - snap.gross_exposure
            max_qty = max(0, int(remaining / signal.current_price)) if signal.current_price > 0 else 0
            if max_qty == 0:
                return ControlResult(
                    passed=False,
                    reason=f"leverage cap {params.max_leverage:.1f}x would be breached ({projected_leverage:.2f}x)",
                )
            logger.info(
                "LeverageCapControl REDUCED %s qty %d→%d (leverage cap %.1fx)",
                signal.symbol, quantity, max_qty, params.max_leverage,
            )
            return ControlResult(
                passed=True,
                reason=f"qty reduced to stay within {params.max_leverage:.1f}x leverage",
                reduced_quantity=max_qty,
            )

        return ControlResult(passed=True, reason="leverage ok")


# ──────────────────────────────────────────────────────────────────────
# 6. Volatility Shock Protection
# ──────────────────────────────────────────────────────────────────────

class VolatilityShockFilter(RiskControlBase):
    """
    Reduce position size when current ATR is significantly above baseline.

    baseline_atr must be supplied via signal.  If current ATR > multiplier × baseline,
    the quantity is scaled back by (baseline / current_atr).
    """

    def __init__(self, baseline_atr_map: dict[str, Decimal] | None = None) -> None:
        self._baseline: dict[str, Decimal] = baseline_atr_map or {}

    def set_baseline(self, symbol: str, atr: Decimal) -> None:
        self._baseline[symbol] = atr

    def check(
        self,
        signal: SignalInput,
        quantity: int,
        state: PortfolioStateEngine,
        params: RiskParams,
    ) -> ControlResult:
        if signal.atr is None or signal.atr <= 0:
            return ControlResult(passed=True, reason="no atr provided, skip vol shock check")

        baseline = self._baseline.get(signal.symbol)
        if baseline is None or baseline <= 0:
            return ControlResult(passed=True, reason="no baseline atr, skip vol shock check")

        ratio = float(signal.atr / baseline)
        if ratio > params.volatility_shock_multiplier:
            scale = 1.0 / ratio
            reduced = max(1, int(quantity * scale))
            logger.warning(
                "VolatilityShockFilter REDUCED %s qty %d→%d (atr_ratio=%.2f > %.1fx baseline)",
                signal.symbol, quantity, reduced, ratio, params.volatility_shock_multiplier,
            )
            return ControlResult(
                passed=True,
                reason=f"vol shock: atr {float(signal.atr):.2f} is {ratio:.2f}x baseline",
                reduced_quantity=reduced,
            )

        return ControlResult(passed=True, reason="volatility normal")


# ──────────────────────────────────────────────────────────────────────
# 7. Correlation Risk Filter
# ──────────────────────────────────────────────────────────────────────

class CorrelationRiskFilter(RiskControlBase):
    """
    Reduce exposure when the new symbol is highly correlated with
    an existing open position.

    Correlation matrix must be injected externally (e.g., rolling Pearson).
    """

    def __init__(self, correlation_matrix: dict[tuple[str, str], float] | None = None) -> None:
        self._corr: dict[tuple[str, str], float] = correlation_matrix or {}

    def update_correlation(self, sym_a: str, sym_b: str, corr: float) -> None:
        self._corr[(sym_a, sym_b)] = corr
        self._corr[(sym_b, sym_a)] = corr

    def _get_corr(self, a: str, b: str) -> float:
        return self._corr.get((a, b), self._corr.get((b, a), 0.0))

    def check(
        self,
        signal: SignalInput,
        quantity: int,
        state: PortfolioStateEngine,
        params: RiskParams,
    ) -> ControlResult:
        max_corr = 0.0
        correlated_symbol = ""
        for sym in state.open_symbols:
            if sym == signal.symbol:
                continue
            c = abs(self._get_corr(signal.symbol, sym))
            if c > max_corr:
                max_corr = c
                correlated_symbol = sym

        if max_corr >= params.correlation_threshold:
            # Scale back proportionally to how much above the threshold we are
            scale = (1.0 - params.correlation_threshold) / max(1e-9, 1.0 - params.correlation_threshold + (max_corr - params.correlation_threshold))
            reduced = max(1, int(quantity * scale))
            logger.info(
                "CorrelationRiskFilter REDUCED %s qty %d→%d (corr=%.2f with %s)",
                signal.symbol, quantity, reduced, max_corr, correlated_symbol,
            )
            return ControlResult(
                passed=True,
                reason=f"high correlation {max_corr:.2f} with {correlated_symbol}",
                reduced_quantity=reduced,
            )

        return ControlResult(passed=True, reason="correlation ok")


# ──────────────────────────────────────────────────────────────────────
# Composite — runs all controls in order
# ──────────────────────────────────────────────────────────────────────

class RiskControlsEngine:
    """
    Runs all registered risk controls in priority order.

    Blocking controls stop evaluation immediately.
    Reducing controls update quantity and continue.
    """

    def __init__(
        self,
        params: RiskParams,
        volatility_filter: VolatilityShockFilter | None = None,
        correlation_filter: CorrelationRiskFilter | None = None,
    ) -> None:
        self._params = params
        self._blocking: list[RiskControlBase] = [
            MaxDrawdownGuard(),
            DailyLossLimiter(),
        ]
        self._reducing: list[RiskControlBase] = [
            AssetExposureLimit(),
            StrategyExposureLimit(),
            LeverageCapControl(),
            volatility_filter or VolatilityShockFilter(),
            correlation_filter or CorrelationRiskFilter(),
        ]

    def evaluate(
        self,
        signal: SignalInput,
        quantity: int,
        state: PortfolioStateEngine,
    ) -> tuple[bool, int, str]:
        """
        Returns (approved: bool, final_qty: int, reason: str).

        approved=False means the trade must be blocked entirely.
        """
        # Blocking checks first
        for ctrl in self._blocking:
            result = ctrl.check(signal, quantity, state, self._params)
            if not result.passed:
                return False, 0, result.reason

        # Reducing checks
        current_qty = quantity
        reasons: list[str] = []
        for ctrl in self._reducing:
            result = ctrl.check(signal, current_qty, state, self._params)
            if not result.passed:
                return False, 0, result.reason
            if result.reduced_quantity is not None and result.reduced_quantity < current_qty:
                current_qty = result.reduced_quantity
                reasons.append(result.reason)

        reason = "; ".join(reasons) if reasons else "all controls passed"
        return True, current_qty, reason

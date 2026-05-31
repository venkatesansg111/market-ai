"""Phase 7 — Slippage model abstraction and implementations."""
from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal, ROUND_HALF_UP


class SlippageModel(ABC):
    """Abstract base for all slippage models."""

    @abstractmethod
    def apply_buy(self, price: Decimal) -> Decimal:
        """Return effective fill price for a buy order."""

    @abstractmethod
    def apply_sell(self, price: Decimal) -> Decimal:
        """Return effective fill price for a sell order."""

    def apply(self, price: Decimal, is_buy: bool) -> Decimal:
        return self.apply_buy(price) if is_buy else self.apply_sell(price)


class ZeroSlippageModel(SlippageModel):
    """No slippage — fill at exactly the requested price."""

    def apply_buy(self, price: Decimal) -> Decimal:
        return price

    def apply_sell(self, price: Decimal) -> Decimal:
        return price


class FixedBpsSlippageModel(SlippageModel):
    """Fixed basis-point slippage plus a half-spread cost.

    Buy fills at: price * (1 + slip_bps/10000 + half_spread_bps/10000)
    Sell fills at: price * (1 − slip_bps/10000 − half_spread_bps/10000)
    Result is quantized to 2 decimal places.
    """

    _QUANTIZE = Decimal("0.01")

    def __init__(self, slip_bps: float = 5.0, half_spread_bps: float = 2.0) -> None:
        self._slip = Decimal(str(slip_bps)) / Decimal("10000")
        self._spread = Decimal(str(half_spread_bps)) / Decimal("10000")
        self._buy_factor = Decimal("1") + self._slip + self._spread
        self._sell_factor = Decimal("1") - self._slip - self._spread

    def apply_buy(self, price: Decimal) -> Decimal:
        return (price * self._buy_factor).quantize(self._QUANTIZE, rounding=ROUND_HALF_UP)

    def apply_sell(self, price: Decimal) -> Decimal:
        return (price * self._sell_factor).quantize(self._QUANTIZE, rounding=ROUND_HALF_UP)


class PercentageSlippageModel(SlippageModel):
    """Fixed percentage slippage (no separate spread component).

    Buy fills at: price * (1 + pct/100)
    Sell fills at: price * (1 − pct/100)
    """

    _QUANTIZE = Decimal("0.01")

    def __init__(self, pct: float = 0.05) -> None:
        self._factor = Decimal(str(pct)) / Decimal("100")

    def apply_buy(self, price: Decimal) -> Decimal:
        return (price * (Decimal("1") + self._factor)).quantize(
            self._QUANTIZE, rounding=ROUND_HALF_UP
        )

    def apply_sell(self, price: Decimal) -> Decimal:
        return (price * (Decimal("1") - self._factor)).quantize(
            self._QUANTIZE, rounding=ROUND_HALF_UP
        )

"""Phase 7 — Broker adapter abstraction."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from execution.execution_models import (
    AccountInfo,
    BrokerPosition,
    BrokerResponse,
    Order,
)


class BrokerAdapter(ABC):
    """Abstract interface that all broker adapters must implement."""

    @abstractmethod
    def submit_order(self, order: Order) -> BrokerResponse:
        """Submit an order to the broker and return the immediate response."""

    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> bool:
        """Request cancellation of an order. Returns True if accepted."""

    @abstractmethod
    def get_positions(self) -> list[BrokerPosition]:
        """Return all current positions as reported by the broker."""

    @abstractmethod
    def get_account_info(self) -> AccountInfo:
        """Return current account / balance information."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if the adapter has an active connection."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from backtesting.backtest_models import BacktestConfig, OpenPosition, Trade, TradeSide
from utils.logger import get_logger
from config import settings

logger = get_logger(__name__, settings.log_dir, settings.log_level)

_ONE = Decimal("1")
_ZERO = Decimal("0")
_CENT = Decimal("0.01")
_PRICE_PREC = Decimal("0.0001")


class TradeExecutor:
    """Simulates trade execution with realistic slippage and commission.

    Slippage model (adverse fill):
        Entry (LONG): market_price × (1 + slippage_pct)  — pays more
        Exit  (LONG): market_price × (1 − slippage_pct)  — receives less

    Commission model:
        Charged on actual trade value at both entry and exit.
        commission = trade_value × commission_pct

    Position sizing:
        trade_value = available_capital × position_size_pct
        quantity    = floor(trade_value / entry_price)
        If quantity < 1, the position cannot be opened.
    """

    def __init__(self, config: BacktestConfig) -> None:
        self._config = config

    def open_long(
        self,
        instrument: str,
        market_price: Decimal,
        entry_time: datetime,
        available_capital: Decimal,
    ) -> Optional[OpenPosition]:
        """Simulate a long entry. Returns None if capital is insufficient."""
        entry_price = (market_price * (_ONE + self._config.slippage_pct)).quantize(_PRICE_PREC)

        trade_value = available_capital * self._config.position_size_pct
        quantity = int(trade_value / entry_price)

        if quantity < 1:
            logger.debug(
                "[TradeExecutor] OPEN LONG skipped — insufficient capital: "
                "capital=%.2f, trade_value=%.2f, entry_price=%.4f",
                float(available_capital), float(trade_value), float(entry_price),
            )
            return None

        actual_value = entry_price * quantity
        commission = (actual_value * self._config.commission_pct).quantize(_CENT)
        slippage_cost = (market_price * quantity * self._config.slippage_pct).quantize(_CENT)

        logger.debug(
            "[TradeExecutor] OPEN LONG %s qty=%d @ %.4f (market=%.4f) "
            "value=%.2f comm=%.2f slip=%.2f",
            instrument, quantity, float(entry_price), float(market_price),
            float(actual_value), float(commission), float(slippage_cost),
        )

        return OpenPosition(
            trade_id=Trade.new_id(),
            instrument=instrument,
            quantity=quantity,
            average_price=entry_price,
            entry_time=entry_time,
            side=TradeSide.LONG,
            entry_commission=commission,
            entry_slippage=slippage_cost,
        )

    def close_long(
        self,
        position: OpenPosition,
        market_price: Decimal,
        exit_time: datetime,
    ) -> Trade:
        """Simulate a long exit. Returns the completed Trade."""
        exit_price = (market_price * (_ONE - self._config.slippage_pct)).quantize(_PRICE_PREC)

        actual_value = exit_price * position.quantity
        exit_commission = (actual_value * self._config.commission_pct).quantize(_CENT)
        exit_slippage = (market_price * position.quantity * self._config.slippage_pct).quantize(_CENT)

        trade = Trade(
            trade_id=position.trade_id,
            instrument=position.instrument,
            entry_time=position.entry_time,
            exit_time=exit_time,
            entry_price=position.average_price,
            exit_price=exit_price,
            quantity=position.quantity,
            side=position.side,
            entry_commission=position.entry_commission,
            exit_commission=exit_commission,
            entry_slippage=position.entry_slippage,
            exit_slippage=exit_slippage,
        )

        logger.debug(
            "[TradeExecutor] CLOSE LONG %s qty=%d @ %.4f (market=%.4f) "
            "gross_pnl=%.2f net_pnl=%.2f",
            position.instrument, position.quantity,
            float(exit_price), float(market_price),
            float(trade.gross_pnl), float(trade.net_pnl),
        )

        return trade

    def total_entry_cost(
        self,
        market_price: Decimal,
        available_capital: Decimal,
    ) -> Decimal:
        """Cash debited on entry (entry_value + commission + slippage).
        Returns a value larger than available_capital if position cannot be opened.
        """
        entry_price = (market_price * (_ONE + self._config.slippage_pct)).quantize(_PRICE_PREC)
        trade_value = available_capital * self._config.position_size_pct
        quantity = int(trade_value / entry_price)
        if quantity < 1:
            return available_capital + _ONE

        actual_value = entry_price * quantity
        commission = (actual_value * self._config.commission_pct).quantize(_CENT)
        slippage_cost = (market_price * quantity * self._config.slippage_pct).quantize(_CENT)
        return (actual_value + commission + slippage_cost).quantize(_CENT)

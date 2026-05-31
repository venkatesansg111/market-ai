from __future__ import annotations

"""Integration test fixtures — seeds synthetic market data so tests are self-contained.

Inserts ~65 days of NIFTY 50 1day candles + indicators that alternate between
bullish and bearish regimes, ensuring the signal engine generates both BUY and
SELL signals and the backtest engine actually opens/closes trades.

All data is scoped to the test session and deleted after the suite completes.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

from database.connection import get_session
from database.models import MarketCandle, MarketIndicator
from database.models_backtesting import (
    BacktestRun,
    BacktestTrade,
    PortfolioSnapshot,
    create_backtest_tables,
)


# ──────────────────────────────────────────────────────────────────────
# Constants matching _minimal_config() in test_backtest_engine.py
# ──────────────────────────────────────────────────────────────────────
_INSTRUMENT = "NIFTY 50"
_TIMEFRAME = "1day"
_START = datetime(2023, 10, 1)
_END = datetime(2024, 1, 1)
_BASE_PRICE = 19_500.0


def _weekdays_between(start: datetime, end: datetime) -> list[datetime]:
    """Return all Mon–Fri dates in [start, end)."""
    days = []
    cur = start
    while cur < end:
        if cur.weekday() < 5:  # 0=Mon … 4=Fri
            days.append(cur)
        cur += timedelta(days=1)
    return days


def _make_candle_row(dt: datetime, price: float) -> dict:
    return {
        "instrument": _INSTRUMENT,
        "candle_time": dt,
        "open": round(price * 0.9985, 2),
        "high": round(price * 1.0025, 2),
        "low": round(price * 0.9965, 2),
        "close": round(price, 2),
        "volume": 500_000,
        "timeframe": _TIMEFRAME,
    }


def _make_indicator_row(dt: datetime, price: float, bullish: bool) -> dict:
    """
    Bullish regime  → ema20>ema50>ema200, rsi=65, price>vwap, macd>signal → STRONG_BUY
    Bearish regime  → ema20<ema50<ema200, rsi=35, price<vwap, macd<signal → STRONG_SELL
    """
    if bullish:
        return {
            "instrument": _INSTRUMENT,
            "candle_time": dt,
            "timeframe": _TIMEFRAME,
            "ema20": round(price * 1.004, 4),
            "ema50": round(price * 1.001, 4),
            "ema200": round(price * 0.990, 4),
            "rsi14": 65.0,
            "vwap": round(price * 0.993, 4),
            "macd": 80.0,
            "macd_signal": 40.0,
        }
    else:
        return {
            "instrument": _INSTRUMENT,
            "candle_time": dt,
            "timeframe": _TIMEFRAME,
            "ema20": round(price * 0.990, 4),
            "ema50": round(price * 0.996, 4),
            "ema200": round(price * 1.004, 4),
            "rsi14": 35.0,
            "vwap": round(price * 1.007, 4),
            "macd": -80.0,
            "macd_signal": -40.0,
        }


@pytest.fixture(scope="session", autouse=True)
def seed_integration_data():
    """Insert synthetic candles + indicators once per test session, clean up after."""
    create_backtest_tables()

    days = _weekdays_between(_START, _END)
    price = _BASE_PRICE

    candle_rows = []
    indicator_rows = []

    for i, dt in enumerate(days):
        # Small random walk
        price *= 1.0003 if i % 3 != 0 else 0.9997
        price = round(price, 2)

        # Alternate: 10 bullish days → 10 bearish days → ...
        bullish = (i // 10) % 2 == 0

        candle_rows.append(_make_candle_row(dt, price))
        indicator_rows.append(_make_indicator_row(dt, price, bullish))

    with get_session() as session:
        # Use INSERT ... ON CONFLICT DO NOTHING so re-runs don't fail
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        session.execute(
            pg_insert(MarketCandle)
            .values(candle_rows)
            .on_conflict_do_nothing()
        )
        session.execute(
            pg_insert(MarketIndicator)
            .values(indicator_rows)
            .on_conflict_do_nothing()
        )

    yield  # ← tests run here

    # Teardown: delete synthetic data and any backtest runs created during tests
    with get_session() as session:
        session.execute(
            delete(MarketCandle).where(
                MarketCandle.instrument == _INSTRUMENT,
                MarketCandle.timeframe == _TIMEFRAME,
                MarketCandle.candle_time >= _START,
                MarketCandle.candle_time < _END,
            )
        )
        session.execute(
            delete(MarketIndicator).where(
                MarketIndicator.instrument == _INSTRUMENT,
                MarketIndicator.timeframe == _TIMEFRAME,
                MarketIndicator.candle_time >= _START,
                MarketIndicator.candle_time < _END,
            )
        )
        # Remove test backtest_runs (cascades to trades + snapshots)
        session.execute(
            delete(BacktestRun).where(
                BacktestRun.run_name.like("test_run%")
            )
        )

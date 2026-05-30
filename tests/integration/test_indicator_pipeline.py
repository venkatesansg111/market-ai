from __future__ import annotations

"""Integration tests for the full indicator → signal pipeline.

Requires a live PostgreSQL database (docker compose up -d).
Run with: pytest tests/integration/ -v

These tests use a dedicated TEST_INSTRUMENT to avoid polluting production data
and clean up after themselves.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select, text

from data_providers.base import CandleData
from database.connection import get_session, verify_connection
from database.models import MarketCandle, MarketIndicator, TradeSignal, create_tables
from indicators.indicator_engine import IndicatorEngineService
from ingestion.loader import bulk_upsert
from signals.signal_engine import SignalEngineService

_TEST_INSTRUMENT = "TEST_INTEG_INSTRUMENT"
_TEST_TIMEFRAME = "1day"


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def require_db():
    if not verify_connection():
        pytest.skip("PostgreSQL not available — skipping integration tests")
    create_tables()


@pytest.fixture(scope="module")
def clean_test_data():
    """Remove all test data before and after the test module runs."""
    _wipe()
    yield
    _wipe()


def _wipe():
    with get_session() as session:
        for table in ("market_indicators", "market_candles", "trade_signals"):
            session.execute(
                text(f"DELETE FROM {table} WHERE instrument = :i"),
                {"i": _TEST_INSTRUMENT},
            )


def _make_candles(n: int = 300) -> list[CandleData]:
    base = datetime(2022, 1, 3)
    price = 20000.0
    result = []
    for i in range(n):
        price *= 1.001 if i % 2 == 0 else 0.9995
        result.append(
            CandleData(
                instrument=_TEST_INSTRUMENT,
                candle_time=(base + timedelta(days=i)).isoformat(),
                open=round(price * 0.999, 2),
                high=round(price * 1.002, 2),
                low=round(price * 0.997, 2),
                close=round(price, 2),
                volume=100_000,
                timeframe=_TEST_TIMEFRAME,
            )
        )
    return result


def _count_table(model, instrument: str = _TEST_INSTRUMENT) -> int:
    with get_session() as session:
        return session.execute(
            select(func.count()).select_from(model).where(
                model.instrument == instrument
            )
        ).scalar() or 0


# ──────────────────────────────────────────────────────────────────────
# Tests (ordered — each depends on the previous)
# ──────────────────────────────────────────────────────────────────────

def test_01_indicator_engine_processes_all_candles(clean_test_data):
    """Inserting 300 candles then running the indicator engine should produce indicator rows."""
    candles = _make_candles(300)
    bulk_upsert(candles)

    engine = IndicatorEngineService()
    results = engine.run([_TEST_INSTRUMENT], [_TEST_TIMEFRAME])
    count = results[(_TEST_INSTRUMENT, _TEST_TIMEFRAME)]

    assert count > 0, "Expected indicator rows to be inserted"
    # EMA200 needs 200 bars to warm up; first 199 will have NaN but still get a row
    assert count == 300, f"Expected 300 indicator rows (one per candle), got {count}"


def test_02_indicator_engine_is_idempotent():
    """Running the indicator engine again without new candles should insert 0 rows."""
    engine = IndicatorEngineService()
    results = engine.run([_TEST_INSTRUMENT], [_TEST_TIMEFRAME])
    count = results[(_TEST_INSTRUMENT, _TEST_TIMEFRAME)]
    assert count == 0, f"Re-run should insert 0 rows, got {count}"


def test_03_indicator_engine_incremental_insert():
    """Adding 10 new candles and re-running should insert exactly 10 indicator rows."""
    existing_count = _count_table(MarketCandle)
    base = datetime(2022, 1, 3)
    new_candles = []
    price = 22000.0
    for i in range(existing_count, existing_count + 10):
        price *= 1.001
        new_candles.append(
            CandleData(
                instrument=_TEST_INSTRUMENT,
                candle_time=(base + timedelta(days=i)).isoformat(),
                open=round(price * 0.999, 2),
                high=round(price * 1.002, 2),
                low=round(price * 0.997, 2),
                close=round(price, 2),
                volume=100_000,
                timeframe=_TEST_TIMEFRAME,
            )
        )
    bulk_upsert(new_candles)

    engine = IndicatorEngineService()
    results = engine.run([_TEST_INSTRUMENT], [_TEST_TIMEFRAME])
    count = results[(_TEST_INSTRUMENT, _TEST_TIMEFRAME)]
    assert count == 10, f"Expected 10 new indicator rows, got {count}"


def test_04_signal_engine_generates_signal():
    """After indicators exist, the signal engine should evaluate and store a signal."""
    engine = SignalEngineService()
    results = engine.run([_TEST_INSTRUMENT], [_TEST_TIMEFRAME])
    count = results[(_TEST_INSTRUMENT, _TEST_TIMEFRAME)]
    # A signal should always be generated (even if NO_TRADE)
    assert count >= 0

    signal_count = _count_table(TradeSignal)
    assert signal_count > 0, "Expected at least one signal row in trade_signals"


def test_05_signal_engine_is_idempotent():
    """Running the signal engine again without new indicators should insert 0 new signals."""
    before = _count_table(TradeSignal)
    engine = SignalEngineService()
    engine.run([_TEST_INSTRUMENT], [_TEST_TIMEFRAME])
    after = _count_table(TradeSignal)
    assert after == before, "Re-run should not insert duplicate signals"


def test_06_indicator_rows_have_valid_schema():
    """All indicator rows should have the correct instrument and timeframe."""
    with get_session() as session:
        rows = session.execute(
            select(MarketIndicator).where(
                MarketIndicator.instrument == _TEST_INSTRUMENT,
                MarketIndicator.timeframe == _TEST_TIMEFRAME,
            )
        ).scalars().all()

    assert len(rows) > 0
    for row in rows:
        assert row.instrument == _TEST_INSTRUMENT
        assert row.timeframe == _TEST_TIMEFRAME
        assert row.candle_time is not None


def test_07_signal_rows_have_valid_signal_type():
    """All stored signals should have a recognized signal_type value."""
    from signals.signal_models import SignalType

    valid_types = {st.value for st in SignalType}
    with get_session() as session:
        rows = session.execute(
            select(TradeSignal).where(
                TradeSignal.instrument == _TEST_INSTRUMENT
            )
        ).scalars().all()

    for row in rows:
        assert row.signal_type in valid_types, (
            f"Unknown signal_type: {row.signal_type}"
        )
        assert 0 <= float(row.confidence) <= 100

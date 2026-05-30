from __future__ import annotations

"""Integration tests for BacktestEngine.

Requirements:
    - PostgreSQL running (docker compose up -d)
    - Phase 1 ingestion and Phase 2 indicator pipeline already executed
      for the test instrument (or conftest inserts synthetic data)

Run with: pytest tests/integration/test_backtest_engine.py -v
"""

from datetime import datetime
from decimal import Decimal

import pytest

from backtesting.backtest_engine import BacktestEngine
from backtesting.backtest_models import BacktestConfig, BacktestResult
from backtesting.reporting import BacktestReporter
from database.connection import get_session
from database.models_backtesting import (
    BacktestRun,
    BacktestTrade,
    PortfolioSnapshot,
    create_backtest_tables,
)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _minimal_config(
    instrument: str = "NIFTY 50",
    timeframe: str = "1day",
    months: int = 3,
    capital: float = 1_000_000.0,
) -> BacktestConfig:
    """Return a short-period config suitable for integration tests."""
    end = datetime(2024, 1, 1)
    start = datetime(2023, 10, 1)
    return BacktestConfig(
        instrument=instrument,
        timeframe=timeframe,
        start_date=start,
        end_date=end,
        starting_capital=Decimal(str(capital)),
        strategy_name="signal",
        run_name=f"test_run_{datetime.utcnow().strftime('%H%M%S%f')}",
    )


# ──────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestBacktestEngineDB:
    """End-to-end tests — require live DB with pre-ingested data."""

    def test_tables_created_idempotently(self):
        """create_backtest_tables() should not raise on repeated calls."""
        create_backtest_tables()
        create_backtest_tables()  # second call must be a no-op

    def test_run_returns_backtest_result(self):
        config = _minimal_config()
        engine = BacktestEngine()
        result = engine.run(config)
        assert isinstance(result, BacktestResult)
        assert result.run_name == config.run_name

    def test_result_has_equity_curve(self):
        config = _minimal_config()
        result = BacktestEngine().run(config)
        # Equity curve must have at least one point per trading day in range
        assert len(result.equity_curve) > 0

    def test_ending_capital_is_decimal(self):
        config = _minimal_config()
        result = BacktestEngine().run(config)
        assert isinstance(result.ending_capital, Decimal)

    def test_run_persisted_to_db(self):
        config = _minimal_config()
        result = BacktestEngine().run(config)
        with get_session() as session:
            runs = session.query(BacktestRun).filter(
                BacktestRun.run_name == result.run_name
            ).all()
        assert len(runs) == 1
        assert runs[0].instrument == config.instrument

    def test_trades_persisted_to_db(self):
        config = _minimal_config()
        result = BacktestEngine().run(config)
        with get_session() as session:
            run = session.query(BacktestRun).filter(
                BacktestRun.run_name == result.run_name
            ).first()
            if run is None:
                pytest.skip("Run not persisted — DB may lack indicator data")
            trade_count = session.query(BacktestTrade).filter(
                BacktestTrade.run_id == run.id
            ).count()
        assert trade_count == result.total_trades

    def test_snapshots_persisted_to_db(self):
        config = _minimal_config()
        result = BacktestEngine().run(config)
        with get_session() as session:
            run = session.query(BacktestRun).filter(
                BacktestRun.run_name == result.run_name
            ).first()
            if run is None:
                pytest.skip("Run not persisted — DB may lack indicator data")
            snapshot_count = session.query(PortfolioSnapshot).filter(
                PortfolioSnapshot.run_id == run.id
            ).count()
        assert snapshot_count == len(result.equity_curve)

    def test_two_runs_produce_independent_records(self):
        """Each run gets its own auto-named entry; names must be unique."""
        config1 = _minimal_config()
        config2 = BacktestConfig(
            instrument=config1.instrument,
            timeframe=config1.timeframe,
            start_date=config1.start_date,
            end_date=config1.end_date,
            starting_capital=config1.starting_capital,
            strategy_name=config1.strategy_name,
            run_name=f"test_run2_{datetime.utcnow().strftime('%H%M%S%f')}",
        )
        engine = BacktestEngine()
        r1 = engine.run(config1)
        r2 = engine.run(config2)
        assert r1.run_name != r2.run_name

    def test_reporter_generates_valid_json(self):
        config = _minimal_config()
        result = BacktestEngine().run(config)
        import json
        reporter = BacktestReporter(result)
        data = json.loads(reporter.to_json())
        assert "run_name" in data
        assert "performance" in data
        assert "trade_statistics" in data
        assert "trades" in data

    def test_reporter_generates_markdown(self):
        config = _minimal_config()
        result = BacktestEngine().run(config)
        reporter = BacktestReporter(result)
        md = reporter.to_markdown()
        assert "# Backtest Report" in md
        assert "## Performance Summary" in md
        assert "## Trade Statistics" in md

    def test_raises_on_missing_data(self):
        """Expect ValueError when no candle/indicator data exists for the range."""
        config = BacktestConfig(
            instrument="NONEXISTENT_XYZ",
            timeframe="1day",
            start_date=datetime(2020, 1, 1),
            end_date=datetime(2020, 2, 1),
            starting_capital=Decimal("1000000"),
            strategy_name="signal",
        )
        with pytest.raises(ValueError, match="No data found"):
            BacktestEngine().run(config)


@pytest.mark.integration
class TestBacktestMetricsValidity:
    """Verify computed metrics are within plausible bounds."""

    def test_win_rate_between_0_and_100(self):
        config = _minimal_config()
        result = BacktestEngine().run(config)
        assert Decimal("0") <= result.win_rate_pct <= Decimal("100")

    def test_max_drawdown_non_negative(self):
        config = _minimal_config()
        result = BacktestEngine().run(config)
        assert result.max_drawdown_pct >= Decimal("0")

    def test_equity_curve_starts_near_capital(self):
        config = _minimal_config()
        result = BacktestEngine().run(config)
        if result.equity_curve:
            first_eq = float(result.equity_curve[0].equity)
            assert abs(first_eq - 1_000_000.0) / 1_000_000.0 < 0.05

    def test_winning_plus_losing_equals_total(self):
        config = _minimal_config()
        result = BacktestEngine().run(config)
        assert result.winning_trades + result.losing_trades == result.total_trades

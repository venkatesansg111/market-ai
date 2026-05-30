"""Phase 3 — Institutional-grade backtesting framework.

Entry points:
    BacktestEngine.run(config) -> BacktestResult
    BacktestReporter(result).save(output_dir)

Quick start:
    from backtesting.backtest_engine import BacktestEngine
    from backtesting.backtest_models import BacktestConfig
    from datetime import datetime
    from decimal import Decimal

    config = BacktestConfig(
        instrument="NIFTY 50",
        timeframe="1day",
        start_date=datetime(2023, 1, 1),
        end_date=datetime(2025, 1, 1),
        starting_capital=Decimal("1000000"),
        strategy_name="signal",
    )
    result = BacktestEngine().run(config)
"""

from __future__ import annotations

"""Entry point for the Market AI platform.

Phase 1 — Historical Ingestion:
    python main.py                                 # defaults from .env
    python main.py --provider yfinance
    python main.py --instruments "NIFTY 50,NIFTY BANK" --timeframes 1day,5min
    python main.py --months 6

Phase 2 — Intelligence Pipeline:
    python main.py --mode indicators               # calculate EMA/RSI/VWAP/MACD
    python main.py --mode signals                  # generate trade signals
    python main.py --mode pipeline                 # indicators + signals in sequence
    python main.py --mode replay --months 1        # historical replay through candle builder

Phase 3 — Backtesting:
    python main.py --mode backtest --instruments "NIFTY 50" --timeframes 1day
    python main.py --mode backtest --strategy signal --capital 1000000
    python main.py --mode backtest --from-date 2023-01-01 --to-date 2024-01-01
"""

import argparse
import sys

from config import settings
from data_providers.base import Timeframe
from database.connection import verify_connection
from database.models import create_tables
from utils.logger import get_logger

logger = get_logger("market_ai.main", settings.log_dir, settings.log_level)

_TIMEFRAME_MAP = {tf.value: tf for tf in Timeframe}


# ──────────────────────────────────────────────────────────────────────
# Argument parsing
# ──────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Market AI — data and intelligence platform")
    parser.add_argument(
        "--mode",
        choices=["ingest", "indicators", "signals", "pipeline", "replay", "backtest"],
        default="ingest",
        help=(
            "Operating mode: "
            "ingest (Phase 1 historical fetch), "
            "indicators (calculate technical indicators), "
            "signals (generate trade signals), "
            "pipeline (indicators + signals), "
            "replay (historical candle replay through candle builder), "
            "backtest (Phase 3 strategy backtesting)"
        ),
    )
    parser.add_argument(
        "--provider",
        choices=["yfinance", "nse"],
        default=settings.data_provider,
        help="Data provider (ingest mode only)",
    )
    parser.add_argument(
        "--instruments",
        default=",".join(settings.instruments),
        help='Comma-separated instrument list (e.g. "NIFTY 50,NIFTY BANK")',
    )
    parser.add_argument(
        "--timeframes",
        default=",".join(settings.timeframes),
        help="Comma-separated timeframes: 1min,5min,15min,1day",
    )
    parser.add_argument(
        "--months",
        type=int,
        default=settings.ingestion.history_months,
        help="How many months of history to fetch/replay",
    )
    # Phase 3 — backtest arguments
    parser.add_argument(
        "--strategy",
        default="signal",
        help="Backtest strategy name (default: signal)",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=1_000_000.0,
        help="Starting capital in INR (default: 1000000)",
    )
    parser.add_argument(
        "--from-date",
        dest="from_date",
        default=None,
        help="Backtest start date YYYY-MM-DD (default: 1 year ago)",
    )
    parser.add_argument(
        "--to-date",
        dest="to_date",
        default=None,
        help="Backtest end date YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--run-name",
        dest="run_name",
        default="",
        help="Optional backtest run name (auto-generated if blank)",
    )
    parser.add_argument(
        "--list-strategies",
        dest="list_strategies",
        action="store_true",
        default=False,
        help="List all available backtest strategies and exit",
    )
    return parser.parse_args()


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _build_provider(name: str):
    if name == "nse":
        from data_providers.nse_provider import NseProvider
        return NseProvider()
    from data_providers.yfinance_provider import YFinanceProvider
    return YFinanceProvider()


def _resolve_timeframes(raw: str) -> list[Timeframe]:
    tfs: list[Timeframe] = []
    for token in raw.split(","):
        token = token.strip()
        if token not in _TIMEFRAME_MAP:
            logger.error("Unknown timeframe '%s'. Valid: %s", token, list(_TIMEFRAME_MAP))
            sys.exit(1)
        tfs.append(_TIMEFRAME_MAP[token])
    return tfs


def _db_preflight() -> None:
    """Verify DB connection and ensure all tables exist."""
    if not verify_connection():
        logger.critical("Cannot connect to database. Aborting.")
        sys.exit(1)
    create_tables()


# ──────────────────────────────────────────────────────────────────────
# Mode handlers
# ──────────────────────────────────────────────────────────────────────

def _run_ingest(args: argparse.Namespace) -> None:
    from ingestion.fetch_historical import fetch_and_store, print_summary

    provider = _build_provider(args.provider)
    instruments = [i.strip() for i in args.instruments.split(",")]
    timeframes = _resolve_timeframes(args.timeframes)

    logger.info("=" * 55)
    logger.info("  Market AI — Historical Ingestion Pipeline")
    logger.info("=" * 55)
    logger.info("Provider    : %s", provider.provider_name())
    logger.info("Instruments : %s", instruments)
    logger.info("Timeframes  : %s", [tf.value for tf in timeframes])
    logger.info("History     : %d months", args.months)

    summaries = fetch_and_store(
        provider=provider,
        instruments=instruments,
        timeframes=timeframes,
        history_months=args.months,
    )
    print_summary(summaries)


def _run_indicators(args: argparse.Namespace) -> None:
    from indicators.indicator_engine import IndicatorEngineService

    instruments = [i.strip() for i in args.instruments.split(",")]
    timeframes = [tf.strip() for tf in args.timeframes.split(",")]

    logger.info("=" * 55)
    logger.info("  Market AI — Indicator Engine")
    logger.info("=" * 55)
    logger.info("Instruments : %s", instruments)
    logger.info("Timeframes  : %s", timeframes)

    engine = IndicatorEngineService()
    results = engine.run(instruments, timeframes)

    total = sum(results.values())
    logger.info("─" * 55)
    for (instr, tf), count in results.items():
        logger.info("  %-20s %-8s  +%d indicator rows", instr, tf, count)
    logger.info("─" * 55)
    logger.info("  Total new indicator rows: %d", total)


def _run_signals(args: argparse.Namespace) -> None:
    from signals.signal_engine import SignalEngineService

    instruments = [i.strip() for i in args.instruments.split(",")]
    timeframes = [tf.strip() for tf in args.timeframes.split(",")]

    logger.info("=" * 55)
    logger.info("  Market AI — Signal Engine")
    logger.info("=" * 55)

    engine = SignalEngineService()
    results = engine.run(instruments, timeframes)

    logger.info("─" * 55)
    for (instr, tf), count in results.items():
        logger.info("  %-20s %-8s  %d signal(s) stored", instr, tf, count)


def _run_pipeline(args: argparse.Namespace) -> None:
    """Run indicators then signals in sequence."""
    logger.info("Running pipeline: indicators → signals")
    _run_indicators(args)
    _run_signals(args)


def _run_backtest(args: argparse.Namespace) -> None:
    from datetime import datetime, timezone
    from decimal import Decimal
    from backtesting.backtest_engine import BacktestEngine
    from backtesting.backtest_models import BacktestConfig
    from backtesting.reporting import BacktestReporter

    instruments = [i.strip() for i in args.instruments.split(",")]
    timeframes = [tf.strip() for tf in args.timeframes.split(",")]

    if len(instruments) != 1 or len(timeframes) != 1:
        logger.error("Backtest mode requires exactly one instrument and one timeframe.")
        sys.exit(1)

    instrument = instruments[0]
    timeframe = timeframes[0]

    today = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    if args.from_date:
        try:
            start_date = datetime.strptime(args.from_date, "%Y-%m-%d")
        except ValueError:
            logger.error("--from-date must be YYYY-MM-DD, got: %s", args.from_date)
            sys.exit(1)
    else:
        from utils.time_utils import history_start_date
        start_date = history_start_date(months=12)

    if args.to_date:
        try:
            end_date = datetime.strptime(args.to_date, "%Y-%m-%d")
        except ValueError:
            logger.error("--to-date must be YYYY-MM-DD, got: %s", args.to_date)
            sys.exit(1)
    else:
        end_date = today

    config = BacktestConfig(
        instrument=instrument,
        timeframe=timeframe,
        start_date=start_date,
        end_date=end_date,
        starting_capital=Decimal(str(args.capital)),
        strategy_name=args.strategy,
        run_name=args.run_name,
    )

    logger.info("=" * 55)
    logger.info("  Market AI — Backtesting Engine")
    logger.info("=" * 55)

    engine = BacktestEngine()
    result = engine.run(config)

    reporter = BacktestReporter(result)
    paths = reporter.save()
    logger.info("Reports saved: %s", {k: str(v) for k, v in paths.items()})


def _run_replay(args: argparse.Namespace) -> None:
    from realtime.candle_manager import CandleManager
    from realtime.candle_persistence import CandlePersistenceService
    from indicators.indicator_engine import IndicatorEngineService
    from signals.signal_engine import SignalEngineService
    from scheduler.realtime_scheduler import RealtimeCandleService

    instruments = [i.strip() for i in args.instruments.split(",")]
    timeframes = _resolve_timeframes(args.timeframes)

    logger.info("=" * 55)
    logger.info("  Market AI — Historical Replay")
    logger.info("=" * 55)
    logger.info("Instruments : %s", instruments)
    logger.info("Timeframes  : %s", [tf.value for tf in timeframes])
    logger.info("Months back : %d", args.months)

    service = RealtimeCandleService(
        candle_manager=CandleManager(timeframes),
        persistence_service=CandlePersistenceService(),
        indicator_service=IndicatorEngineService(),
        signal_service=SignalEngineService(),
    )
    stats = service.run_historical_replay(
        instruments=instruments,
        timeframes=timeframes,
        months_back=args.months,
    )
    logger.info("Replay complete: %s", stats)


# ──────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()

    # --list-strategies is a pure query — no DB connection needed
    if args.list_strategies:
        from strategies.registry import list_strategies, STRATEGIES
        for name in list_strategies():
            strat = STRATEGIES[name]
            print(f"{name:<20} {strat.description}")
        sys.exit(0)

    _db_preflight()

    dispatch = {
        "ingest": _run_ingest,
        "indicators": _run_indicators,
        "signals": _run_signals,
        "pipeline": _run_pipeline,
        "replay": _run_replay,
        "backtest": _run_backtest,
    }
    dispatch[args.mode](args)


if __name__ == "__main__":
    main()

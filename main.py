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
        choices=["ingest", "indicators", "signals", "pipeline", "replay"],
        default="ingest",
        help=(
            "Operating mode: "
            "ingest (Phase 1 historical fetch), "
            "indicators (calculate technical indicators), "
            "signals (generate trade signals), "
            "pipeline (indicators + signals), "
            "replay (historical candle replay through candle builder)"
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

    _db_preflight()

    dispatch = {
        "ingest": _run_ingest,
        "indicators": _run_indicators,
        "signals": _run_signals,
        "pipeline": _run_pipeline,
        "replay": _run_replay,
    }
    dispatch[args.mode](args)


if __name__ == "__main__":
    main()

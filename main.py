from __future__ import annotations

"""Entry point for the Market AI data ingestion pipeline.

Usage:
    python main.py                          # use defaults from .env
    python main.py --provider yfinance
    python main.py --provider nse
    python main.py --instruments "NIFTY 50,NIFTY BANK"
    python main.py --timeframes 1day,5min
    python main.py --months 6
"""

import argparse
import sys

from config import settings
from data_providers.base import Timeframe
from database.connection import verify_connection
from database.models import create_tables
from ingestion.fetch_historical import fetch_and_store, print_summary
from utils.logger import get_logger

logger = get_logger("market_ai.main", settings.log_dir, settings.log_level)

_TIMEFRAME_MAP = {tf.value: tf for tf in Timeframe}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Market AI — historical data ingestion")
    parser.add_argument(
        "--provider",
        choices=["yfinance", "nse"],
        default=settings.data_provider,
        help="Data provider to use (default: from .env DATA_PROVIDER)",
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
        help="How many months of history to fetch",
    )
    return parser.parse_args()


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


def main() -> None:
    args = _parse_args()

    logger.info("=" * 55)
    logger.info("  Market AI — Historical Ingestion Pipeline")
    logger.info("=" * 55)
    logger.info("Provider    : %s", args.provider)
    logger.info("Instruments : %s", args.instruments)
    logger.info("Timeframes  : %s", args.timeframes)
    logger.info("History     : %d months", args.months)

    # 1. Verify DB connection
    if not verify_connection():
        logger.critical("Cannot connect to database. Aborting.")
        sys.exit(1)

    # 2. Auto-create tables (idempotent)
    create_tables()

    # 3. Build provider
    provider = _build_provider(args.provider)
    logger.info("Using provider: %s", provider.provider_name())

    # 4. Resolve inputs
    instruments = [i.strip() for i in args.instruments.split(",")]
    timeframes = _resolve_timeframes(args.timeframes)

    # 5. Run ingestion
    summaries = fetch_and_store(
        provider=provider,
        instruments=instruments,
        timeframes=timeframes,
        history_months=args.months,
    )

    # 6. Print report
    print_summary(summaries)


if __name__ == "__main__":
    main()

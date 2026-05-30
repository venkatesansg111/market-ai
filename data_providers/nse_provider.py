from __future__ import annotations

"""NSE-based provider using nsepython.

nsepython is a third-party wrapper around NSE's unofficial endpoints.
It works best for end-of-day data. For intraday, we fall back to yfinance
unless a premium data source is wired in.

Install: pip install nsepython
"""

from datetime import date
from typing import Sequence

from data_providers.base import CandleData, MarketDataProvider, Timeframe
from data_providers.yfinance_provider import YFinanceProvider
from utils.logger import get_logger
from config import settings

logger = get_logger(__name__, settings.log_dir, settings.log_level)

# Intraday timeframes that NSEPython cannot provide
_INTRADAY_TIMEFRAMES = {Timeframe.MIN_1, Timeframe.MIN_5, Timeframe.MIN_15}

# NSEPython expects these index names
_NSE_INDEX_MAP: dict[str, str] = {
    "NIFTY 50": "NIFTY 50",
    "NIFTY": "NIFTY 50",
    "NIFTY BANK": "NIFTY BANK",
    "BANKNIFTY": "NIFTY BANK",
}


class NseProvider(MarketDataProvider):
    """
    Fetches EOD data via nsepython; falls back to YFinanceProvider for
    intraday timeframes where NSE does not expose free APIs.
    """

    def __init__(self) -> None:
        try:
            import nsepython  # noqa: F401
            self._nsepython_available = True
        except ImportError:
            logger.warning(
                "nsepython not installed — NseProvider will fully delegate to YFinance."
            )
            self._nsepython_available = False

        self._fallback = YFinanceProvider()

    def provider_name(self) -> str:
        return "NSEPython"

    def get_historical_data(
        self,
        symbol: str,
        from_date: date,
        to_date: date,
        interval: Timeframe,
    ) -> Sequence[CandleData]:
        if not self._nsepython_available or interval in _INTRADAY_TIMEFRAMES:
            logger.debug(
                "[%s] Delegating %s %s to YFinance fallback",
                self.provider_name(), symbol, interval,
            )
            return self._fallback.get_historical_data(symbol, from_date, to_date, interval)

        return self._fetch_eod(symbol, from_date, to_date, interval)

    def _fetch_eod(
        self,
        symbol: str,
        from_date: date,
        to_date: date,
        interval: Timeframe,
    ) -> list[CandleData]:
        import nsepython as nse  # type: ignore[import]

        nse_sym = _NSE_INDEX_MAP.get(symbol.upper(), symbol)
        start_str = from_date.strftime("%d-%m-%Y")
        end_str = to_date.strftime("%d-%m-%Y")

        logger.debug(
            "[%s] Fetching EOD %s %s → %s",
            self.provider_name(), nse_sym, start_str, end_str,
        )

        try:
            df = nse.index_history(nse_sym, start_str, end_str)
        except Exception as exc:
            logger.warning(
                "[%s] nsepython failed for %s: %s — falling back to YFinance",
                self.provider_name(), symbol, exc,
            )
            return list(
                self._fallback.get_historical_data(symbol, from_date, to_date, interval)
            )

        if df is None or df.empty:
            return []

        candles: list[CandleData] = []
        for _, row in df.iterrows():
            try:
                import pandas as pd
                ts = pd.to_datetime(row.get("HistoricalDate") or row.get("Date"))
                candles.append(
                    CandleData(
                        instrument=symbol,
                        candle_time=str(ts),
                        open=float(row["OPEN"]),
                        high=float(row["HIGH"]),
                        low=float(row["LOW"]),
                        close=float(row["CLOSE"]),
                        volume=int(row.get("VOLUME", 0) or 0),
                        timeframe=interval.value,
                    )
                )
            except (KeyError, ValueError) as exc:
                logger.warning("Skipping malformed row: %s — %s", row.to_dict(), exc)

        return candles

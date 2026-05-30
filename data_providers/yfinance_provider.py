from __future__ import annotations

from datetime import date, timedelta
from typing import Sequence

import logging

import pandas as pd
import yfinance as yf

from data_providers.base import CandleData, MarketDataProvider, Timeframe

# yfinance prints noisy "possibly delisted" messages via its own logger
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
from utils.logger import get_logger
from config import settings

logger = get_logger(__name__, settings.log_dir, settings.log_level)

# Maps our canonical timeframe → yfinance interval string
_YF_INTERVAL_MAP: dict[Timeframe, str] = {
    Timeframe.MIN_1: "1m",
    Timeframe.MIN_5: "5m",
    Timeframe.MIN_15: "15m",
    Timeframe.DAY_1: "1d",
}

# Hard limits imposed by Yahoo Finance per timeframe
_YF_MAX_DAYS: dict[Timeframe, int] = {
    Timeframe.MIN_1: 7,
    Timeframe.MIN_5: 60,
    Timeframe.MIN_15: 60,
    Timeframe.DAY_1: 730,
}

# Maps our canonical instrument names → Yahoo Finance tickers
_SYMBOL_MAP: dict[str, str] = {
    "NIFTY 50": "^NSEI",
    "NIFTY BANK": "^NSEBANK",
    "NIFTY": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
}


def _resolve_ticker(symbol: str) -> str:
    return _SYMBOL_MAP.get(symbol.upper(), symbol)


class YFinanceProvider(MarketDataProvider):
    """Fetches OHLCV data from Yahoo Finance (free, no auth required)."""

    def provider_name(self) -> str:
        return "YFinance"

    def get_historical_data(
        self,
        symbol: str,
        from_date: date,
        to_date: date,
        interval: Timeframe,
    ) -> Sequence[CandleData]:
        # Clamp the date range to what yfinance actually supports
        effective_from, effective_to = self._clamp_range(from_date, to_date, interval)
        if effective_from is None:
            logger.debug(
                "[%s] Skipping %s %s %s→%s — outside %d-day yfinance window",
                self.provider_name(), symbol, interval.value,
                from_date, to_date, _YF_MAX_DAYS[interval],
            )
            return []

        ticker_sym = _resolve_ticker(symbol)
        yf_interval = _YF_INTERVAL_MAP[interval]
        start = effective_from.strftime("%Y-%m-%d")
        end = effective_to.strftime("%Y-%m-%d")

        logger.debug(
            "[%s] Fetching %s (%s) %s → %s interval=%s",
            self.provider_name(), symbol, ticker_sym, start, end, yf_interval,
        )

        ticker = yf.Ticker(ticker_sym)
        df: pd.DataFrame = ticker.history(
            start=start,
            end=end,
            interval=yf_interval,
            auto_adjust=True,
            back_adjust=False,
            repair=False,
            keepna=False,
        )

        if df.empty:
            logger.debug(
                "[%s] No data returned for %s %s %s→%s",
                self.provider_name(), symbol, yf_interval, start, end,
            )
            return []

        return self._to_candles(df, symbol, interval)

    @staticmethod
    def _clamp_range(
        from_date: date, to_date: date, interval: Timeframe
    ) -> tuple[date, date] | tuple[None, None]:
        """Return (clamped_from, to_date) or (None, None) if entirely out of range."""
        earliest_allowed = date.today() - timedelta(days=_YF_MAX_DAYS[interval])
        if to_date <= earliest_allowed:
            return None, None
        clamped_from = max(from_date, earliest_allowed)
        # Need at least 1 day of range after clamping
        if clamped_from >= to_date:
            return None, None
        return clamped_from, to_date

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_candles(
        df: pd.DataFrame, symbol: str, interval: Timeframe
    ) -> list[CandleData]:
        candles: list[CandleData] = []
        for ts, row in df.iterrows():
            # Normalize timezone — store as UTC-naive for DB simplicity
            if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
                ts = ts.tz_convert("UTC").tz_localize(None)

            candles.append(
                CandleData(
                    instrument=symbol,
                    candle_time=str(ts),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=int(row.get("Volume", 0) or 0),
                    timeframe=interval.value,
                )
            )
        return candles

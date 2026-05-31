from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from config import settings
from database.connection import get_session
from database.models import MarketCandle, MarketIndicator
from database.models import TradeSignal as TradeSignalModel
from indicators.indicator_models import IndicatorRecord
from signals.signal_models import ConfidenceComponents, SignalResult, SignalType
from utils.logger import get_logger

logger = get_logger(__name__, settings.log_dir, settings.log_level)

_ZERO = Decimal("0")


class SignalEngineService:
    """Rule-based signal engine implementing the 5-condition trade signal spec.

    Signal classification rules:
        STRONG_BUY:  EMA20>EMA50>EMA200  AND RSI>60  AND Price>VWAP  AND MACD>Signal
        BUY:         EMA20>EMA50         AND RSI>55  AND Price>VWAP
        STRONG_SELL: EMA20<EMA50<EMA200  AND RSI<40  AND Price<VWAP  AND MACD<Signal
        SELL:        EMA20<EMA50         AND RSI<45  AND Price<VWAP
        NO_TRADE:    RSI in [45, 55]  OR indicators conflict

    Confidence score = clamp(50 + sum_of_component_scores // 2, 0, 100)
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        instruments: Sequence[str],
        timeframes: Sequence[str],
    ) -> dict[tuple[str, str], int]:
        """Evaluate and store signals for all (instrument, timeframe) pairs."""
        results: dict[tuple[str, str], int] = {}
        for instrument in instruments:
            for timeframe in timeframes:
                count = self.process_pair(instrument, timeframe)
                results[(instrument, timeframe)] = count
        return results

    def process_pair(self, instrument: str, timeframe: str) -> int:
        """Evaluate the latest indicator row for one pair and store the signal."""
        rec = self._get_latest_indicator(instrument, timeframe)
        if rec is None:
            logger.debug(
                "[SignalEngine] No indicators found for %s %s — run indicators first",
                instrument, timeframe,
            )
            return 0

        close_price = self._get_candle_close(instrument, timeframe, rec.candle_time)
        signal_result = self.evaluate_signal(rec, close_price or _ZERO)

        stored = self._store_signal(instrument, timeframe, rec.candle_time, signal_result)
        logger.info(
            "[SignalEngine] %s %s → %s (confidence=%d%%) — %s",
            instrument, timeframe,
            signal_result.signal_type.value,
            signal_result.confidence,
            signal_result.reason,
        )
        return stored

    def evaluate_signal(
        self, rec: IndicatorRecord, current_price: Decimal
    ) -> SignalResult:
        """Pure evaluation: score each component, classify, return SignalResult."""
        ema_score, ema_reasons = self._score_ema(rec)
        rsi_score, rsi_reasons = self._score_rsi(rec)
        vwap_score, vwap_reasons = self._score_vwap(rec, current_price)
        macd_score, macd_reasons = self._score_macd(rec)

        components = ConfidenceComponents(
            ema_score=ema_score,
            rsi_score=rsi_score,
            vwap_score=vwap_score,
            macd_score=macd_score,
            reasons=tuple(ema_reasons + rsi_reasons + vwap_reasons + macd_reasons),
        )
        signal_type = self._classify(components, rec, current_price)
        return SignalResult(
            signal_type=signal_type,
            confidence=components.confidence,
            reason="; ".join(components.reasons) or "No clear signal",
            components=components,
        )

    # ------------------------------------------------------------------
    # Scoring helpers — each returns (score, reasons)
    # ------------------------------------------------------------------

    def _score_ema(self, rec: IndicatorRecord) -> tuple[int, list[str]]:
        if rec.ema20 is None or rec.ema50 is None:
            return 0, ["EMA data insufficient"]

        if rec.ema200 is not None:
            if rec.ema20 > rec.ema50 > rec.ema200:
                return 30, ["EMA20>EMA50>EMA200 (full bullish alignment)"]
            if rec.ema20 < rec.ema50 < rec.ema200:
                return -30, ["EMA20<EMA50<EMA200 (full bearish alignment)"]

        if rec.ema20 > rec.ema50:
            return 15, ["EMA20>EMA50 (short-term bullish)"]
        if rec.ema20 < rec.ema50:
            return -15, ["EMA20<EMA50 (short-term bearish)"]
        return 0, ["EMA20≈EMA50 (flat)"]

    def _score_rsi(self, rec: IndicatorRecord) -> tuple[int, list[str]]:
        if rec.rsi14 is None:
            return 0, ["RSI data insufficient"]
        rsi = float(rec.rsi14)
        if rsi > 60:
            return 20, [f"RSI={rsi:.1f}>60 (bullish momentum)"]
        if rsi > 55:
            return 10, [f"RSI={rsi:.1f}>55 (mildly bullish)"]
        if rsi < 40:
            return -20, [f"RSI={rsi:.1f}<40 (bearish momentum)"]
        if rsi < 45:
            return -10, [f"RSI={rsi:.1f}<45 (mildly bearish)"]
        return 0, [f"RSI={rsi:.1f} in 45-55 (neutral)"]

    def _score_vwap(
        self, rec: IndicatorRecord, current_price: Decimal
    ) -> tuple[int, list[str]]:
        if rec.vwap is None or current_price == _ZERO:
            return 0, ["VWAP data insufficient"]
        if current_price > rec.vwap:
            return 20, [f"Price>{float(rec.vwap):.2f} VWAP (bullish)"]
        if current_price < rec.vwap:
            return -20, [f"Price<{float(rec.vwap):.2f} VWAP (bearish)"]
        return 0, ["Price≈VWAP"]

    def _score_macd(self, rec: IndicatorRecord) -> tuple[int, list[str]]:
        if rec.macd is None or rec.macd_signal is None:
            return 0, ["MACD data insufficient"]
        diff = float(rec.macd - rec.macd_signal)
        signal_abs = abs(float(rec.macd_signal)) if rec.macd_signal != _ZERO else 1.0
        strong_threshold = signal_abs * 0.1
        if rec.macd > rec.macd_signal:
            score = 30 if diff > strong_threshold else 15
            return score, [f"MACD>{float(rec.macd_signal):.4f} signal (bullish)"]
        if rec.macd < rec.macd_signal:
            score = -30 if abs(diff) > strong_threshold else -15
            return score, [f"MACD<{float(rec.macd_signal):.4f} signal (bearish)"]
        return 0, ["MACD≈Signal"]

    # ------------------------------------------------------------------
    # Signal classification — directly implements the 5-rule spec
    # ------------------------------------------------------------------

    def _classify(
        self,
        components: ConfidenceComponents,
        rec: IndicatorRecord,
        current_price: Decimal,
    ) -> SignalType:
        rsi = float(rec.rsi14) if rec.rsi14 is not None else 50.0

        # NO_TRADE: RSI in neutral zone 45-55
        if 45.0 <= rsi <= 55.0:
            return SignalType.NO_TRADE

        # Evaluate each rule condition explicitly
        ema20_gt_50 = bool(rec.ema20 and rec.ema50 and rec.ema20 > rec.ema50)
        ema50_gt_200 = bool(rec.ema50 and rec.ema200 and rec.ema50 > rec.ema200)
        ema20_lt_50 = bool(rec.ema20 and rec.ema50 and rec.ema20 < rec.ema50)
        ema50_lt_200 = bool(rec.ema50 and rec.ema200 and rec.ema50 < rec.ema200)
        price_gt_vwap = bool(rec.vwap and current_price > rec.vwap and current_price > _ZERO)
        price_lt_vwap = bool(rec.vwap and current_price > _ZERO and current_price < rec.vwap)
        macd_bullish = bool(rec.macd and rec.macd_signal and rec.macd > rec.macd_signal)
        macd_bearish = bool(rec.macd and rec.macd_signal and rec.macd < rec.macd_signal)

        # STRONG_BUY: all 5 bullish conditions
        if ema20_gt_50 and ema50_gt_200 and rsi > 60 and price_gt_vwap and macd_bullish:
            return SignalType.STRONG_BUY

        # BUY: EMA20>50, RSI>55, Price>VWAP (conflicting MACD → NO_TRADE)
        if ema20_gt_50 and rsi > 55 and price_gt_vwap:
            if macd_bearish:
                return SignalType.NO_TRADE
            return SignalType.BUY

        # STRONG_SELL: all 5 bearish conditions
        if ema20_lt_50 and ema50_lt_200 and rsi < 40 and price_lt_vwap and macd_bearish:
            return SignalType.STRONG_SELL

        # SELL: EMA20<50, RSI<45, Price<VWAP (conflicting MACD → NO_TRADE)
        if ema20_lt_50 and rsi < 45 and price_lt_vwap:
            if macd_bullish:
                return SignalType.NO_TRADE
            return SignalType.SELL

        # Conflicting indicators or insufficient data
        return SignalType.NO_TRADE

    # ------------------------------------------------------------------
    # Database helpers
    # ------------------------------------------------------------------

    def _get_latest_indicator(
        self, instrument: str, timeframe: str
    ) -> Optional[IndicatorRecord]:
        with get_session() as session:
            row = session.execute(
                select(MarketIndicator)
                .where(
                    MarketIndicator.instrument == instrument,
                    MarketIndicator.timeframe == timeframe,
                )
                .order_by(MarketIndicator.candle_time.desc())
                .limit(1)
            ).scalar_one_or_none()

        if row is None:
            return None

        def to_dec(v) -> Optional[Decimal]:
            return Decimal(str(v)) if v is not None else None

        return IndicatorRecord(
            instrument=row.instrument,
            candle_time=row.candle_time,
            timeframe=row.timeframe,
            ema20=to_dec(row.ema20),
            ema50=to_dec(row.ema50),
            ema200=to_dec(row.ema200),
            rsi14=to_dec(row.rsi14),
            vwap=to_dec(row.vwap),
            macd=to_dec(row.macd),
            macd_signal=to_dec(row.macd_signal),
        )

    def _get_candle_close(
        self, instrument: str, timeframe: str, candle_time: datetime
    ) -> Optional[Decimal]:
        with get_session() as session:
            close = session.execute(
                select(MarketCandle.close).where(
                    MarketCandle.instrument == instrument,
                    MarketCandle.timeframe == timeframe,
                    MarketCandle.candle_time == candle_time,
                )
            ).scalar_one_or_none()
        return Decimal(str(close)) if close is not None else None

    def _store_signal(
        self,
        instrument: str,
        timeframe: str,
        signal_time: datetime,
        result: SignalResult,
    ) -> int:
        try:
            with get_session() as session:
                res = session.execute(
                    pg_insert(TradeSignalModel)
                    .values(
                        {
                            "instrument": instrument,
                            "signal_time": signal_time,
                            "timeframe": timeframe,
                            "signal_type": result.signal_type.value,
                            "confidence": result.confidence,
                            "reason": result.reason,
                        }
                    )
                    .on_conflict_do_nothing()
                )
                return res.rowcount if res.rowcount >= 0 else 1
        except Exception as exc:
            logger.error(
                "[SignalEngine] Failed to store signal for %s %s: %s",
                instrument, timeframe, exc,
            )
            return 0

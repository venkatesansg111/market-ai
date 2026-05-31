from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal

import pandas as pd
import pytest

from indicators.indicator_engine import IndicatorEngineService
from indicators.indicator_models import IndicatorRecord


# ---------------------------------------------------------------------------
# Helpers — build a synthetic DataFrame identical to what _load_candles returns
# ---------------------------------------------------------------------------

def make_price_df(
    n: int = 50,
    start: float = 100.0,
    step: float = 0.5,
) -> pd.DataFrame:
    """Generate a monotonically rising OHLCV DataFrame."""
    closes = [start + i * step for i in range(n)]
    highs = [c + 1.0 for c in closes]
    lows = [c - 1.0 for c in closes]
    times = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "open": closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [10_000 + i * 100 for i in range(n)],
        },
        index=times,
    )


def make_flat_df(n: int = 50, price: float = 100.0) -> pd.DataFrame:
    times = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "open": [price] * n,
            "high": [price] * n,
            "low": [price] * n,
            "close": [price] * n,
            "volume": [1_000] * n,
        },
        index=times,
    )


_INSTRUMENT = "NIFTY 50"
_TIMEFRAME = "1day"


# ---------------------------------------------------------------------------
# _calculate_all — presence of new columns
# ---------------------------------------------------------------------------

class TestCalculateAll:
    """Tests for IndicatorEngineService._calculate_all via direct invocation."""

    def _engine(self) -> IndicatorEngineService:
        return IndicatorEngineService()

    def test_calculates_atr_14_column(self):
        df = make_price_df(50)
        result = self._engine()._calculate_all(df)
        assert "atr_14" in result.columns

    def test_calculates_adx_14_column(self):
        df = make_price_df(50)
        result = self._engine()._calculate_all(df)
        assert "adx_14" in result.columns

    def test_calculates_plus_di_column(self):
        df = make_price_df(50)
        result = self._engine()._calculate_all(df)
        assert "plus_di" in result.columns

    def test_calculates_minus_di_column(self):
        df = make_price_df(50)
        result = self._engine()._calculate_all(df)
        assert "minus_di" in result.columns

    def test_calculates_bb_columns(self):
        df = make_price_df(50)
        result = self._engine()._calculate_all(df)
        for col in ["bb_middle", "bb_upper", "bb_lower", "bb_width"]:
            assert col in result.columns, f"Missing column: {col}"

    def test_calculates_supertrend_column(self):
        df = make_price_df(50)
        result = self._engine()._calculate_all(df)
        assert "supertrend" in result.columns

    def test_calculates_supertrend_direction_column(self):
        df = make_price_df(50)
        result = self._engine()._calculate_all(df)
        assert "supertrend_direction" in result.columns

    def test_calculates_obv_column(self):
        df = make_price_df(50)
        result = self._engine()._calculate_all(df)
        assert "obv" in result.columns

    def test_calculates_stoch_rsi_k_column(self):
        df = make_price_df(50)
        result = self._engine()._calculate_all(df)
        assert "stoch_rsi_k" in result.columns

    def test_calculates_stoch_rsi_d_column(self):
        df = make_price_df(50)
        result = self._engine()._calculate_all(df)
        assert "stoch_rsi_d" in result.columns

    def test_preserves_original_phase1_columns(self):
        df = make_price_df(50)
        result = self._engine()._calculate_all(df)
        for col in ["ema20", "ema50", "ema200", "rsi14", "vwap", "macd", "macd_signal"]:
            assert col in result.columns, f"Phase 1 column missing: {col}"

    def test_does_not_modify_input_dataframe(self):
        df = make_price_df(50)
        original_columns = list(df.columns)
        self._engine()._calculate_all(df)
        assert list(df.columns) == original_columns

    def test_output_length_equals_input_length(self):
        df = make_price_df(50)
        result = self._engine()._calculate_all(df)
        assert len(result) == len(df)


# ---------------------------------------------------------------------------
# _df_to_records — IndicatorRecord field mapping
# ---------------------------------------------------------------------------

class TestDfToRecords:
    """Tests for IndicatorEngineService._df_to_records via direct invocation."""

    def _engine(self) -> IndicatorEngineService:
        return IndicatorEngineService()

    def _full_df(self, n: int = 50) -> pd.DataFrame:
        df = make_price_df(n)
        return self._engine()._calculate_all(df)

    def test_returns_list_of_indicator_records(self):
        engine = self._engine()
        df = self._full_df()
        records = engine._df_to_records(df, _INSTRUMENT, _TIMEFRAME)
        assert all(isinstance(r, IndicatorRecord) for r in records)

    def test_record_count_equals_df_length(self):
        engine = self._engine()
        df = self._full_df()
        records = engine._df_to_records(df, _INSTRUMENT, _TIMEFRAME)
        assert len(records) == len(df)

    def test_atr_14_is_none_or_decimal(self):
        engine = self._engine()
        df = self._full_df()
        records = engine._df_to_records(df, _INSTRUMENT, _TIMEFRAME)
        for r in records:
            assert r.atr_14 is None or isinstance(r.atr_14, Decimal)

    def test_adx_14_is_none_or_decimal(self):
        engine = self._engine()
        df = self._full_df()
        records = engine._df_to_records(df, _INSTRUMENT, _TIMEFRAME)
        for r in records:
            assert r.adx_14 is None or isinstance(r.adx_14, Decimal)

    def test_supertrend_direction_is_none_or_int(self):
        engine = self._engine()
        df = self._full_df()
        records = engine._df_to_records(df, _INSTRUMENT, _TIMEFRAME)
        for r in records:
            assert r.supertrend_direction is None or isinstance(r.supertrend_direction, int)

    def test_supertrend_direction_values_only_1_or_minus1(self):
        engine = self._engine()
        df = self._full_df()
        records = engine._df_to_records(df, _INSTRUMENT, _TIMEFRAME)
        for r in records:
            if r.supertrend_direction is not None:
                assert r.supertrend_direction in (1, -1), (
                    f"direction must be 1 or -1, got {r.supertrend_direction}"
                )

    def test_obv_is_none_or_decimal(self):
        engine = self._engine()
        df = self._full_df()
        records = engine._df_to_records(df, _INSTRUMENT, _TIMEFRAME)
        for r in records:
            assert r.obv is None or isinstance(r.obv, Decimal)

    def test_bb_upper_geq_bb_middle_when_both_present(self):
        engine = self._engine()
        df = self._full_df(60)
        records = engine._df_to_records(df, _INSTRUMENT, _TIMEFRAME)
        for r in records:
            if r.bb_upper is not None and r.bb_middle is not None:
                assert r.bb_upper >= r.bb_middle

    def test_bb_lower_leq_bb_middle_when_both_present(self):
        engine = self._engine()
        df = self._full_df(60)
        records = engine._df_to_records(df, _INSTRUMENT, _TIMEFRAME)
        for r in records:
            if r.bb_lower is not None and r.bb_middle is not None:
                assert r.bb_lower <= r.bb_middle

    def test_instrument_and_timeframe_propagated(self):
        engine = self._engine()
        df = self._full_df()
        records = engine._df_to_records(df, _INSTRUMENT, _TIMEFRAME)
        for r in records:
            assert r.instrument == _INSTRUMENT
            assert r.timeframe == _TIMEFRAME


# ---------------------------------------------------------------------------
# NaN → None conversion
# ---------------------------------------------------------------------------

class TestNanToNone:
    """Ensures NaN values in the DataFrame become None in IndicatorRecord."""

    def _engine(self) -> IndicatorEngineService:
        return IndicatorEngineService()

    def test_nan_atr_becomes_none(self):
        engine = self._engine()
        df = make_price_df(5)  # too few for ATR-14 warmup
        df = engine._calculate_all(df)
        records = engine._df_to_records(df, _INSTRUMENT, _TIMEFRAME)
        # With only 5 bars, all ATR values should be None
        assert all(r.atr_14 is None for r in records)

    def test_nan_adx_becomes_none(self):
        engine = self._engine()
        df = make_price_df(10)  # too few for ADX-14 (needs ~28)
        df = engine._calculate_all(df)
        records = engine._df_to_records(df, _INSTRUMENT, _TIMEFRAME)
        assert all(r.adx_14 is None for r in records)

    def test_nan_bb_becomes_none(self):
        engine = self._engine()
        df = make_price_df(15)  # too few for BB-20
        df = engine._calculate_all(df)
        records = engine._df_to_records(df, _INSTRUMENT, _TIMEFRAME)
        assert all(r.bb_middle is None for r in records)

    def test_nan_supertrend_direction_becomes_none(self):
        engine = self._engine()
        df = make_price_df(5)
        df = engine._calculate_all(df)
        records = engine._df_to_records(df, _INSTRUMENT, _TIMEFRAME)
        assert all(r.supertrend_direction is None for r in records)


# ---------------------------------------------------------------------------
# Phase 1 backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    """Ensure existing indicator fields still work correctly after Phase 4B changes."""

    def _engine(self) -> IndicatorEngineService:
        return IndicatorEngineService()

    def test_ema20_still_populated(self):
        engine = self._engine()
        df = make_price_df(50)
        df = engine._calculate_all(df)
        records = engine._df_to_records(df, _INSTRUMENT, _TIMEFRAME)
        # Last bar should have EMA20 after 50 bars
        assert records[-1].ema20 is not None

    def test_rsi14_still_populated(self):
        engine = self._engine()
        df = make_price_df(50)
        df = engine._calculate_all(df)
        records = engine._df_to_records(df, _INSTRUMENT, _TIMEFRAME)
        assert records[-1].rsi14 is not None

    def test_macd_still_populated(self):
        engine = self._engine()
        df = make_price_df(50)
        df = engine._calculate_all(df)
        records = engine._df_to_records(df, _INSTRUMENT, _TIMEFRAME)
        assert records[-1].macd is not None

    def test_indicator_record_frozen(self):
        r = IndicatorRecord(
            instrument=_INSTRUMENT,
            candle_time=datetime(2024, 1, 1),
            timeframe=_TIMEFRAME,
        )
        with pytest.raises((AttributeError, TypeError)):
            r.ema20 = Decimal("100")  # type: ignore[misc]

    def test_indicator_record_all_new_fields_default_none(self):
        r = IndicatorRecord(
            instrument=_INSTRUMENT,
            candle_time=datetime(2024, 1, 1),
            timeframe=_TIMEFRAME,
        )
        for field in [
            "atr_14", "adx_14", "plus_di", "minus_di",
            "bb_middle", "bb_upper", "bb_lower", "bb_width",
            "supertrend", "supertrend_direction",
            "obv", "stoch_rsi_k", "stoch_rsi_d",
        ]:
            assert getattr(r, field) is None, f"{field} should default to None"

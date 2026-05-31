from __future__ import annotations

import pytest

from indicators.indicator_metadata import IndicatorCategory, IndicatorDefinition
from indicators.indicator_registry import (
    INDICATORS,
    get_indicator,
    list_indicators,
)


# ---------------------------------------------------------------------------
# list_indicators
# ---------------------------------------------------------------------------

class TestListIndicators:
    def test_returns_list(self):
        result = list_indicators()
        assert isinstance(result, list)

    def test_contains_all_expected_keys(self):
        result = list_indicators()
        expected = {
            "ema20", "ema50", "ema200", "rsi14", "macd",
            "stoch_rsi", "vwap", "atr14", "bb20", "supertrend", "obv", "adx14",
        }
        assert set(result) == expected

    def test_contains_exactly_12_indicators(self):
        assert len(list_indicators()) == 12

    def test_order_is_stable(self):
        # Two calls must return the same order
        assert list_indicators() == list_indicators()

    def test_all_entries_are_strings(self):
        for name in list_indicators():
            assert isinstance(name, str)


# ---------------------------------------------------------------------------
# get_indicator — happy path
# ---------------------------------------------------------------------------

class TestGetIndicator:
    def test_get_ema20_returns_definition(self):
        defn = get_indicator("ema20")
        assert isinstance(defn, IndicatorDefinition)

    def test_get_atr14_returns_correct_name(self):
        defn = get_indicator("atr14")
        assert defn.name == "atr14"

    def test_get_adx14_returns_correct_name(self):
        defn = get_indicator("adx14")
        assert defn.name == "adx14"

    def test_get_bb20_returns_correct_name(self):
        defn = get_indicator("bb20")
        assert defn.name == "bb20"

    def test_get_supertrend_returns_correct_name(self):
        defn = get_indicator("supertrend")
        assert defn.name == "supertrend"

    def test_get_obv_returns_correct_name(self):
        defn = get_indicator("obv")
        assert defn.name == "obv"

    def test_get_stoch_rsi_returns_correct_name(self):
        defn = get_indicator("stoch_rsi")
        assert defn.name == "stoch_rsi"

    def test_case_insensitive_lookup(self):
        defn_lower = get_indicator("atr14")
        defn_upper = get_indicator("ATR14")
        assert defn_lower.name == defn_upper.name

    def test_case_insensitive_mixed_case(self):
        defn = get_indicator("Bb20")
        assert defn.name == "bb20"


# ---------------------------------------------------------------------------
# get_indicator — error handling
# ---------------------------------------------------------------------------

class TestGetIndicatorErrors:
    def test_unknown_name_raises_key_error(self):
        with pytest.raises(KeyError):
            get_indicator("unknown_indicator")

    def test_empty_string_raises_key_error(self):
        with pytest.raises(KeyError):
            get_indicator("")

    def test_key_error_message_lists_available(self):
        with pytest.raises(KeyError, match="Available"):
            get_indicator("nonexistent")

    def test_key_error_includes_the_unknown_name(self):
        with pytest.raises(KeyError, match="bogus_indicator"):
            get_indicator("bogus_indicator")


# ---------------------------------------------------------------------------
# IndicatorDefinition field validation
# ---------------------------------------------------------------------------

class TestDefinitionFields:
    def test_all_definitions_have_non_empty_description(self):
        for name in list_indicators():
            defn = get_indicator(name)
            assert len(defn.description) > 0, f"{name}: empty description"

    def test_all_definitions_have_required_columns(self):
        for name in list_indicators():
            defn = get_indicator(name)
            assert len(defn.required_columns) > 0, f"{name}: no required_columns"

    def test_all_definitions_have_output_columns(self):
        for name in list_indicators():
            defn = get_indicator(name)
            assert len(defn.output_columns) > 0, f"{name}: no output_columns"

    def test_all_warmup_periods_non_negative(self):
        for name in list_indicators():
            defn = get_indicator(name)
            assert defn.warmup_period >= 0, f"{name}: negative warmup_period"

    def test_all_categories_are_valid(self):
        valid_categories = set(IndicatorCategory)
        for name in list_indicators():
            defn = get_indicator(name)
            assert defn.category in valid_categories, f"{name}: invalid category"

    def test_required_columns_are_strings(self):
        for name in list_indicators():
            defn = get_indicator(name)
            for col in defn.required_columns:
                assert isinstance(col, str), f"{name}: non-string required column"

    def test_output_columns_are_strings(self):
        for name in list_indicators():
            defn = get_indicator(name)
            for col in defn.output_columns:
                assert isinstance(col, str), f"{name}: non-string output column"


# ---------------------------------------------------------------------------
# Category classification correctness
# ---------------------------------------------------------------------------

class TestCategoryClassification:
    def test_ema20_is_trend(self):
        assert get_indicator("ema20").category == IndicatorCategory.TREND

    def test_ema50_is_trend(self):
        assert get_indicator("ema50").category == IndicatorCategory.TREND

    def test_ema200_is_trend(self):
        assert get_indicator("ema200").category == IndicatorCategory.TREND

    def test_adx14_is_trend(self):
        assert get_indicator("adx14").category == IndicatorCategory.TREND

    def test_rsi14_is_momentum(self):
        assert get_indicator("rsi14").category == IndicatorCategory.MOMENTUM

    def test_macd_is_momentum(self):
        assert get_indicator("macd").category == IndicatorCategory.MOMENTUM

    def test_stoch_rsi_is_momentum(self):
        assert get_indicator("stoch_rsi").category == IndicatorCategory.MOMENTUM

    def test_atr14_is_volatility(self):
        assert get_indicator("atr14").category == IndicatorCategory.VOLATILITY

    def test_bb20_is_volatility(self):
        assert get_indicator("bb20").category == IndicatorCategory.VOLATILITY

    def test_vwap_is_volatility(self):
        assert get_indicator("vwap").category == IndicatorCategory.VOLATILITY

    def test_supertrend_is_volatility(self):
        assert get_indicator("supertrend").category == IndicatorCategory.VOLATILITY

    def test_obv_is_volume(self):
        assert get_indicator("obv").category == IndicatorCategory.VOLUME


# ---------------------------------------------------------------------------
# Output columns match IndicatorRecord field names
# ---------------------------------------------------------------------------

class TestOutputColumnNames:
    def test_atr14_output_columns(self):
        assert get_indicator("atr14").output_columns == ["atr_14"]

    def test_adx14_output_columns(self):
        defn = get_indicator("adx14")
        assert "adx_14" in defn.output_columns
        assert "plus_di" in defn.output_columns
        assert "minus_di" in defn.output_columns

    def test_bb20_output_columns(self):
        defn = get_indicator("bb20")
        assert "bb_middle" in defn.output_columns
        assert "bb_upper" in defn.output_columns
        assert "bb_lower" in defn.output_columns
        assert "bb_width" in defn.output_columns

    def test_supertrend_output_columns(self):
        defn = get_indicator("supertrend")
        assert "supertrend" in defn.output_columns
        assert "supertrend_direction" in defn.output_columns

    def test_obv_output_columns(self):
        assert get_indicator("obv").output_columns == ["obv"]

    def test_stoch_rsi_output_columns(self):
        defn = get_indicator("stoch_rsi")
        assert "stoch_rsi_k" in defn.output_columns
        assert "stoch_rsi_d" in defn.output_columns


# ---------------------------------------------------------------------------
# Warmup period sanity checks
# ---------------------------------------------------------------------------

class TestWarmupPeriods:
    def test_ema200_warmup_is_200(self):
        assert get_indicator("ema200").warmup_period == 200

    def test_atr14_warmup_is_14(self):
        assert get_indicator("atr14").warmup_period == 14

    def test_bb20_warmup_is_20(self):
        assert get_indicator("bb20").warmup_period == 20

    def test_obv_warmup_is_1(self):
        assert get_indicator("obv").warmup_period == 1

    def test_adx14_warmup_greater_than_14(self):
        # ADX needs two rounds of smoothing; warmup should be > 14
        assert get_indicator("adx14").warmup_period > 14

    def test_stoch_rsi_warmup_greater_than_14(self):
        # StochRSI needs RSI warmup + stoch window; warmup > 14
        assert get_indicator("stoch_rsi").warmup_period > 14


# ---------------------------------------------------------------------------
# INDICATORS dict integrity
# ---------------------------------------------------------------------------

class TestIndicatorsDictIntegrity:
    def test_all_keys_match_definition_names(self):
        for key, defn in INDICATORS.items():
            assert key == defn.name, f"Key '{key}' != definition name '{defn.name}'"

    def test_all_values_are_indicator_definitions(self):
        for key, defn in INDICATORS.items():
            assert isinstance(defn, IndicatorDefinition), f"{key}: not IndicatorDefinition"

    def test_definitions_are_frozen(self):
        defn = get_indicator("atr14")
        with pytest.raises((AttributeError, TypeError)):
            defn.name = "should_not_work"  # type: ignore[misc]

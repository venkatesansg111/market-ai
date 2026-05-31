from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class IndicatorCategory(StrEnum):
    """Functional classification of technical indicators."""

    TREND = "TREND"
    MOMENTUM = "MOMENTUM"
    VOLATILITY = "VOLATILITY"
    VOLUME = "VOLUME"


@dataclass(frozen=True)
class IndicatorDefinition:
    """Metadata descriptor for a single technical indicator.

    Attributes:
        name:             Registry key used in INDICATORS dict (e.g. "atr14").
        description:      Human-readable summary of the indicator.
        required_columns: DataFrame column names required as input
                          (subset of: open, high, low, close, volume).
        output_columns:   Names of the columns produced, matching IndicatorRecord
                          field names (e.g. ["adx_14", "plus_di", "minus_di"]).
        warmup_period:    Minimum number of bars before the first valid output.
                          Rows below this count will be NaN / None.
        category:         IndicatorCategory classification.
    """

    name: str
    description: str
    required_columns: list[str]
    output_columns: list[str]
    warmup_period: int
    category: IndicatorCategory

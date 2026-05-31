from __future__ import annotations

import pandas as pd
import pytest

from indicators.advanced_calculators import calculate_obv


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_series(closes, volumes=None):
    n = len(closes)
    c = pd.Series(closes, dtype=float)
    v = pd.Series(volumes if volumes is not None else [1_000] * n, dtype=float)
    return c, v


# ---------------------------------------------------------------------------
# Basic cumulative behaviour
# ---------------------------------------------------------------------------

class TestCumulativeBehaviour:
    def test_all_up_closes_obv_monotonically_increases(self):
        closes = [100, 101, 102, 103, 104, 105]
        volumes = [1000, 1000, 1000, 1000, 1000, 1000]
        c, v = make_series(closes, volumes)
        result = calculate_obv(c, v)
        # Every bar is an up-close → OBV adds volume each bar
        for i in range(1, len(result)):
            assert float(result.iloc[i]) > float(result.iloc[i - 1])

    def test_all_down_closes_obv_monotonically_decreases(self):
        closes = [105, 104, 103, 102, 101, 100]
        volumes = [1000, 1000, 1000, 1000, 1000, 1000]
        c, v = make_series(closes, volumes)
        result = calculate_obv(c, v)
        # Every bar from bar 1 is a down-close → OBV loses volume each bar
        for i in range(2, len(result)):
            assert float(result.iloc[i]) < float(result.iloc[i - 1])

    def test_flat_closes_obv_unchanged(self):
        closes = [100, 100, 100, 100, 100]
        volumes = [500, 500, 500, 500, 500]
        c, v = make_series(closes, volumes)
        result = calculate_obv(c, v)
        # After bar 0, flat closes → OBV stays at bar-0 value
        for i in range(1, len(result)):
            assert float(result.iloc[i]) == float(result.iloc[0])

    def test_known_obv_sequence(self):
        # up, up, down, flat, up
        closes = [100, 101, 102, 101, 101, 103]
        volumes = [100, 200, 300, 400, 500, 600]
        c, v = make_series(closes, volumes)
        result = calculate_obv(c, v)
        # Bar 0: OBV = 100 (first bar positive by convention)
        assert float(result.iloc[0]) == 100.0
        # Bar 1 (up): 100 + 200 = 300
        assert float(result.iloc[1]) == 300.0
        # Bar 2 (up): 300 + 300 = 600
        assert float(result.iloc[2]) == 600.0
        # Bar 3 (down): 600 - 400 = 200
        assert float(result.iloc[3]) == 200.0
        # Bar 4 (flat): 200 + 0 = 200
        assert float(result.iloc[4]) == 200.0
        # Bar 5 (up): 200 + 600 = 800
        assert float(result.iloc[5]) == 800.0


# ---------------------------------------------------------------------------
# No warmup — all bars valid
# ---------------------------------------------------------------------------

class TestNoWarmup:
    def test_all_bars_are_valid_no_nan(self):
        c, v = make_series([100, 101, 102], [1000, 1000, 1000])
        result = calculate_obv(c, v)
        assert result.notna().sum() == 3

    def test_single_bar_is_valid(self):
        c, v = make_series([100], [5000])
        result = calculate_obv(c, v)
        assert not pd.isna(result.iloc[0])
        assert float(result.iloc[0]) == 5000.0

    def test_output_named_obv(self):
        c, v = make_series([100, 101], [1000, 1000])
        result = calculate_obv(c, v)
        assert result.name == "obv"


# ---------------------------------------------------------------------------
# Volume spikes
# ---------------------------------------------------------------------------

class TestVolumeSpike:
    def test_volume_spike_on_up_close_jumps_obv(self):
        closes = [100, 101, 102, 103, 104]
        # Bar 3 has a volume spike
        volumes = [1000, 1000, 1000, 50_000, 1000]
        c, v = make_series(closes, volumes)
        result = calculate_obv(c, v)
        # OBV jump at bar 3 should be much larger than surrounding bars
        delta_before = float(result.iloc[2]) - float(result.iloc[1])
        delta_spike = float(result.iloc[3]) - float(result.iloc[2])
        assert delta_spike > delta_before * 10

    def test_volume_spike_on_down_close_drops_obv_sharply(self):
        closes = [105, 104, 103, 102, 101]
        # Bar 3 (down-close) has volume spike
        volumes = [1000, 1000, 1000, 50_000, 1000]
        c, v = make_series(closes, volumes)
        result = calculate_obv(c, v)
        # From bar 2 to bar 3, OBV should drop sharply
        delta_spike = float(result.iloc[2]) - float(result.iloc[3])
        assert delta_spike == pytest.approx(50_000.0)

    def test_zero_volume_bars_do_not_change_obv(self):
        closes = [100, 101, 102, 103]
        volumes = [1000, 0, 0, 1000]
        c, v = make_series(closes, volumes)
        result = calculate_obv(c, v)
        # Bars 1 and 2 have zero volume → OBV stays same as bar 0
        assert float(result.iloc[1]) == float(result.iloc[0])
        assert float(result.iloc[2]) == float(result.iloc[0])


# ---------------------------------------------------------------------------
# Constant volume
# ---------------------------------------------------------------------------

class TestConstantVolume:
    def test_constant_volume_obv_changes_by_volume_each_move(self):
        closes = [100, 101, 100, 101, 100]
        volumes = [500, 500, 500, 500, 500]
        c, v = make_series(closes, volumes)
        result = calculate_obv(c, v)
        # Bar 0: +500, Bar 1 (up): +500=1000, Bar 2 (down): -500=500, etc.
        assert float(result.iloc[0]) == 500.0
        assert float(result.iloc[1]) == 1000.0
        assert float(result.iloc[2]) == 500.0
        assert float(result.iloc[3]) == 1000.0
        assert float(result.iloc[4]) == 500.0


# ---------------------------------------------------------------------------
# OBV divergence concept (structural test)
# ---------------------------------------------------------------------------

class TestDivergence:
    def test_price_rising_obv_falling_represents_divergence(self):
        # Price trend: up; Volume trend: down-closes have big volume
        closes = [100, 101, 102, 103, 104, 103, 104, 105, 104, 105]
        # Alternating pattern where down-close bars carry more volume
        volumes = [1000, 500, 500, 500, 500, 5000, 500, 500, 5000, 500]
        c, v = make_series(closes, volumes)
        result = calculate_obv(c, v)
        # OBV should be calculable for all bars
        assert result.notna().sum() == len(closes)
        # Sanity: result is finite
        assert all(float(val) != float("inf") for val in result)

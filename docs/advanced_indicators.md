# Advanced Indicators — Phase 4B

This document describes the six new technical indicators introduced in Phase 4B,
covering formulas, warmup requirements, interpretation, database fields, and
planned strategy usage.

---

## Table of Contents

1. [ATR — Average True Range](#1-atr--average-true-range)
2. [ADX — Average Directional Index](#2-adx--average-directional-index)
3. [Bollinger Bands](#3-bollinger-bands)
4. [Supertrend](#4-supertrend)
5. [OBV — On Balance Volume](#5-obv--on-balance-volume)
6. [Stochastic RSI](#6-stochastic-rsi)
7. [Database Fields](#7-database-fields)
8. [Indicator Registry](#8-indicator-registry)
9. [Strategy Integration](#9-strategy-integration)
10. [Warmup Summary](#10-warmup-summary)

---

## 1. ATR — Average True Range

**Category:** Volatility  
**Period:** 14  
**Output column:** `atr_14`

### Formula

```
True Range (TR) = max(
    High − Low,
    |High − Prev_Close|,
    |Low  − Prev_Close|
)

ATR(14) = Wilder's EWM of TR,  alpha = 1/14
```

Wilder's smoothing (EWM with `adjust=False`, `alpha=1/period`) is equivalent to:

```
ATR[t] = ATR[t-1] × (13/14) + TR[t] × (1/14)
```

### Warmup

14 bars minimum. NaN for the first 13 bars.

### Interpretation

| ATR value | Meaning |
|-----------|---------|
| Rising    | Increasing volatility (large bars, gaps) |
| Falling   | Decreasing volatility (compression before breakout) |
| High      | Use wider stop-losses; position size down |
| Low       | Use tighter stop-losses; potential breakout approaching |

ATR is always ≥ 0. It does **not** indicate direction, only magnitude.

---

## 2. ADX — Average Directional Index

**Category:** Trend  
**Period:** 14  
**Output columns:** `adx_14`, `plus_di`, `minus_di`

### Formula

```
+DM[t] = High[t] − High[t-1]  if (+DM > −DM and +DM > 0)  else 0
−DM[t] = Low[t-1] − Low[t]   if (−DM > +DM and −DM > 0)  else 0

Smooth all with Wilder's (alpha=1/14):
  ATR = Wilder(TR, 14)
  +DI = 100 × Wilder(+DM, 14) / ATR
  −DI = 100 × Wilder(−DM, 14) / ATR

  DX  = 100 × |+DI − −DI| / (+DI + −DI)
  ADX = Wilder(DX, 14)
```

### Warmup

~28 bars (14 for the DI smoothing + 14 for the ADX smoothing of DX).

### Interpretation

| ADX Value | Trend Strength |
|-----------|---------------|
| < 20      | No trend / ranging |
| 20–25     | Emerging trend |
| 25–50     | Strong trend |
| > 50      | Very strong trend |

- `plus_di > minus_di`: Bullish directional bias  
- `minus_di > plus_di`: Bearish directional bias  
- ADX measures **strength**, not direction. ADX can be high in both up- and downtrends.

---

## 3. Bollinger Bands

**Category:** Volatility  
**Period:** 20, StdDev multiplier: 2  
**Output columns:** `bb_middle`, `bb_upper`, `bb_lower`, `bb_width`

### Formula

```
Middle = SMA(Close, 20)
StdDev = Rolling sample std dev (ddof=1) over 20 bars
Upper  = Middle + 2 × StdDev
Lower  = Middle − 2 × StdDev
Width  = (Upper − Lower) / Middle      ← normalised band width
```

### Warmup

20 bars. NaN for the first 19 bars.

### Interpretation

| Condition | Signal |
|-----------|--------|
| Price touches Upper Band | Potentially overbought; watch for reversal |
| Price touches Lower Band | Potentially oversold; watch for reversal |
| Width expanding          | Volatility increasing; trend strengthening |
| Width contracting (Squeeze) | Low volatility; potential breakout |
| Price walks Upper Band   | Strong uptrend |
| Price walks Lower Band   | Strong downtrend |

Width ≈ 0 indicates a Bollinger Squeeze — historically precedes large moves.

---

## 4. Supertrend

**Category:** Volatility / Trend-following  
**Period (ATR):** 10, Multiplier: 3  
**Output columns:** `supertrend`, `supertrend_direction`

### Formula

```
HL2         = (High + Low) / 2
ATR         = calculate_atr(period=10)

Raw Upper   = HL2 + multiplier × ATR
Raw Lower   = HL2 − multiplier × ATR

Band locking (prevents whipsaws):
  Final_Upper[t] = min(Raw_Upper[t], Final_Upper[t-1])
                   unless Close[t-1] > Final_Upper[t-1]  → reset to Raw_Upper[t]
  Final_Lower[t] = max(Raw_Lower[t], Final_Lower[t-1])
                   unless Close[t-1] < Final_Lower[t-1]  → reset to Raw_Lower[t]

Direction and Supertrend value:
  If previous bar was bearish (supertrend = upper band):
    Close[t] > Final_Upper[t] → flip Bullish; supertrend = Final_Lower[t]
    else                      → stay Bearish; supertrend = Final_Upper[t]

  If previous bar was bullish (supertrend = lower band):
    Close[t] < Final_Lower[t] → flip Bearish; supertrend = Final_Upper[t]
    else                      → stay Bullish; supertrend = Final_Lower[t]
```

### Warmup

10 bars (ATR10 warmup). NaN for bars before ATR is valid.

### Direction encoding

| Value | Meaning |
|-------|---------|
| `1`   | Bullish — price is above Supertrend line |
| `-1`  | Bearish — price is below Supertrend line |
| `NULL`| Warmup / insufficient data |

### Interpretation

- A direction flip from −1 → 1 is a **Buy signal**  
- A direction flip from 1 → −1 is a **Sell signal**  
- The Supertrend value acts as a dynamic support (bullish) / resistance (bearish) level  
- Works best in trending markets; generates whipsaws in ranging conditions

---

## 5. OBV — On Balance Volume

**Category:** Volume  
**Output column:** `obv`

### Formula

```
OBV[0] = Volume[0]     (first bar, baseline)

OBV[t] = OBV[t-1] + Volume[t]   if Close[t] > Close[t-1]
OBV[t] = OBV[t-1] − Volume[t]   if Close[t] < Close[t-1]
OBV[t] = OBV[t-1]               if Close[t] == Close[t-1]
```

### Warmup

None — valid from bar 1.

### Interpretation

| Condition | Signal |
|-----------|--------|
| OBV rising with price rising | Strong bullish confirmation |
| OBV falling with price falling | Strong bearish confirmation |
| OBV rising, price flat/falling | Bullish divergence (accumulation) |
| OBV falling, price flat/rising | Bearish divergence (distribution) |

OBV is a leading indicator — divergence between OBV and price often precedes price reversal.  
Absolute OBV value is meaningless; only the **slope and divergence** matter.

---

## 6. Stochastic RSI

**Category:** Momentum  
**RSI Period:** 14, Stochastic Period: 14  
**Output columns:** `stoch_rsi_k`, `stoch_rsi_d`

### Formula

```
RSI        = RSI(Close, 14)           (Wilder's smoothing)
RSI_min    = Rolling min(RSI, 14)
RSI_max    = Rolling max(RSI, 14)

%K = 100 × (RSI − RSI_min) / (RSI_max − RSI_min)
%D = SMA(%K, 3)
```

When `RSI_max == RSI_min` (constant RSI over the window), %K is undefined → `NULL`.

### Warmup

%K: ~28 bars (14 RSI + 14 stochastic window).  
%D: ~30 bars (28 + 3-bar SMA).

### Interpretation

| Value | Condition |
|-------|-----------|
| %K > 80 | Overbought — watch for pullback |
| %K < 20 | Oversold — watch for bounce |
| %K crosses above %D | Bullish momentum signal |
| %K crosses below %D | Bearish momentum signal |

Stoch RSI is more sensitive than plain RSI — generates more signals in fast-moving markets.  
Best used on higher timeframes (1day, 1week) to filter noise.

---

## 7. Database Fields

All new fields are added as **nullable** columns to the `market_indicators` table.  
Existing rows are unaffected (columns default to `NULL`).

```sql
ALTER TABLE market_indicators ADD COLUMN atr_14           NUMERIC(18,6);
ALTER TABLE market_indicators ADD COLUMN adx_14           NUMERIC(8,4);
ALTER TABLE market_indicators ADD COLUMN plus_di          NUMERIC(8,4);
ALTER TABLE market_indicators ADD COLUMN minus_di         NUMERIC(8,4);
ALTER TABLE market_indicators ADD COLUMN bb_middle        NUMERIC(18,6);
ALTER TABLE market_indicators ADD COLUMN bb_upper         NUMERIC(18,6);
ALTER TABLE market_indicators ADD COLUMN bb_lower         NUMERIC(18,6);
ALTER TABLE market_indicators ADD COLUMN bb_width         NUMERIC(10,8);
ALTER TABLE market_indicators ADD COLUMN supertrend       NUMERIC(18,6);
ALTER TABLE market_indicators ADD COLUMN supertrend_direction INTEGER;
ALTER TABLE market_indicators ADD COLUMN obv              NUMERIC(18,2);
ALTER TABLE market_indicators ADD COLUMN stoch_rsi_k      NUMERIC(8,4);
ALTER TABLE market_indicators ADD COLUMN stoch_rsi_d      NUMERIC(8,4);
```

> In production, run `python main.py --mode indicators` after applying the schema
> change (or let `create_tables()` handle it via SQLAlchemy `create_all`).

---

## 8. Indicator Registry

The registry (`indicators/indicator_registry.py`) maps short names to
`IndicatorDefinition` objects:

```python
from indicators.indicator_registry import get_indicator, list_indicators, INDICATORS

# List all registered indicators
print(list_indicators())
# ['ema20', 'ema50', 'ema200', 'rsi14', 'macd', 'stoch_rsi',
#  'vwap', 'atr14', 'bb20', 'supertrend', 'obv', 'adx14']

# Get metadata for a specific indicator
defn = get_indicator("atr14")
print(defn.warmup_period)   # 14
print(defn.category)        # VOLATILITY
print(defn.output_columns)  # ['atr_14']
```

**`IndicatorDefinition` fields:**

| Field              | Type                | Description |
|--------------------|---------------------|-------------|
| `name`             | `str`               | Registry key |
| `description`      | `str`               | Human-readable summary |
| `required_columns` | `list[str]`         | Input DataFrame columns |
| `output_columns`   | `list[str]`         | IndicatorRecord field names produced |
| `warmup_period`    | `int`               | Minimum bars before first valid output |
| `category`         | `IndicatorCategory` | TREND / MOMENTUM / VOLATILITY / VOLUME |

---

## 9. Strategy Integration

Existing strategies declare their indicator dependencies via `required_indicators`.
Phase 4B extends these declarations while keeping `generate_signal()` logic unchanged —
new indicators are available but not yet driving signals (reserved for future phases).

| Strategy          | New indicators declared | Usage |
|-------------------|------------------------|-------|
| `EmaCrossoverStrategy` | `adx_14`, `supertrend` | Trend confirmation in future multi-timeframe engine |
| `MomentumStrategy`     | `adx_14`, `obv`         | Trend strength filter + volume confirmation |

**Graceful degradation:** All strategies handle `None` values for any indicator.  
A strategy with `adx_14=None` in `IndicatorRecord` continues to function using only
its primary indicators.

### Future usage examples

```python
# Future trend-confluence strategy (Phase 5+)
class TrendConfluenceStrategy(Strategy):
    @property
    def required_indicators(self):
        return ["ema20", "ema50", "ema200", "adx_14", "supertrend", "atr_14"]

    def generate_signal(self, candle, indicators):
        # Use ADX to confirm trend strength before entering
        if indicators.adx_14 and float(indicators.adx_14) < 25:
            return self._no_trade(candle, "ADX < 25 — ranging market, no trade")
        # Use Supertrend as direction filter
        if indicators.supertrend_direction != 1:
            return self._no_trade(candle, "Supertrend bearish")
        # ... EMA logic ...
```

---

## 10. Warmup Summary

| Indicator    | Output Fields                          | Warmup (bars) |
|--------------|----------------------------------------|---------------|
| EMA20        | `ema20`                                | 20            |
| EMA50        | `ema50`                                | 50            |
| EMA200       | `ema200`                               | 200           |
| RSI14        | `rsi14`                                | 14            |
| MACD(12,26,9)| `macd`, `macd_signal`                  | 34            |
| VWAP         | `vwap`                                 | 1 (resets daily)|
| ATR14        | `atr_14`                               | 14            |
| ADX14        | `adx_14`, `plus_di`, `minus_di`        | 28            |
| BB(20,2)     | `bb_middle`, `bb_upper`, `bb_lower`, `bb_width` | 20   |
| Supertrend   | `supertrend`, `supertrend_direction`   | 10            |
| OBV          | `obv`                                  | 1             |
| StochRSI(14) | `stoch_rsi_k`, `stoch_rsi_d`           | 28 / 30       |

The indicator engine loads 250 warmup candles before the watermark on incremental runs,
comfortably exceeding the maximum warmup requirement of 200 bars (EMA200).

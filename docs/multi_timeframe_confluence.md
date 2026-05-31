# Multi-Timeframe Confluence Framework (Phase 4C)

## Overview

The Phase 4C framework enables strategies to analyse multiple timeframes simultaneously and combine their signals into a single high-confidence trade decision. It is built on three pillars:

1. **Timeframe Alignment** — look-ahead-bias-free alignment of indicator data across timeframes
2. **Confluence Rules** — stateless, composable scoring rules (one per indicator)
3. **MTF Strategies** — three production-ready multi-timeframe strategies

---

## Architecture

```
BacktestEngine._build_strategy()
        │
        ├─ SingleTF strategy ──► StrategyBacktestAdapter (unchanged)
        │
        └─ MultiTimeframeStrategy
                │
                ▼
   MultiTimeframeBacktestAdapter
                │
                ├─ _load_mtf_indicators()  (loads all required TF data)
                │
                ├─ TimeframeAlignmentService.align()
                │
                └─ strategy.generate_multi_signal(aligned_records, ...)
                                │
                                ▼
                          StrategySignal → TradeAction
```

### Package layout

```
confluence/
    __init__.py                 exports core classes
    confluence_models.py        ConfluenceComponent, ConfluenceResult
    confluence_rules.py         8 stateless rule classes
    confluence_registry.py      CONFLUENCE_RULES dict, get_rule(), list_rules()
    confluence_engine.py        ConfluenceEngineService.evaluate()
    timeframe_alignment.py      TimeframeAlignmentService

strategies/
    multi_timeframe_base.py     MultiTimeframeStrategy ABC
    trend_confluence.py         EMA + ADX + VWAP
    supertrend_confluence.py    Supertrend + ADX + RSI
    momentum_confluence.py      MACD + RSI + OBV
    backtest_mtf_adapter.py     MultiTimeframeBacktestAdapter
```

---

## Timeframe Alignment

### The look-ahead bias problem

When processing a 5-minute entry bar that opens at 10:25, we must not use the 10:30 daily or 15-minute bar — it has not yet closed. Only bars whose close time is ≤ the entry bar's close time may be used.

### Alignment formula

```
close_time   = entry_time + entry_duration
anchor       = close_time - target_duration
aligned_time = floor(anchor, target_duration)
```

`floor(t, d)` rounds `t` down to the nearest `d`-minute boundary within the same calendar date.

### Examples

| Entry bar | Entry TF | Target TF | Calculation | Aligned time |
|-----------|----------|-----------|-------------|--------------|
| 10:25 | 5min | 15min | close=10:30, anchor=10:15, floor(10:15,15)=10:15 | **10:15** |
| 10:25 | 5min | 1day | close=10:30, anchor=prev day 10:30, floor(,1440)=prev day 00:00 | **prev day 00:00** |
| 10:04 | 1min | 5min | close=10:05, anchor=10:00, floor(10:00,5)=10:00 | **10:00** |
| 10:14 | 1min | 15min | close=10:15, anchor=10:00, floor(10:00,15)=10:00 | **10:00** |
| 10:15 | 15min | 1hour | close=10:30, anchor=09:30, floor(09:30,60)=09:00 | **09:00** |

The formula handles all intraday-to-intraday and intraday-to-daily pairs without special cases.

### Supported timeframes

| String | Duration |
|--------|----------|
| `1min` | 1 minute |
| `5min` | 5 minutes |
| `15min` | 15 minutes |
| `30min` | 30 minutes |
| `1hour` | 60 minutes |
| `4hour` | 240 minutes |
| `1day` | 1440 minutes |

---

## Confluence Rules

Each rule is a stateless class with an `evaluate()` method:

```python
rule.evaluate(
    indicators: IndicatorRecord,
    prev_indicators: Optional[IndicatorRecord] = None,
    current_price: Optional[Decimal] = None,
) -> RuleResult(score: int, reason: str, available: bool)
```

Positive scores are bullish; negative scores are bearish; zero is neutral or data-unavailable.

### Rule summary

| Rule | Name | Max score | Bullish condition | Bearish condition |
|------|------|-----------|-------------------|-------------------|
| `EmaAlignmentRule` | `ema_alignment` | ±20 | EMA20 > EMA50 > EMA200 | EMA20 < EMA50 < EMA200 |
| `AdxStrengthRule` | `adx_strength` | +15 | ADX > 25 | — (direction-agnostic) |
| `VWAPConfirmationRule` | `vwap_confirmation` | ±15 | price > VWAP | price < VWAP |
| `SupertrendRule` | `supertrend` | ±20 | direction = +1 | direction = -1 |
| `RsiMomentumRule` | `rsi_momentum` | ±15 | RSI > 60 (+15), 55-60 (+7) | RSI < 40 (-15), 40-45 (-7) |
| `MacdConfirmationRule` | `macd_confirmation` | ±15 | MACD > signal | MACD < signal |
| `ObvConfirmationRule` | `obv_confirmation` | ±15 | OBV rising | OBV falling |
| `BreakoutConfirmationRule` | `breakout_confirmation` | ±15 | price > BB upper | price < BB lower |

---

## Confluence Scoring

The `ConfluenceEngineService` aggregates rule scores into a 0–100 confidence value:

```
total_score = sum of all rule scores across all timeframes
confidence  = clamp(50 + total_score // 2, 0, 100)
```

| Confidence | Signal type |
|------------|-------------|
| ≥ 70 | `STRONG_BUY` |
| 55–69 | `BUY` |
| 46–54 | `NO_TRADE` |
| 31–45 | `SELL` |
| ≤ 30 | `STRONG_SELL` |

A score of 0 (all rules neutral) maps to confidence = 50 = `NO_TRADE`.  
A score of +40 maps to confidence = 70 = `STRONG_BUY`.  
A score of -40 maps to confidence = 30 = `STRONG_SELL`.

---

## Multi-Timeframe Strategies

### TrendConfluenceStrategy (`trend_confluence`)

Combines medium-term trend direction, momentum strength, and intraday price confirmation.

| Timeframe | Default | Indicator | Condition |
|-----------|---------|-----------|-----------|
| Trend | `1day` | EMA stack | EMA20 > EMA50 > EMA200 (bull) |
| Setup | `15min` | ADX | ADX > 25 |
| Entry | `5min` | VWAP | price > VWAP |

- **BUY** (confidence 75): all three conditions bullish
- **SELL** (confidence 25): EMA bear stack + ADX > 25 + price < VWAP
- **NO_TRADE**: any condition fails

**CLI example:**
```bash
python main.py --mode backtest --strategy trend_confluence \
    --instruments "NIFTY 50" --timeframes 5min \
    --trend-timeframe 1day --setup-timeframe 15min --entry-timeframe 5min
```

---

### SupertrendConfluenceStrategy (`supertrend_confluence`)

Uses the Supertrend indicator for trend direction, ADX for trend strength, and RSI for momentum confirmation.

| Timeframe | Default | Indicator | Condition |
|-----------|---------|-----------|-----------|
| Trend | `1day` | Supertrend direction | direction = +1 (bull) |
| Setup | `15min` | ADX | ADX > 25 |
| Entry | `5min` | RSI | RSI > 55 |

- **BUY** (confidence 75): all three bullish
- **SELL** (confidence 25): Supertrend = -1 + ADX > 25 + RSI < 45
- **NO_TRADE**: any condition fails

---

### MomentumConfluenceStrategy (`momentum_confluence`)

Designed for shorter intraday momentum trades using MACD, RSI, and OBV direction.

| Timeframe | Default | Indicator | Condition |
|-----------|---------|-----------|-----------|
| Trend | `15min` | MACD | MACD > signal |
| Setup | `5min` | RSI | RSI > 60 |
| Entry | `1min` | OBV | OBV rising (requires prev bar) |

| Conditions met | Signal | Confidence |
|----------------|--------|------------|
| MACD + RSI + OBV bullish | BUY | 75 |
| MACD + RSI bullish, OBV unavailable | BUY | 65 |
| MACD + RSI + OBV bearish | SELL | 25 |
| MACD + RSI bearish, OBV unavailable | SELL | 35 |
| Any single condition fails | NO_TRADE | 50 |

OBV direction requires two consecutive bars. During backtesting, `MultiTimeframeBacktestAdapter` supplies the previous aligned record automatically.

---

## Backtest Integration

### How MTF strategies are wired in

`BacktestEngine._build_strategy()` detects whether the selected strategy is a `MultiTimeframeStrategy` instance and automatically wraps it with `MultiTimeframeBacktestAdapter`:

```python
# Simplified
if isinstance(strat, MultiTimeframeStrategy):
    all_indicators = self._load_mtf_indicators(config, strat)
    return MultiTimeframeBacktestAdapter(strat, all_indicators)
```

`_load_mtf_indicators()` loads a separate `IndicatorRecord` list for each timeframe the strategy requires, with a 30-day pre-start buffer to allow indicator warm-up.

### TimeframeAlignmentService in the backtest loop

For each entry bar in the backtest, the adapter calls `TimeframeAlignmentService.align()` to produce aligned records from all timeframes. The entry row itself is then injected as the authoritative record for its own timeframe, overriding the alignment result (which may point to a slightly earlier bar due to sparse data).

### Timeframe override via CLI

The three `BacktestConfig` timeframe fields default to empty string (= use the strategy's built-in defaults). Passing non-empty values on the CLI overrides the strategy's timeframes for that run:

```bash
python main.py --mode backtest --strategy trend_confluence \
    --trend-timeframe 15min --setup-timeframe 5min --entry-timeframe 1min
```

---

## Scanner Preparation

The `ConfluenceEngineService` is designed to be reused by a future real-time scanner with zero modification:

1. Fetch aligned `IndicatorRecord` instances from the database (one per timeframe per instrument).
2. Call `engine.evaluate(...)` passing the aligned records and a `rule_config` dict.
3. Act on the returned `ConfluenceResult.signal_type` and `confidence`.

The scanner will share the same `TimeframeAlignmentService` and the same rule registry — no duplication required.

---

## Adding a New Rule

1. Subclass `_BaseRule` in `confluence/confluence_rules.py`:

```python
class MyNewRule(_BaseRule):
    name = "my_new_rule"
    max_score = 10

    def evaluate(self, indicators, prev_indicators=None, current_price=None) -> RuleResult:
        if indicators.some_field is None:
            return RuleResult(score=0, reason="my_new_rule: data unavailable", available=False)
        ...
```

2. Register it in `confluence/confluence_registry.py`:

```python
CONFLUENCE_RULES["my_new_rule"] = MyNewRule
```

The rule is immediately available to all strategy configurations and the `ConfluenceEngineService` without any further changes.

---

## Adding a New MTF Strategy

1. Subclass `MultiTimeframeStrategy` and implement the four abstract members:
   - `trend_timeframe`, `setup_timeframe`, `entry_timeframe` properties
   - `generate_multi_signal()` method

2. Register it in `strategies/registry.py`:

```python
STRATEGIES["my_strategy"] = MyStrategy()
```

3. Use it immediately:

```bash
python main.py --mode backtest --strategy my_strategy --timeframes 5min
```

# Meta Strategy Engine — Phase 6

## Overview

The Meta Strategy Engine is a strategy orchestration layer that sits above the existing strategy framework. Instead of selecting a strategy manually, the system detects the current market regime and dynamically routes execution to the best-fit strategy (or a weighted blend).

```
Indicator Data
     │
     ▼
┌────────────────┐
│ RegimeDetector │  ─── ADX, ATR, Supertrend, EMA alignment, BB width
└────────────────┘
     │  MarketRegime (type + confidence)
     ▼
┌────────────────┐
│StrategyScorer  │  ─── scoring matrix × confidence → StrategyScore[]
└────────────────┘
     │  sorted scores
     ▼
┌────────────────┐
│StrategyRouter  │  ─── SINGLE_BEST or WEIGHTED_BLEND → MetaSignal
└────────────────┘
     │  MetaSignal
     ▼
┌──────────────────────┐
│  BacktestEngine /    │  ─── executes selected strategy
│  Live Trading        │
└──────────────────────┘
     │  BacktestResult
     ▼
┌──────────────────────┐
│ PerformanceFeedback  │  ─── extracts StrategyPerformanceRecord
└──────────────────────┘
     │
     ▼
┌──────────────────────┐
│ AdaptiveLearningEngine│  ─── updates scoring matrix (blended update)
└──────────────────────┘
```

---

## Market Regimes

Five regimes are supported. Each is detected from a combination of indicator signals.

| Regime | Detection Criteria | Example Market |
|--------|-------------------|----------------|
| `TRENDING_UP` | ADX > 25, Supertrend bullish or EMA bullish alignment | Bull run |
| `TRENDING_DOWN` | ADX > 25, Supertrend bearish or EMA bearish alignment | Bear market |
| `RANGING` | ADX ≤ 25, ATR ratio 0.5–1.5× mean | Sideways consolidation |
| `HIGH_VOLATILITY` | ATR ratio > 1.5× mean, ADX ≤ 35 | News events, earnings |
| `LOW_VOLATILITY` | ATR ratio < 0.5× mean, ADX ≤ 25 | Summer doldrums |

### Detection Algorithm

1. **ATR ratio** (`atr / mean_atr`) determines volatility regime when extreme (> 1.5 or < 0.5)
2. **ADX** determines trend strength (> 25 = trending)
3. **Supertrend direction** + **EMA alignment** resolve TRENDING_UP vs TRENDING_DOWN
4. All other conditions → RANGING
5. A `confidence` score [0.35, 0.95] reflects signal strength

---

## Strategy Scoring Logic

Each strategy has a baseline score (0–100) per regime, reflecting expected fit:

| Strategy | TRENDING_UP | TRENDING_DOWN | RANGING | HIGH_VOL | LOW_VOL |
|----------|-------------|---------------|---------|----------|---------|
| `ema` | 95 | 80 | 15 | 50 | 40 |
| `trend_confluence` | 95 | 90 | 15 | 45 | 35 |
| `supertrend_confluence` | 90 | 85 | 20 | 50 | 30 |
| `momentum` | 90 | 70 | 10 | 60 | 30 |
| `momentum_confluence` | 85 | 75 | 25 | 65 | 35 |
| `vwap` | 75 | 70 | 60 | 55 | 45 |
| `mean_reversion` | 15 | 15 | 85 | 20 | 80 |

Adjusted score formula:
```
adjusted_score = base * confidence + base * (1 - confidence) * 0.5
```

This ensures lower-confidence regimes produce scores closer to 50% of baseline, reducing overconfidence.

---

## Routing Modes

### SINGLE_BEST (default)

Selects the highest-scoring strategy. `strategy_weights = {selected: 1.0}`.

### WEIGHTED_BLEND

Distributes weight among the top-N strategies with score ≥ threshold (default 30):

```
raw_weight[strategy] = score[strategy]
weight[strategy] = raw_weight[strategy] / sum(all raw_weights)
```

Weights are normalised to sum = 1.0. The `selected_strategy` field is set to the highest-weight strategy.

---

## Adaptive Weighting System

`StrategyWeightsManager` maintains a rolling window (default N=10) of performance records per `(strategy, regime)` pair.

Weight computation:
```
perf_score = rolling_mean(composite_score(records))
regime_fit = strategy_base_score / 100
weight = perf_score * regime_fit
```
Weights normalised to sum = 1.0.

`composite_score` formula (all values normalised to [0, 1]):
```
composite = sharpe_norm * 0.30
          + cagr_norm   * 0.25
          + dd_score    * 0.20
          + wr_norm     * 0.15
          + exp_norm    * 0.10
```
Records with < 5 trades are excluded to prevent noise.

---

## Learning Loop Explanation

The `AdaptiveLearningEngine` uses an exponential blending update:

```
new_score = old_score * (1 - α) + target_score * α
```

Where:
- `α` (learning rate) defaults to 0.10
- `target_score = composite_score(performance_record) * 100`

After each update cycle, the full learning state (scoring overrides, weight history, performance history, version) is persisted to the `learning_state_snapshots` database table as a JSON blob.

On startup with `--enable-adaptive-learning`, the latest snapshot is loaded and overrides are applied to the scoring matrix.

---

## Backtest Integration Flow

```
python main.py --mode meta-backtest \
               --instruments "NIFTY 50" \
               --timeframes 5min \
               --from-date 2023-01-01 \
               --to-date 2024-01-01 \
               --enable-adaptive-learning \
               --routing-mode single
```

1. Load indicator data for the date range
2. Detect current regime from the latest indicator row
3. Score all strategies for that regime
4. Route to best strategy (or weighted blend)
5. Execute standard `BacktestEngine.run()` with selected strategy
6. If `--enable-adaptive-learning`: feed result back into learning engine
7. Save reports to `reports/meta/`

---

## Database Tables

| Table | Purpose |
|-------|---------|
| `meta_strategy_runs` | Each meta-strategy signal: regime, selected strategy, weights, reasoning |
| `strategy_regime_performance` | Performance metrics per strategy per regime |
| `strategy_weight_history` | Historical weight snapshots for auditing |
| `learning_state_snapshots` | Full JSON state of AdaptiveLearningEngine |

---

## Example Output

```json
{
  "instrument": "NIFTY 50",
  "timeframe": "5min",
  "selected_strategy": "ema",
  "regime_type": "trending_up",
  "confidence": 0.82,
  "routing_mode": "single_best",
  "strategy_weights": {"ema": 1.0},
  "reasoning": "Selected 'ema' (score=77.9) as best fit for regime 'trending_up' (confidence=0.82)"
}
```

Weighted blend example:
```json
{
  "selected_strategy": "ema",
  "regime_type": "trending_up",
  "routing_mode": "weighted_blend",
  "strategy_weights": {
    "ema": 0.456,
    "trend_confluence": 0.339,
    "momentum": 0.205
  }
}
```

---

## Module Reference

| Module | Class | Responsibility |
|--------|-------|---------------|
| `meta/meta_models.py` | `RegimeType`, `MarketRegime`, `MetaSignal`, etc. | Data models |
| `meta/regime_detector.py` | `RegimeDetector` | Classify market regime from indicators |
| `meta/strategy_scoring.py` | `StrategyScorer` | Score strategies per regime |
| `meta/strategy_router.py` | `StrategyRouter` | Select strategy from scores |
| `meta/strategy_weights.py` | `StrategyWeightsManager` | Adaptive per-regime weights |
| `meta/performance_feedback.py` | `PerformanceFeedback` | Convert backtest results to performance records |
| `meta/adaptive_learning.py` | `AdaptiveLearningEngine` | Update scoring matrix from performance |
| `meta/meta_strategy_engine.py` | `MetaStrategyEngine` | Top-level orchestrator |

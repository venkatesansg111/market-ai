# Market AI — Quantitative Trading Platform

Production-grade pipeline for Indian equity indices (NIFTY 50, NIFTY BANK) covering three phases:
- **Phase 1** — Historical OHLCV ingestion (yfinance / NSE)
- **Phase 2** — Technical indicator engine + rule-based signal generation
- **Phase 3** — Event-driven backtesting framework with performance analytics

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Setup](#2-setup)
3. [Environment Variables](#3-environment-variables)
4. [Phase 1 — Data Ingestion](#4-phase-1--data-ingestion)
5. [Phase 2 — Indicators & Signals](#5-phase-2--indicators--signals)
6. [Phase 3 — Backtesting](#6-phase-3--backtesting)
7. [Full Pipeline Walkthrough](#7-full-pipeline-walkthrough)
8. [Running Tests](#8-running-tests)
9. [Database Access](#9-database-access)
10. [Project Structure](#10-project-structure)
11. [Timeframe Reference](#11-timeframe-reference)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10+ | 3.12+ recommended |
| Docker + Docker Compose | any | for PostgreSQL |
| pip | any | dependencies in requirements.txt |

---

## 2. Setup

```bash
# Clone and enter the project
cd market-ai

# Start PostgreSQL + PgAdmin
docker compose up -d

# Create and activate virtual environment (recommended)
python -m venv env
source env/bin/activate        # macOS/Linux
env\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt

# Copy environment config
cp .env.example .env
# Edit .env if your DB credentials differ from the docker-compose defaults
```

---

## 3. Environment Variables

The `.env.example` ships with defaults that match `docker-compose.yml` out of the box.

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=postgres

LOG_LEVEL=INFO
LOG_DIR=logs

INSTRUMENTS=NIFTY 50,NIFTY BANK
TIMEFRAMES=1min,5min,15min,1day
DATA_PROVIDER=yfinance
```

Tables are created automatically on first run — no manual migrations needed.

---

## 4. Phase 1 — Data Ingestion

Fetches OHLCV candles from Yahoo Finance (default) or NSE and stores them in the `market_candles` table.

### Basic usage

```bash
# Full 2-year backfill — NIFTY 50 + NIFTY BANK, all timeframes
python main.py

# or explicitly:
python main.py --mode ingest
```

### With options

```bash
# Last 3 months, daily candles only
python main.py --months 3 --timeframes 1day

# Specific instruments
python main.py --instruments "NIFTY 50" --timeframes 1day,5min

# Both indices, daily, last 45 months (covers EMA200 warmup for 2023 backtests)
python main.py --instruments "NIFTY 50,NIFTY BANK" --timeframes 1day --months 45

# Use NSE provider instead of yfinance (requires: pip install nsepython)
python main.py --provider nse --timeframes 1day
```

### All ingest flags

| Flag | Default | Description |
|---|---|---|
| `--mode` | `ingest` | Pipeline mode |
| `--instruments` | `NIFTY 50,NIFTY BANK` | Comma-separated instruments |
| `--timeframes` | `1min,5min,15min,1day` | Comma-separated timeframes |
| `--months` | `24` | How many months of history to fetch |
| `--provider` | `yfinance` | Data provider: `yfinance` or `nse` |

### Expected output

```
INFO  [Ingestion] Starting fetch: NIFTY 50 1day 2023-01-01 → 2025-05-31
INFO  [Ingestion] Inserted: 125, Duplicates: 0, Chunks failed: 0
INFO  [Ingestion] Starting fetch: NIFTY BANK 1day 2023-01-01 → 2025-05-31
INFO  [Ingestion] Inserted: 125, Duplicates: 0, Chunks failed: 0
```

### YFinance data availability limits

| Timeframe | Max history | Notes |
|---|---|---|
| `1min` | 7 days | Hard Yahoo Finance limit |
| `5min` | 60 days | Hard Yahoo Finance limit |
| `15min` | 60 days | Hard Yahoo Finance limit |
| `1day` | ~10 years | No real limit; code caps at 3650 days |

> **Important:** For backtesting a period in 2023–2024 using `1day`, you must ingest with `--months 45` or more (to cover EMA200 warmup of ~250 trading days before your backtest start).

---

## 5. Phase 2 — Indicators & Signals

### Run the indicator engine

Calculates EMA20, EMA50, EMA200, RSI14, VWAP, MACD+Signal from stored candles.
Stores results in `market_indicators`. Incremental — only processes new candles.

```bash
python main.py --mode indicators

# Specific instruments/timeframes
python main.py --mode indicators --instruments "NIFTY 50" --timeframes 1day
```

### Run the signal engine

Evaluates the latest indicator row per instrument/timeframe pair using 5 rules.
Stores results in `trade_signals`.

```bash
python main.py --mode signals

# Specific
python main.py --mode signals --instruments "NIFTY 50" --timeframes 1day
```

### Run both in sequence (pipeline)

```bash
python main.py --mode pipeline
python main.py --mode pipeline --instruments "NIFTY 50,NIFTY BANK" --timeframes 1day
```

### Run historical replay (mock tick simulation)

Replays stored candles through the realtime candle builder as synthetic ticks.

```bash
python main.py --mode replay --months 1

# Specific instruments
python main.py --mode replay --instruments "NIFTY 50" --months 1 --timeframes 1min,5min
```

### Signal classification rules

| Signal | Conditions |
|---|---|
| `STRONG_BUY` | EMA20>EMA50>EMA200 AND RSI>60 AND Price>VWAP AND MACD>Signal |
| `BUY` | EMA20>EMA50 AND RSI>55 AND Price>VWAP AND MACD not bearish |
| `STRONG_SELL` | EMA20<EMA50<EMA200 AND RSI<40 AND Price<VWAP AND MACD<Signal |
| `SELL` | EMA20<EMA50 AND RSI<45 AND Price<VWAP AND MACD not bullish |
| `NO_TRADE` | RSI in 45–55, or conflicting indicators |

### Confidence scoring

Confidence is a 0–100 scale: **0 = maximum bearish conviction, 50 = neutral, 100 = maximum bullish conviction.**

```
confidence = clamp(50 + sum_of_component_scores // 2, 0, 100)
```

| Component | Bullish | Neutral | Bearish |
|---|---|---|---|
| EMA alignment | +30 / +15 | 0 | -15 / -30 |
| RSI | +20 / +10 | 0 | -10 / -20 |
| VWAP | +20 | 0 | -20 |
| MACD | +30 / +15 | 0 | -15 / -30 |

---

## 6. Phase 3 — Backtesting

### Prerequisites

Before running a backtest you must have:
1. Candle data in `market_candles` for the instrument + timeframe (Phase 1)
2. Indicator data in `market_indicators` for the same range (Phase 2)

### Run a backtest

```bash
# NIFTY 50, daily, Oct 2023 – Jan 2024, ₹10 lakh capital
python main.py --mode backtest \
  --instruments "NIFTY 50" \
  --timeframes 1day \
  --from-date 2023-10-01 \
  --to-date 2024-01-01 \
  --capital 1000000

# NIFTY BANK, daily, full year 2024
python main.py --mode backtest \
  --instruments "NIFTY BANK" \
  --timeframes 1day \
  --from-date 2024-01-01 \
  --to-date 2024-12-31 \
  --capital 500000

# Custom run name
python main.py --mode backtest \
  --instruments "NIFTY 50" \
  --timeframes 1day \
  --from-date 2024-01-01 \
  --to-date 2024-06-30 \
  --capital 2000000 \
  --run-name "nifty50_h1_2024"
```

### All backtest flags

| Flag | Default | Description |
|---|---|---|
| `--from-date` | required | Backtest start date `YYYY-MM-DD` |
| `--to-date` | required | Backtest end date `YYYY-MM-DD` |
| `--capital` | `1000000` | Starting capital in ₹ |
| `--strategy` | `signal` | Strategy name (currently: `signal`) |
| `--run-name` | auto-generated | Name for this run in the DB |

> **Note:** Backtest requires exactly one instrument and one timeframe per run.

### Expected output

```
============================================================
  Backtest: nifty50_h1_2024
  NIFTY 50 | 1day | 2024-01-01 → 2024-06-30
  Capital: 2000000.00 | Strategy: signal
============================================================
INFO  [BacktestEngine] Loaded 123 rows for backtest
────────────────────────────────────────────────────────────
  BACKTEST COMPLETE: nifty50_h1_2024
  Total Return    : 8.42%
  CAGR            : 17.35%
  Max Drawdown    : 4.21%
  Sharpe Ratio    : 1.8432
  Win Rate        : 62.50%
  Total Trades    : 16
  Profit Factor   : 2.1045
────────────────────────────────────────────────────────────
```

### Reports

Reports are saved to `reports/` in three formats:

```
reports/
├── nifty50_h1_2024.json          # Full metrics + equity curve sample
├── nifty50_h1_2024_trades.csv    # Every trade with PnL breakdown
└── nifty50_h1_2024.md            # Markdown report with tables
```

### Strategy: `signal`

The `signal` strategy uses the Phase 2 `SignalEngineService` logic:
- `STRONG_BUY` signal → open a long position
- `STRONG_SELL` signal → close the open position (if any)

### Risk controls (defaults)

| Control | Default | Description |
|---|---|---|
| Max open positions | 1 | Only one trade at a time |
| Position size | 10% of capital | Per-trade capital allocation |
| Max drawdown | 15% | Trading halts if breached |
| Max daily loss | 2% | No new trades after daily limit hit |
| Commission | 0.03% (3 bps) | Per leg (entry + exit) |
| Slippage | 0.05% (5 bps) | Adverse fill simulation |

### Performance metrics computed

CAGR, Total Return %, Max Drawdown %, Sharpe Ratio (252-day, Rf=6.5%), Sortino Ratio,
Calmar Ratio, Recovery Factor, Profit Factor, Expectancy, Win Rate,
Avg Winner, Avg Loser, Avg Holding Minutes, Longest Win/Loss Streak,
Monthly Returns, Yearly Returns, full Equity Curve.

---

## 7. Full Pipeline Walkthrough

Complete end-to-end example for NIFTY 50 daily backtest over 2023.

```bash
# Step 1: Ingest enough history (45 months covers EMA200 warmup + 2023 backtest)
python main.py --instruments "NIFTY 50" --timeframes 1day --months 45

# Step 2: Compute indicators
python main.py --mode indicators --instruments "NIFTY 50" --timeframes 1day

# Step 3: Run the signal engine (optional — generates trade_signals table entries)
python main.py --mode signals --instruments "NIFTY 50" --timeframes 1day

# Step 4: Run backtest
python main.py --mode backtest \
  --instruments "NIFTY 50" \
  --timeframes 1day \
  --from-date 2023-01-01 \
  --to-date 2023-12-31 \
  --capital 1000000

# Reports appear in reports/
```

For NIFTY BANK 5-minute (recent data only — yfinance 60-day limit):

```bash
# Ingest last 60 days of 5min data
python main.py --instruments "NIFTY BANK" --timeframes 5min --months 2

# Indicators
python main.py --mode indicators --instruments "NIFTY BANK" --timeframes 5min

# Backtest over last 30 days
python main.py --mode backtest \
  --instruments "NIFTY BANK" \
  --timeframes 5min \
  --from-date $(date -d "30 days ago" +%Y-%m-%d) \
  --to-date $(date +%Y-%m-%d) \
  --capital 500000
```

---

## 8. Running Tests

### Quick run — all tests

```bash
pytest tests/ -v
```

### Unit tests only (no database required)

```bash
pytest tests/unit/ -v
```

Expected: **~102 tests, all pass** in under 2 seconds.

```
tests/unit/test_candle_builder.py          10 tests   PASSED
tests/unit/test_indicator_calculators.py   12 tests   PASSED
tests/unit/test_signal_engine.py           15 tests   PASSED
tests/unit/test_portfolio.py               18 tests   PASSED
tests/unit/test_risk_engine.py             12 tests   PASSED
tests/unit/test_performance.py             16 tests   PASSED
tests/unit/test_trade_executor.py          19 tests   PASSED
```

### Integration tests (requires Docker PostgreSQL)

```bash
# Make sure DB is running first
docker compose up -d

pytest tests/integration/ -v
```

Expected: **~22 tests, all pass.** Integration tests are self-contained — they seed synthetic data automatically and clean up after themselves.

```
tests/integration/test_indicator_pipeline.py    7 tests   PASSED
tests/integration/test_backtest_engine.py       15 tests  PASSED
```

### Run only integration tests

```bash
pytest -m integration -v
```

### Run everything except integration tests

```bash
pytest -m "not integration" -v
```

### Run a specific test file or test

```bash
pytest tests/unit/test_signal_engine.py -v
pytest tests/unit/test_signal_engine.py::TestStrongBuySignal -v
pytest tests/unit/test_portfolio.py::TestMarkToMarket::test_equity_equals_cash_plus_market_value -v
```

### Test coverage summary

| Module | Test file | What is tested |
|---|---|---|
| `realtime/candle_builder.py` | `test_candle_builder.py` | OHLCV accumulation, finalization, interval boundary, thread safety |
| `indicators/indicator_calculators.py` | `test_indicator_calculators.py` | EMA warmup, RSI bounds/overbought/oversold, VWAP session reset, MACD crossover |
| `signals/signal_engine.py` | `test_signal_engine.py` | All signal types, conflict detection, confidence scoring, reason strings |
| `backtesting/portfolio.py` | `test_portfolio.py` | Enter/exit position, mark-to-market, drawdown, equity formula, force-close |
| `backtesting/risk_engine.py` | `test_risk_engine.py` | All 4 risk checks, daily P&L accumulation, daily reset |
| `backtesting/performance.py` | `test_performance.py` | Return, win rate, streaks, max drawdown, monthly/yearly returns, ratios |
| `backtesting/trade_executor.py` | `test_trade_executor.py` | Slippage pricing, commission, qty sizing, PnL, holding time |
| `indicators/ + signals/ + DB` | `test_indicator_pipeline.py` | Full pipeline: candles → indicators → signals, idempotency, incremental insert |
| `backtesting/backtest_engine.py` + DB | `test_backtest_engine.py` | End-to-end run, DB persistence, metrics validity, reporter output |

---

## 9. Database Access

### PgAdmin (web UI)

Open [http://localhost:8080](http://localhost:8080) in your browser.

- **Email:** `admin@admin.com`
- **Password:** `admin123`
- **Server:** `market-postgres` / host `postgres` / port `5432`
- **DB:** `postgres` / user `postgres` / password `postgres`

### Tables

| Table | Phase | Description |
|---|---|---|
| `market_candles` | 1 | OHLCV data per instrument + timeframe + candle_time |
| `market_indicators` | 2 | EMA20/50/200, RSI14, VWAP, MACD+Signal per candle |
| `trade_signals` | 2 | Classified signals with confidence score and reason |
| `market_ticks` | 2 | Raw tick data (realtime path) |
| `market_realtime_status` | 2 | Pipeline health per instrument/timeframe |
| `backtest_runs` | 3 | Summary row per backtest run |
| `backtest_trades` | 3 | Every trade with full PnL breakdown |
| `portfolio_snapshots` | 3 | Equity curve at every bar |

### Useful queries

```sql
-- How much candle data do we have?
SELECT instrument, timeframe, COUNT(*) as rows,
       MIN(candle_time) as earliest, MAX(candle_time) as latest
FROM market_candles
GROUP BY instrument, timeframe
ORDER BY instrument, timeframe;

-- Latest signals
SELECT instrument, timeframe, signal_type, confidence, reason, signal_time
FROM trade_signals
ORDER BY signal_time DESC
LIMIT 20;

-- Backtest run history
SELECT run_name, instrument, timeframe,
       total_return_pct, max_drawdown_pct, win_rate_pct, sharpe_ratio
FROM backtest_runs
ORDER BY id DESC;

-- Trades for a specific run
SELECT bt.entry_time, bt.exit_time, bt.side, bt.entry_price, bt.exit_price,
       bt.quantity, bt.net_pnl
FROM backtest_trades bt
JOIN backtest_runs br ON bt.run_id = br.id
WHERE br.run_name = 'your_run_name'
ORDER BY bt.entry_time;
```

---

## 10. Project Structure

```
market-ai/
│
├── config/
│   ├── __init__.py              # exposes singleton `settings`
│   └── settings.py              # typed dataclasses; reads .env
│
├── database/
│   ├── connection.py            # SQLAlchemy engine, connection pool, session ctx manager
│   ├── models.py                # Phase 1+2 ORM models (MarketCandle, MarketIndicator, TradeSignal, ...)
│   └── models_backtesting.py    # Phase 3 ORM models (BacktestRun, BacktestTrade, PortfolioSnapshot)
│
├── data_providers/
│   ├── base.py                  # MarketDataProvider ABC, CandleData, Timeframe enum
│   ├── yfinance_provider.py     # YFinanceProvider (default, free, no auth required)
│   └── nse_provider.py          # NseProvider (EOD via nsepython)
│
├── ingestion/
│   ├── loader.py                # bulk_upsert() — batched INSERT ON CONFLICT DO NOTHING
│   └── fetch_historical.py      # month-by-month orchestrator with retry logic
│
├── indicators/
│   ├── indicator_models.py      # IndicatorRecord dataclass
│   ├── indicator_calculators.py # Pure functions: EMA, RSI, VWAP (session), MACD
│   └── indicator_engine.py      # IndicatorEngineService — incremental batch processing
│
├── signals/
│   ├── signal_models.py         # SignalType enum, SignalResult, ConfidenceComponents
│   └── signal_engine.py         # SignalEngineService — 5-rule evaluator + scorer
│
├── realtime/
│   ├── tick_models.py           # TickData, CandleDataRealtime dataclasses
│   ├── candle_builder.py        # Per-(instrument, timeframe) OHLCV accumulator
│   ├── candle_manager.py        # Thread-safe dispatcher to all CandleBuilders
│   └── candle_persistence.py    # Persists ticks + candles + status to DB
│
├── scheduler/
│   └── realtime_scheduler.py    # MockTickGenerator, HistoricalReplay, RealtimeCandleService
│
├── backtesting/
│   ├── backtest_models.py       # BacktestConfig, BacktestResult, Trade, OpenPosition, ...
│   ├── strategy_base.py         # Strategy ABC
│   ├── strategy_signal_adapter.py # Adapts SignalEngine output to TradeAction
│   ├── trade_executor.py        # Slippage + commission simulation
│   ├── portfolio.py             # Cash, position, equity, drawdown tracking
│   ├── risk_engine.py           # Max drawdown, daily loss, max open positions guards
│   ├── performance.py           # PerformanceEngine — full metrics computation
│   ├── backtest_engine.py       # Core orchestrator (load → iterate → persist → report)
│   └── reporting.py             # BacktestReporter: JSON, CSV, Markdown output
│
├── utils/
│   ├── logger.py                # Rotating file + console logger factory
│   └── time_utils.py            # month_chunks(), history_start_date()
│
├── tests/
│   ├── conftest.py              # Shared fixtures
│   ├── unit/                    # 102 pure unit tests — no DB, no network
│   └── integration/             # 22 integration tests — require Docker PostgreSQL
│       └── conftest.py          # Auto-seeds synthetic data for test session
│
├── docs/
│   ├── architecture.md          # Phase 2 Mermaid diagrams + component docs
│   └── backtesting_architecture.md  # Phase 3 Mermaid diagrams + metrics docs
│
├── main.py                      # CLI entry point (--mode flag)
├── requirements.txt
├── docker-compose.yml
├── .env.example
└── pytest.ini
```

---

## 11. Timeframe Reference

| Key | Description | YFinance limit | Use case |
|---|---|---|---|
| `1min` | 1-minute candles | Last 7 days | Intraday scalping |
| `5min` | 5-minute candles | Last 60 days | Intraday swing |
| `15min` | 15-minute candles | Last 60 days | Intraday trend |
| `1day` | Daily candles | ~10 years | Positional / swing |

---

## 12. Troubleshooting

### `ValueError: No data found for ... — Run Phase 1 ingestion first`

The backtest date range has no rows in `market_candles` + `market_indicators`. Fix:

```bash
# Re-ingest with enough months (45 = ~3.75 years, covers EMA200 warmup)
python main.py --instruments "NIFTY 50" --timeframes 1day --months 45
python main.py --mode indicators --instruments "NIFTY 50" --timeframes 1day
```

### `Inserted: 0, Duplicates: N` (all chunks skipped)

Data already in DB — this is correct idempotent behavior. If you expected new data, check:
- `--months` covers the range you need
- The timeframe is within YFinance's availability window (see table above)

### Integration tests fail with connection error

PostgreSQL is not running. Start it:
```bash
docker compose up -d
docker compose ps    # verify 'running' status
```

### `DeprecationWarning: datetime.datetime.utcnow()` on Python 3.12+

All internal usages have been updated to `datetime.now(tz=timezone.utc)`. If you see this in a third-party library, it is safe to ignore.

### 5-minute backtest returns no data for 2023/2024

YFinance only provides 5min data for the last 60 days. For historical intraday backtests beyond that window, use `1day` timeframe or a commercial data provider.

### PgAdmin shows no server

Register the server manually:
- Host: `localhost` (or `postgres` inside Docker network)
- Port: `5432`
- Database: `postgres`
- Username: `postgres`
- Password: `postgres`

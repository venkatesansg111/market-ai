# Market AI — Historical Data Ingestion System

Production-grade pipeline to fetch OHLCV data for Indian indices (NIFTY 50, NIFTY BANK)
and store it in a local PostgreSQL database.

## Quick Start

### 1. Prerequisites

- Docker + Docker Compose running
- Python 3.10+

### 2. Start the database

```bash
docker compose up -d
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp .env.example .env
# Edit .env if needed — defaults already match docker-compose.yml
```

### 5. Run ingestion

```bash
# Full 2-year backfill — NIFTY 50 + NIFTY BANK, all 4 timeframes
python main.py

# Quick test — last 3 months, daily candles only
python main.py --months 3 --timeframes 1day

# Specific instruments
python main.py --instruments "NIFTY 50,NIFTY BANK" --timeframes 1day,5min

# Use NSE provider (requires: pip install nsepython)
python main.py --provider nse --timeframes 1day
```

---

## Architecture

```
market-ai/
├── config/
│   ├── __init__.py          # exposes singleton `settings`
│   └── settings.py          # typed dataclasses, reads .env
│
├── database/
│   ├── connection.py        # SQLAlchemy engine + connection pool + session ctx
│   ├── models.py            # MarketCandle ORM model + create_tables()
│   └── schema.sql           # DDL reference (SQLAlchemy is source of truth)
│
├── data_providers/
│   ├── base.py              # MarketDataProvider ABC + CandleData + Timeframe
│   ├── yfinance_provider.py # YFinanceProvider  (default, free, no auth)
│   └── nse_provider.py      # NseProvider       (EOD via nsepython, falls back to yfinance)
│
├── ingestion/
│   ├── loader.py            # bulk_upsert() — batched INSERT ON CONFLICT DO NOTHING
│   └── fetch_historical.py  # orchestrates month-by-month fetch + store + retry
│
├── utils/
│   ├── logger.py            # rotating file + console logger
│   └── time_utils.py        # month_chunks(), history_start_date()
│
├── main.py                  # CLI entry point
├── requirements.txt
├── .env.example
└── docker-compose.yml
```

## Timeframes

| Key    | Description |
|--------|-------------|
| `1min` | 1-minute candles (yfinance: last 7 days only) |
| `5min` | 5-minute candles (yfinance: last 60 days) |
| `15min`| 15-minute candles (yfinance: last 60 days) |
| `1day` | Daily candles (yfinance: up to 2 years) |

## Adding a new data provider

1. Create `data_providers/my_provider.py`
2. Inherit from `MarketDataProvider` and implement `get_historical_data()` + `provider_name()`
3. Register it in `main.py::_build_provider()`
4. No other files need to change.

## Future modules (planned)

- `indicators/` — RSI, EMA, MACD computed from stored candles
- `strategy/` — signal generation layer
- `option_chain/` — NSE F&O option chain ingestion
- `realtime/` — Zerodha Kite WebSocket live feed
- `api/` — FastAPI recommendation service

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass
class DatabaseConfig:
    host: str = field(default_factory=lambda: os.getenv("DB_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("DB_PORT", "5432")))
    name: str = field(default_factory=lambda: os.getenv("DB_NAME", "market_ai"))
    user: str = field(default_factory=lambda: os.getenv("DB_USER", "postgres"))
    password: str = field(default_factory=lambda: os.getenv("DB_PASSWORD", "postgres"))
    pool_min: int = field(default_factory=lambda: int(os.getenv("DB_POOL_MIN", "2")))
    pool_max: int = field(default_factory=lambda: int(os.getenv("DB_POOL_MAX", "10")))

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )


@dataclass
class IngestionConfig:
    # How many months to look back for historical data
    history_months: int = field(
        default_factory=lambda: int(os.getenv("HISTORY_MONTHS", "24"))
    )
    # Seconds to wait between provider calls
    request_delay_seconds: float = field(
        default_factory=lambda: float(os.getenv("REQUEST_DELAY_SECONDS", "1.0"))
    )
    max_retries: int = field(
        default_factory=lambda: int(os.getenv("MAX_RETRIES", "3"))
    )
    retry_backoff_seconds: float = field(
        default_factory=lambda: float(os.getenv("RETRY_BACKOFF_SECONDS", "5.0"))
    )
    # Rows to insert per batch
    batch_size: int = field(
        default_factory=lambda: int(os.getenv("BATCH_SIZE", "500"))
    )


@dataclass
class Settings:
    db: DatabaseConfig = field(default_factory=DatabaseConfig)
    ingestion: IngestionConfig = field(default_factory=IngestionConfig)
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    log_dir: Path = field(
        default_factory=lambda: Path(os.getenv("LOG_DIR", "logs"))
    )

    # Instruments to ingest — overrideable via env as comma-separated list
    instruments: list[str] = field(
        default_factory=lambda: os.getenv(
            "INSTRUMENTS", "NIFTY 50,NIFTY BANK"
        ).split(",")
    )

    # Timeframes to ingest
    timeframes: list[str] = field(
        default_factory=lambda: os.getenv(
            "TIMEFRAMES", "1min,5min,15min,1day"
        ).split(",")
    )

    # Which provider to use: "nse" | "yfinance"
    data_provider: str = field(
        default_factory=lambda: os.getenv("DATA_PROVIDER", "yfinance")
    )

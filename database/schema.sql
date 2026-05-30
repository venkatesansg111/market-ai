-- =============================================================
-- market_ai  —  canonical DDL
-- SQLAlchemy models.py is the source of truth; this file is
-- provided for manual inspection / direct DB administration.
-- =============================================================

CREATE TABLE IF NOT EXISTS market_candles (
    id           BIGSERIAL PRIMARY KEY,
    instrument   VARCHAR(50)  NOT NULL,
    candle_time  TIMESTAMP    NOT NULL,
    open         FLOAT        NOT NULL,
    high         FLOAT        NOT NULL,
    low          FLOAT        NOT NULL,
    close        FLOAT        NOT NULL,
    volume       BIGINT,
    timeframe    VARCHAR(10)  NOT NULL,

    CONSTRAINT uq_market_candles_instrument_time_tf
        UNIQUE (instrument, candle_time, timeframe)
);

CREATE INDEX IF NOT EXISTS ix_market_candles_instr_tf_time
    ON market_candles (instrument, timeframe, candle_time);

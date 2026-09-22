-- RAW layer: data exactly as StatCan returned it, plus load bookkeeping.
-- raw.observation is append-only. Every run lands a new batch, so the full
-- history of what StatCan published (including values later revised) is kept.

CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.load_batch (
    batch_id        INTEGER PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL,
    finished_at     TIMESTAMPTZ,
    mode            VARCHAR NOT NULL,   -- 'full' or 'incremental'
    latest_n        INTEGER NOT NULL,   -- months requested per series
    rows_landed     INTEGER,
    facts_inserted  INTEGER,
    facts_revised   INTEGER,
    status          VARCHAR NOT NULL    -- 'running', 'succeeded', 'failed'
);

-- Series catalogue from config/series.yaml, refreshed on every run.
CREATE TABLE IF NOT EXISTS raw.series (
    vector_id   BIGINT PRIMARY KEY,
    table_id    VARCHAR NOT NULL,
    geography   VARCHAR NOT NULL,
    indicator   VARCHAR NOT NULL,
    industry    VARCHAR NOT NULL,
    naics_code  VARCHAR,
    sector      VARCHAR,
    unit        VARCHAR NOT NULL,
    is_rate     BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS raw.observation (
    batch_id            INTEGER NOT NULL,
    vector_id           BIGINT NOT NULL,
    ref_period          DATE NOT NULL,
    value               DOUBLE,          -- NULL when StatCan suppresses a point
    decimals            INTEGER,
    scalar_factor_code  INTEGER,
    symbol_code         INTEGER,
    status_code         INTEGER,
    release_time        TIMESTAMP,
    PRIMARY KEY (batch_id, vector_id, ref_period)
);

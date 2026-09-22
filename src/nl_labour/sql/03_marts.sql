-- MARTS layer: star schema.
-- Grain of the fact: one row per series per month, which is equivalent to one
-- row per (month, geography, indicator, industry). Both keys are enforced.

CREATE SCHEMA IF NOT EXISTS marts;

CREATE SEQUENCE IF NOT EXISTS marts.seq_geography;
CREATE SEQUENCE IF NOT EXISTS marts.seq_indicator;
CREATE SEQUENCE IF NOT EXISTS marts.seq_industry;

CREATE TABLE IF NOT EXISTS marts.dim_date (
    date_key     INTEGER PRIMARY KEY,   -- yyyymm
    month_start  DATE NOT NULL UNIQUE,
    year         INTEGER NOT NULL,
    quarter      INTEGER NOT NULL,
    month        INTEGER NOT NULL,
    month_name   VARCHAR NOT NULL,
    year_month   VARCHAR NOT NULL       -- 'YYYY-MM'
);

CREATE TABLE IF NOT EXISTS marts.dim_geography (
    geography_key   INTEGER PRIMARY KEY DEFAULT nextval('marts.seq_geography'),
    geography_name  VARCHAR NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS marts.dim_indicator (
    indicator_key   INTEGER PRIMARY KEY DEFAULT nextval('marts.seq_indicator'),
    indicator_name  VARCHAR NOT NULL UNIQUE,
    unit            VARCHAR NOT NULL,
    is_rate         BOOLEAN NOT NULL    -- rates are averaged, counts are summed
);

CREATE TABLE IF NOT EXISTS marts.dim_industry (
    industry_key    INTEGER PRIMARY KEY DEFAULT nextval('marts.seq_industry'),
    industry_name   VARCHAR NOT NULL UNIQUE,
    naics_code      VARCHAR,
    sector          VARCHAR             -- 'Goods', 'Services', or NULL for the total
);

CREATE TABLE IF NOT EXISTS marts.fact_labour_market (
    vector_id           BIGINT  NOT NULL,
    date_key            INTEGER NOT NULL REFERENCES marts.dim_date (date_key),
    geography_key       INTEGER NOT NULL REFERENCES marts.dim_geography (geography_key),
    indicator_key       INTEGER NOT NULL REFERENCES marts.dim_indicator (indicator_key),
    industry_key        INTEGER NOT NULL REFERENCES marts.dim_industry (industry_key),
    value               DOUBLE,
    status_code         INTEGER,
    symbol_code         INTEGER,
    release_time        TIMESTAMP,
    row_hash            VARCHAR NOT NULL,
    first_loaded_batch  INTEGER NOT NULL,
    last_changed_batch  INTEGER NOT NULL,
    PRIMARY KEY (vector_id, date_key),
    UNIQUE (date_key, geography_key, indicator_key, industry_key)
);

-- Every value StatCan changed after we first loaded it.
CREATE TABLE IF NOT EXISTS marts.fact_revision (
    vector_id         BIGINT  NOT NULL,
    date_key          INTEGER NOT NULL,
    batch_id          INTEGER NOT NULL,
    old_value         DOUBLE,
    new_value         DOUBLE,
    old_release_time  TIMESTAMP,
    new_release_time  TIMESTAMP,
    PRIMARY KEY (vector_id, date_key, batch_id)
);

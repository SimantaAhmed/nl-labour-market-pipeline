-- Incremental load from staging into the star schema.
-- Expects the variable batch_id to be set (SET VARIABLE batch_id = n).
-- Safe to re-run: unchanged rows are skipped by comparing row_hash.

-- 1. Dimensions: add members that are new; refresh descriptive attributes.
INSERT INTO marts.dim_geography (geography_name)
SELECT DISTINCT geography FROM raw.series
WHERE geography NOT IN (SELECT geography_name FROM marts.dim_geography);

INSERT INTO marts.dim_indicator (indicator_name, unit, is_rate)
SELECT DISTINCT indicator, unit, is_rate FROM raw.series
WHERE indicator NOT IN (SELECT indicator_name FROM marts.dim_indicator);

INSERT INTO marts.dim_industry (industry_name, naics_code, sector)
SELECT DISTINCT industry, naics_code, sector FROM raw.series
WHERE industry NOT IN (SELECT industry_name FROM marts.dim_industry);

INSERT INTO marts.dim_date
SELECT
    CAST(strftime(m, '%Y%m') AS INTEGER),
    m,
    year(m),
    quarter(m),
    month(m),
    monthname(m),
    strftime(m, '%Y-%m')
FROM (
    SELECT CAST(unnest(generate_series(min(ref_period), max(ref_period), INTERVAL 1 MONTH)) AS DATE) AS m
    FROM staging.observation
)
WHERE m NOT IN (SELECT month_start FROM marts.dim_date);

-- 2. Resolve staging rows to surrogate keys.
CREATE OR REPLACE TEMP VIEW conformed AS
SELECT
    o.vector_id,
    d.date_key,
    g.geography_key,
    i.indicator_key,
    n.industry_key,
    o.value,
    o.status_code,
    o.symbol_code,
    o.release_time,
    o.row_hash
FROM staging.observation o
JOIN raw.series s            ON s.vector_id = o.vector_id
JOIN marts.dim_date d        ON d.month_start = o.ref_period
JOIN marts.dim_geography g   ON g.geography_name = s.geography
JOIN marts.dim_indicator i   ON i.indicator_name = s.indicator
JOIN marts.dim_industry n    ON n.industry_name = s.industry;

-- 3. Log revisions before they are applied, so the old value is kept.
INSERT INTO marts.fact_revision
SELECT f.vector_id, f.date_key, getvariable('batch_id'),
       f.value, c.value, f.release_time, c.release_time
FROM marts.fact_labour_market f
JOIN conformed c USING (vector_id, date_key)
WHERE f.row_hash <> c.row_hash;

-- 4. Apply: insert new months, update revised ones, leave the rest alone.
MERGE INTO marts.fact_labour_market f
USING conformed c
ON f.vector_id = c.vector_id AND f.date_key = c.date_key
WHEN MATCHED AND f.row_hash <> c.row_hash THEN UPDATE SET
    value              = c.value,
    status_code        = c.status_code,
    symbol_code        = c.symbol_code,
    release_time       = c.release_time,
    row_hash           = c.row_hash,
    last_changed_batch = getvariable('batch_id')
WHEN NOT MATCHED THEN INSERT (
    vector_id, date_key, geography_key, indicator_key, industry_key,
    value, status_code, symbol_code, release_time, row_hash,
    first_loaded_batch, last_changed_batch
) VALUES (
    c.vector_id, c.date_key, c.geography_key, c.indicator_key, c.industry_key,
    c.value, c.status_code, c.symbol_code, c.release_time, c.row_hash,
    getvariable('batch_id'), getvariable('batch_id')
);

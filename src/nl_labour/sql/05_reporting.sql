-- REPORTING layer: views the dashboard reads.

CREATE SCHEMA IF NOT EXISTS reporting;

-- Every loaded value in long format, with dimension labels attached.
CREATE OR REPLACE VIEW reporting.monthly_series AS
SELECT
    d.month_start,
    d.year_month,
    g.geography_name  AS geography,
    i.indicator_name  AS indicator,
    n.industry_name   AS industry,
    n.sector,
    i.unit,
    i.is_rate,
    f.value
FROM marts.fact_labour_market f
JOIN marts.dim_date d       USING (date_key)
JOIN marts.dim_geography g  USING (geography_key)
JOIN marts.dim_indicator i  USING (indicator_key)
JOIN marts.dim_industry n   USING (industry_key);

-- Headline rates, NL beside Canada, with the gap in percentage points.
CREATE OR REPLACE VIEW reporting.nl_vs_canada AS
SELECT
    month_start,
    indicator,
    max(value) FILTER (WHERE geography = 'Newfoundland and Labrador') AS nl,
    max(value) FILTER (WHERE geography = 'Canada')                    AS canada,
    nl - canada                                                        AS gap_pts
FROM reporting.monthly_series
WHERE is_rate AND industry = 'Total, all industries'
GROUP BY ALL;

-- Unemployment rate with a 12-month average and year-over-year change.
-- The row offsets assume one row per month; checks/monthly_gaps.sql enforces that.
CREATE OR REPLACE VIEW reporting.unemployment_trend AS
SELECT
    month_start,
    geography,
    value                                                    AS unemployment_rate,
    avg(value) OVER w12                                      AS rate_12m_avg,
    value - lag(value, 12) OVER (PARTITION BY geography ORDER BY month_start)
                                                             AS yoy_change_pts
FROM reporting.monthly_series
WHERE indicator = 'Unemployment rate'
WINDOW w12 AS (PARTITION BY geography ORDER BY month_start
               ROWS BETWEEN 11 PRECEDING AND CURRENT ROW);

-- NL employment by industry. Monthly provincial industry estimates carry wide
-- sampling error, so industries are compared on 12-month averages: the year
-- ending in the latest month against the same window 1 and 10 years earlier.
CREATE OR REPLACE VIEW reporting.nl_industry_employment AS
WITH ind AS (
    SELECT industry, sector, month_start, value
    FROM reporting.monthly_series
    WHERE geography = 'Newfoundland and Labrador'
      AND indicator = 'Employment'
      AND industry <> 'Total, all industries'
),
latest AS (SELECT max(month_start) AS m FROM ind),
windows AS (
    SELECT
        ind.industry,
        ind.sector,
        avg(value) FILTER (WHERE month_start >  m - INTERVAL 12 MONTH)                                       AS avg_now,
        avg(value) FILTER (WHERE month_start <= m - INTERVAL 12 MONTH  AND month_start > m - INTERVAL 24 MONTH)  AS avg_1y_ago,
        avg(value) FILTER (WHERE month_start <= m - INTERVAL 120 MONTH AND month_start > m - INTERVAL 132 MONTH) AS avg_10y_ago
    FROM ind, latest
    GROUP BY ALL
)
SELECT
    (SELECT m FROM latest)                              AS window_end,
    industry,
    sector,
    round(avg_now, 1)                                   AS employment_k,
    round(100 * avg_now / sum(avg_now) OVER (), 1)      AS share_pct,
    round(avg_now - avg_1y_ago, 1)                      AS change_1y_k,
    round(avg_now - avg_10y_ago, 1)                     AS change_10y_k,
    round(100 * (avg_now / avg_10y_ago - 1), 1)         AS change_10y_pct
FROM windows
ORDER BY employment_k DESC;

-- Revisions StatCan made to values after this pipeline first loaded them.
CREATE OR REPLACE VIEW reporting.revisions AS
SELECT
    r.batch_id,
    b.finished_at        AS detected_at,
    s.geography,
    s.indicator,
    s.industry,
    d.month_start,
    r.old_value,
    r.new_value,
    r.new_value - r.old_value AS change
FROM marts.fact_revision r
JOIN raw.series s      USING (vector_id)
JOIN marts.dim_date d  USING (date_key)
LEFT JOIN raw.load_batch b USING (batch_id);

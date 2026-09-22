-- severity: error
-- No series skips a month between its first and last loaded month.
-- The reporting views use row offsets (lag 12, 12-row windows) that rely on this.
WITH span AS (
    SELECT vector_id, min(date_key) AS first_key, max(date_key) AS last_key
    FROM marts.fact_labour_market GROUP BY vector_id
)
SELECT s.vector_id, d.month_start AS missing_month
FROM span s
JOIN marts.dim_date d ON d.date_key BETWEEN s.first_key AND s.last_key
LEFT JOIN marts.fact_labour_market f
       ON f.vector_id = s.vector_id AND f.date_key = d.date_key
WHERE f.vector_id IS NULL;

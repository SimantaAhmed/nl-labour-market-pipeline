-- severity: error
-- Every series in the catalogue has data in the fact table.
SELECT s.vector_id, s.geography, s.indicator, s.industry
FROM raw.series s
WHERE NOT EXISTS (
    SELECT 1 FROM marts.fact_labour_market f WHERE f.vector_id = s.vector_id);

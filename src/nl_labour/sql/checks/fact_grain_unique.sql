-- severity: error
-- Fact grain: at most one row per (month, geography, indicator, industry).
SELECT date_key, geography_key, indicator_key, industry_key, count(*) AS n
FROM marts.fact_labour_market
GROUP BY ALL
HAVING count(*) > 1;

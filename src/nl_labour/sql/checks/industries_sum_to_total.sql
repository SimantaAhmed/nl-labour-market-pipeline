-- severity: error
-- NL employment summed across the 16 industries matches total NL employment
-- from the labour force table (two different StatCan tables) within 0.5%.
-- (the largest gap in the data to date is 0.22%, from rounding).
WITH w AS (
    SELECT
        month_start,
        sum(value) FILTER (WHERE industry <> 'Total, all industries') AS industry_sum,
        max(value) FILTER (WHERE industry =  'Total, all industries') AS total
    FROM reporting.monthly_series
    WHERE geography = 'Newfoundland and Labrador' AND indicator = 'Employment'
    GROUP BY month_start
)
SELECT *, round(100 * (industry_sum / total - 1), 2) AS diff_pct
FROM w
WHERE total IS NOT NULL AND industry_sum IS NOT NULL
  AND abs(industry_sum / total - 1) > 0.005;

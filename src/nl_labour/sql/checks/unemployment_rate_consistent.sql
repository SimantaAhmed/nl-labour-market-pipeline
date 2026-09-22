-- severity: error
-- The published unemployment rate matches unemployment / labour force.
-- StatCan rounds counts to 0.1 thousand and rates to 0.1, so allow 0.1 points
-- (the worst case in the data to date is 0.05).
WITH w AS (
    SELECT
        geography,
        month_start,
        max(value) FILTER (WHERE indicator = 'Unemployment rate') AS rate,
        max(value) FILTER (WHERE indicator = 'Unemployment')      AS unemployed,
        max(value) FILTER (WHERE indicator = 'Labour force')      AS labour_force
    FROM reporting.monthly_series
    WHERE industry = 'Total, all industries'
    GROUP BY ALL
)
SELECT *, round(100 * unemployed / labour_force, 2) AS derived_rate
FROM w
WHERE abs(rate - 100 * unemployed / labour_force) > 0.1;

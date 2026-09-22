-- severity: warn
-- The Labour Force Survey is released monthly, about five weeks after the
-- reference month. Warn if the newest month is older than that suggests.
SELECT max(month_start) AS latest_month
FROM reporting.monthly_series
HAVING max(month_start) < current_date - INTERVAL 75 DAY;

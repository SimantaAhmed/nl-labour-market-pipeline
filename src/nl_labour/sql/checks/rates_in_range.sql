-- severity: error
-- Rates are percentages, so they must fall between 0 and 100.
SELECT geography, indicator, month_start, value
FROM reporting.monthly_series
WHERE is_rate AND (value < 0 OR value > 100);

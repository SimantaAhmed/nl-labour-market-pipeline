# Data model

The warehouse is one DuckDB file with four schemas. SQL lives in
[`src/nl_labour/sql`](../src/nl_labour/sql) and runs in file order.

| Schema | Built by | Holds |
|---|---|---|
| `raw` | `01_raw.sql` | Data as StatCan returned it, plus load bookkeeping |
| `staging` | `02_staging.sql` | Views: latest version of each value, hashed |
| `marts` | `03_marts.sql`, loaded by `04_load.sql` | Star schema and revision log |
| `reporting` | `05_reporting.sql` | Views the dashboard reads |

## raw

**`raw.observation`**: append-only. One row per batch, series and month.
Primary key `(batch_id, vector_id, ref_period)`. Because nothing is ever
overwritten, every version StatCan has published since tracking began is kept.

| Column | Notes |
|---|---|
| `batch_id` | The load that landed the row |
| `vector_id` | StatCan series ID |
| `ref_period` | Reference month (first of month) |
| `value` | NULL when StatCan suppresses the point |
| `decimals`, `scalar_factor_code`, `symbol_code`, `status_code` | As returned by the API |
| `release_time` | When StatCan published this version |

**`raw.series`**: the series catalogue from `config/series.yaml`, refreshed on
every run: vector ID, source table, geography, indicator, industry, NAICS code,
sector, unit, and whether the indicator is a rate.

**`raw.load_batch`**: one row per run: mode (`full` or `incremental`), months
requested, rows landed, facts inserted and revised, and status (`running`,
`succeeded`, `failed`).

## staging

**`staging.observation`**: the most recent landed version of each
`(vector_id, ref_period)`, with `row_hash = md5(value | status_code |
symbol_code)`. NULLs are spelled out before hashing, so a value becoming
suppressed counts as a change.

## marts

```
                 dim_date (month grain)
                        |
dim_geography --- fact_labour_market --- dim_indicator
                        |
                   dim_industry

fact_revision: old and new value for every change to a fact
```

**`fact_labour_market`**

Grain: one row per series per month. Since each series is one combination of
geography, indicator and industry, this equals one row per
`(month, geography, indicator, industry)`. Both are enforced: primary key
`(vector_id, date_key)` and a unique constraint on the four dimension keys.

| Column | Notes |
|---|---|
| `vector_id` | Lineage back to the StatCan series |
| `date_key` | `yyyymm`, references `dim_date` |
| `geography_key`, `indicator_key`, `industry_key` | Reference their dimensions |
| `value` | Counts in thousands of persons; rates in percent |
| `status_code`, `symbol_code`, `release_time` | From the source |
| `row_hash` | Compared on each load to detect revisions |
| `first_loaded_batch`, `last_changed_batch` | Load audit |

Labour force characteristics (table 14-10-0287) use the industry member
"Total, all industries". NL employment by industry (table 14-10-0355) uses the
indicator "Employment" with one of 16 industries. Rates are averaged, never
summed; `dim_indicator.is_rate` marks them.

**Dimensions**

| Table | Key | Attributes |
|---|---|---|
| `dim_date` | `date_key` (yyyymm) | month start, year, quarter, month, month name, `YYYY-MM` |
| `dim_geography` | surrogate | name |
| `dim_indicator` | surrogate | name, unit, `is_rate` |
| `dim_industry` | surrogate | name, NAICS code, sector (Goods, Services, or none for the total) |

**`fact_revision`**: `(vector_id, date_key, batch_id)` with old and new value
and old and new release time. Written before the fact is updated.

## Load steps (`04_load.sql`)

1. Insert new geography, indicator, industry and month members.
2. Resolve staging rows to surrogate keys.
3. Write a `fact_revision` row for every fact whose hash differs from staging.
4. `MERGE` into the fact: insert new months, update changed ones, skip the rest.

Steps run inside one transaction together with landing the batch, so a failed
run leaves no partial data. The batch is then marked `failed` in
`raw.load_batch`.

## Data-quality checks

Each file in `sql/checks` returns the rows that violate it. Error-level
failures fail the run; warnings are reported only.

| Check | Severity | Rule |
|---|---|---|
| `fact_grain_unique` | error | One row per month, geography, indicator and industry |
| `series_fully_loaded` | error | Every configured series has data |
| `monthly_gaps` | error | No series skips a month (the reporting views depend on this) |
| `rates_in_range` | error | Rates between 0 and 100 |
| `unemployment_rate_consistent` | error | Published rate within 0.1 points of unemployment / labour force |
| `industries_sum_to_total` | error | 16 NL industries within 0.5% of total NL employment |
| `data_is_current` | warn | Newest month no older than 75 days |

# Newfoundland and Labrador labour market pipeline

[![CI](https://github.com/SimantaAhmed/nl-labour-market-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/SimantaAhmed/nl-labour-market-pipeline/actions/workflows/ci.yml)
[![Pipeline](https://github.com/SimantaAhmed/nl-labour-market-pipeline/actions/workflows/pipeline.yml/badge.svg)](https://github.com/SimantaAhmed/nl-labour-market-pipeline/actions/workflows/pipeline.yml)

A scheduled data pipeline that pulls Labour Force Survey data for Newfoundland
and Labrador (NL) and Canada from the Statistics Canada API, loads it
incrementally into a star schema in DuckDB, keeps a log of every value StatCan
revises, runs data-quality checks, and publishes a dashboard.

**Dashboard:** https://simantaahmed.github.io/nl-labour-market-pipeline/

**Data downloads (CSV):** published with the dashboard and regenerated on every run.
See the "Download the data" section of the dashboard for the files and columns.

## What the data shows

Figures are from the August 2026 release (data through August 2026). Rates are
12-month averages unless stated.

- **NL's unemployment rate is at a record low, but that is not the same as
  more people working.** It fell from 13.5% in 2016 to 9.6% over the last 12
  months, and hit 8.2% in June 2026, the lowest since the series began in 1976.
  Over the same period the employment rate barely moved (52.5% to 51.7%)
  while the participation rate fell from 60.7% to 57.3%. Most of the drop in
  unemployment reflects fewer people in the labour force, not a larger share of
  the population in work.
- **The gap with Canada has narrowed from the unemployment side only.** The
  unemployment gap is 2.9 points, down from 6.5 in 2016 and an average of
  8.9 in the 1990s. The employment rate gap is still 9.0 points, about where
  it was in 2016 (8.7).
- **Employment growth over ten years is concentrated in public-facing
  services.** Comparing the 12 months to August 2026 with the same months ten
  years earlier: health care and social assistance +10,200 (+27%), public
  administration +6,700 (+45%), educational services +3,400. Construction
  (-5,000, -22%), wholesale and retail trade (-4,000) and manufacturing
  (-3,100, -27%) shrank.

These come straight from the reporting views (`reporting.nl_vs_canada`,
`reporting.nl_industry_employment`). Provincial LFS estimates carry sampling
error, which is why the comparisons use 12-month averages rather than single
months.

## How it works

```
Statistics Canada Web Data Service (REST, JSON)
   |   verify-series: every vector ID is checked against its expected title
   v
raw.observation        append-only; every batch kept, so every published
   |                   version of every value is preserved
   v
staging.observation    latest version of each (series, month) + a row hash
   |
   v   04_load.sql: add new dimension members, log revisions, then MERGE
marts                  star schema: fact_labour_market + dim_date,
   |                   dim_geography, dim_indicator, dim_industry;
   |                   fact_revision holds old and new values
   v
reporting              views: NL vs Canada, unemployment trend,
   |                   industry employment, revisions
   v
checks/*.sql           7 data-quality checks; any error-level failure
   |                   fails the run before anything is published
   v
dashboard              static HTML, deployed to GitHub Pages
```

A GitHub Actions workflow runs this every Saturday (the LFS is released on a
Friday). The DuckDB file is kept between runs on the `data` branch.

See [docs/data-model.md](docs/data-model.md) for the tables and grain.

## Design decisions

- **Incremental loads with revision tracking.** Each run re-reads the last 36
  months, which covers StatCan's yearly revision of seasonally adjusted
  estimates. Rows whose hash has not changed are skipped; changed rows are
  updated in the fact table and the old value is written to
  `marts.fact_revision` first. A rerun with no new data writes nothing to the
  marts.
- **Series IDs are verified, not trusted.** StatCan vector IDs are opaque
  numbers, and a wrong one loads the wrong series without any error. Before
  every load, `verify-series` checks each configured ID against the title the
  API returns and stops the run on any mismatch.
- **Checks that test the data, not just the schema.** Besides grain,
  completeness, gaps and range, two checks reconcile numbers against each
  other: the published unemployment rate must match unemployment divided by
  labour force, and the 16 industries must sum to total NL employment from a
  different StatCan table (within 0.5%; the largest gap to date is 0.22%).
- **DuckDB instead of a cloud warehouse.** The data is about 17,000 rows. DuckDB
  runs in-process, needs no account or credentials, and supports `MERGE`,
  window functions and schemas, so the SQL is written the way it would be on a
  larger warehouse.
- **Industries loaded at a level with full history.** StatCan's separate
  wholesale and retail series are missing 132 early months, so the combined
  "wholesale and retail trade" series is used instead.

## Run it locally

Requires Python 3.10 or later. No accounts or keys: the StatCan API is public.

```bash
python -m venv .venv && source .venv/bin/activate
```

```bash
pip install -e ".[dev]"
```

```bash
nl-labour run
```

```bash
nl-labour dashboard --out site
```

The first `run` loads full history (about 10 seconds); later runs are
incremental. Other commands: `nl-labour verify-series`, `nl-labour check`, and
`nl-labour run --full-refresh`. Open `site/index.html` in a browser to view the
dashboard.

Tests run offline against a recorded API response:

```bash
pytest
```

## Project layout

```
config/series.yaml            the 28 series loaded, pinned by vector ID
src/nl_labour/
  statcan.py                  API client (retries, per-request status checks)
  warehouse.py                batch loading, transactions, check runner
  cli.py                      nl-labour command
  dashboard.py                builds the static dashboard from reporting views
  sql/01_raw.sql ... 05_reporting.sql
  sql/checks/                 one file per data-quality check
tests/                        pipeline tests, including revision handling
.github/workflows/            CI (lint + tests) and the scheduled pipeline
```

## Limitations

- Covers NL and Canada totals plus NL industries. Other provinces, age groups,
  gender and wages are not loaded yet.
- Revision tracking starts from the first load. Revisions StatCan made before
  that are not captured.
- The industry comparisons carry the LFS's sampling error. StatCan publishes
  standard errors for these estimates, which are not loaded yet.

## Data source and licence

Source: Statistics Canada, Table 14-10-0287-01 (Labour force characteristics,
monthly, seasonally adjusted) and Table 14-10-0355-01 (Employment by industry,
monthly, seasonally adjusted), retrieved through the
[Web Data Service](https://www.statcan.gc.ca/en/developers/wds). Reproduced and
distributed on an "as is" basis with the permission of Statistics Canada, under
the [Statistics Canada Open Licence](https://www.statcan.gc.ca/en/terms-conditions/open-licence).
This does not constitute an endorsement by Statistics Canada of this product.

The code is released under the MIT License (see [LICENSE](LICENSE)). The data
is not covered by that license.

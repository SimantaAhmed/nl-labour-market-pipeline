"""Build a static, self-contained HTML dashboard from the reporting views."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from .warehouse import run_checks

TEMPLATE = Path(__file__).parent / "templates" / "dashboard.html"


def _rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def collect(con: duckdb.DuckDBPyConnection) -> dict:
    return {
        "rates": _rows(con, """
            SELECT strftime(month_start, '%Y-%m') AS month, indicator, nl, canada
            FROM reporting.nl_vs_canada ORDER BY month_start"""),
        "employment": _rows(con, """
            SELECT strftime(month_start, '%Y-%m') AS month, value
            FROM reporting.monthly_series
            WHERE geography = 'Newfoundland and Labrador' AND indicator = 'Employment'
              AND industry = 'Total, all industries'
            ORDER BY month_start"""),
        "industries": _rows(con, """
            SELECT industry, sector, employment_k, share_pct, change_1y_k,
                   change_10y_k, change_10y_pct, strftime(window_end, '%Y-%m') AS window_end
            FROM reporting.nl_industry_employment"""),
        "revisions": _rows(con, """
            SELECT strftime(detected_at, '%Y-%m-%d') AS detected, geography, indicator,
                   industry, strftime(month_start, '%Y-%m') AS month, old_value, new_value
            FROM reporting.revisions ORDER BY detected_at DESC, abs(change) DESC LIMIT 50"""),
        "pipeline": _rows(con, """
            SELECT
                (SELECT strftime(min(started_at), '%Y-%m-%d') FROM raw.load_batch
                  WHERE status = 'succeeded')                              AS tracking_since,
                (SELECT strftime(max(finished_at), '%Y-%m-%d %H:%M UTC') FROM raw.load_batch
                  WHERE status = 'succeeded')                              AS last_run,
                (SELECT strftime(max(release_time), '%Y-%m-%d') FROM marts.fact_labour_market)
                                                                           AS last_release,
                (SELECT count(*) FROM marts.fact_labour_market)            AS facts,
                (SELECT count(*) FROM raw.series)                          AS series,
                (SELECT count(*) FROM marts.fact_revision)                 AS revisions
            """)[0],
        "checks": [
            {"name": c.name, "severity": c.severity, "passed": c.passed,
             "description": c.description}
            for c in run_checks(con)
        ],
    }


def build(con: duckdb.DuckDBPyConnection, out_dir: Path) -> Path:
    payload = json.dumps(collect(con), default=str, separators=(",", ":"))
    # The JSON sits inside a <script> tag, so "</" must not appear literally.
    html = TEMPLATE.read_text().replace("__DATA__", payload.replace("</", "<\\/"))
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "index.html"
    path.write_text(html, encoding="utf-8")
    return path

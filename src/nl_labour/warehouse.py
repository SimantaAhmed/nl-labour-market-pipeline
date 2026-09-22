"""Load StatCan data into the DuckDB warehouse and run the SQL layers."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from .series import Series
from .statcan import StatCanClient, flatten

log = logging.getLogger(__name__)

SQL_DIR = Path(__file__).parent / "sql"
SCHEMA_FILES = ["01_raw.sql", "02_staging.sql", "03_marts.sql", "05_reporting.sql"]

# StatCan's LFS tables go back to January 1976 (under 700 months); asking for
# more returns everything. Incremental runs re-read three years, which covers
# the routine seasonal-adjustment revisions published each January.
FULL_HISTORY_MONTHS = 1000
INCREMENTAL_MONTHS = 36


@dataclass
class BatchResult:
    batch_id: int
    mode: str
    rows_landed: int
    facts_inserted: int
    facts_revised: int

    @property
    def changed(self) -> bool:
        return self.facts_inserted > 0 or self.facts_revised > 0


@dataclass
class CheckResult:
    name: str
    severity: str
    description: str
    violations: int
    sample: list[tuple] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.violations == 0


def connect(path: str | Path) -> duckdb.DuckDBPyConnection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    for name in SCHEMA_FILES:
        con.execute((SQL_DIR / name).read_text())
    return con


def sync_series(con: duckdb.DuckDBPyConnection, series: list[Series]) -> None:
    con.execute("DELETE FROM raw.series")
    con.executemany(
        "INSERT INTO raw.series VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(s.vector_id, s.table, s.geography, s.indicator, s.industry,
          s.naics, s.sector, s.unit, s.is_rate) for s in series],
    )


def land(con: duckdb.DuckDBPyConnection, batch_id: int, rows: list[dict]) -> int:
    """Bulk insert one batch into raw.observation, one list per column."""
    if not rows:
        return 0
    cols = ["vector_id", "ref_period", "value", "decimals", "scalar_factor_code",
            "symbol_code", "status_code", "release_time"]
    con.execute(
        f"""
        INSERT INTO raw.observation
        SELECT $batch_id, {", ".join(f"unnest(${c})" for c in cols)}
        """,
        {"batch_id": batch_id, **{c: [r[c] for r in rows] for c in cols}},
    )
    return len(rows)


def _count(con: duckdb.DuckDBPyConnection, sql: str, *params) -> int:
    return con.execute(sql, list(params)).fetchone()[0]


def run_batch(
    con: duckdb.DuckDBPyConnection,
    client: StatCanClient,
    series: list[Series],
    full_refresh: bool = False,
) -> BatchResult:
    sync_series(con, series)

    empty = _count(con, "SELECT count(*) FROM marts.fact_labour_market") == 0
    mode = "full" if full_refresh or empty else "incremental"
    latest_n = FULL_HISTORY_MONTHS if mode == "full" else INCREMENTAL_MONTHS

    batch_id = _count(con, "SELECT coalesce(max(batch_id), 0) + 1 FROM raw.load_batch")
    con.execute(
        "INSERT INTO raw.load_batch (batch_id, started_at, mode, latest_n, status) "
        "VALUES (?, ?, ?, ?, 'running')",
        [batch_id, datetime.now(timezone.utc), mode, latest_n],
    )

    in_transaction = False
    try:
        log.info("batch %d: requesting %d series, %s (%d months)",
                 batch_id, len(series), mode, latest_n)
        rows = flatten(client.latest_data([s.vector_id for s in series], latest_n))

        con.begin()
        in_transaction = True
        landed = land(con, batch_id, rows)
        before = _count(con, "SELECT count(*) FROM marts.fact_labour_market")
        con.execute(f"SET VARIABLE batch_id = {batch_id}")
        con.execute((SQL_DIR / "04_load.sql").read_text())
        inserted = _count(con, "SELECT count(*) FROM marts.fact_labour_market") - before
        revised = _count(con, "SELECT count(*) FROM marts.fact_revision WHERE batch_id = ?",
                         batch_id)
        con.execute(
            "UPDATE raw.load_batch SET finished_at = ?, rows_landed = ?, "
            "facts_inserted = ?, facts_revised = ?, status = 'succeeded' "
            "WHERE batch_id = ?",
            [datetime.now(timezone.utc), landed, inserted, revised, batch_id],
        )
        con.commit()
    except Exception:
        if in_transaction:
            con.rollback()
        con.execute(
            "UPDATE raw.load_batch SET finished_at = ?, status = 'failed' WHERE batch_id = ?",
            [datetime.now(timezone.utc), batch_id],
        )
        raise

    result = BatchResult(batch_id, mode, landed, inserted, revised)
    log.info("batch %d: landed %d rows, %d new facts, %d revised",
             batch_id, landed, inserted, revised)
    return result


def run_checks(con: duckdb.DuckDBPyConnection) -> list[CheckResult]:
    results = []
    for path in sorted((SQL_DIR / "checks").glob("*.sql")):
        sql = path.read_text()
        header = [ln[2:].strip() for ln in sql.splitlines() if ln.startswith("--")]
        severity = header[0].removeprefix("severity:").strip()
        description = " ".join(header[1:])
        rows = con.execute(sql).fetchall()
        results.append(CheckResult(path.stem, severity, description, len(rows), rows[:5]))
    return results

"""Command line entry point: `nl-labour <command>` or `python -m nl_labour <command>`."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import warehouse
from .series import load_series
from .statcan import StatCanClient

DEFAULT_DB = Path("warehouse/nl_labour.duckdb")


def verify_series(client: StatCanClient) -> bool:
    """Check every configured vector still points at the series we think it does."""
    series = load_series()
    info = {o["vectorId"]: o for o in client.series_info(s.vector_id for s in series)}
    ok = True
    for s in series:
        got = info.get(s.vector_id, {}).get("SeriesTitleEn")
        if got != s.expected_title:
            ok = False
            print(f"MISMATCH {s.vector_id}: expected {s.expected_title!r}, got {got!r}")
    print(f"{len(series)} series checked: {'all match' if ok else 'mismatches found'}")
    return ok


def print_checks(results: list[warehouse.CheckResult]) -> bool:
    failed = False
    for r in results:
        status = "PASS" if r.passed else ("FAIL" if r.severity == "error" else "WARN")
        print(f"{status:4}  {r.name}  ({r.violations} violations)")
        if not r.passed:
            print(f"      {r.description}")
            for row in r.sample:
                print(f"      {row}")
            failed |= r.severity == "error"
    return not failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nl-labour")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="DuckDB file")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="verify series, load new data, run checks")
    run.add_argument("--full-refresh", action="store_true",
                     help="re-read full history instead of the last 36 months")
    run.add_argument("--summary", type=Path, help="write the batch result as JSON")
    sub.add_parser("verify-series", help="check configured vector IDs against StatCan")
    sub.add_parser("check", help="run data-quality checks on the warehouse")
    dash = sub.add_parser("dashboard", help="build the static dashboard")
    dash.add_argument("--out", type=Path, default=Path("site"))

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    client = StatCanClient()

    if args.command == "verify-series":
        return 0 if verify_series(client) else 1

    if args.command == "run":
        if not verify_series(client):
            return 1
        con = warehouse.connect(args.db)
        result = warehouse.run_batch(con, client, load_series(), args.full_refresh)
        if args.summary:
            args.summary.write_text(json.dumps({**vars(result), "changed": result.changed}))
        return 0 if print_checks(warehouse.run_checks(con)) else 1

    if args.command == "check":
        con = warehouse.connect(args.db)
        return 0 if print_checks(warehouse.run_checks(con)) else 1

    if args.command == "dashboard":
        from .dashboard import build
        con = warehouse.connect(args.db)
        print(f"wrote {build(con, args.out)}")
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())

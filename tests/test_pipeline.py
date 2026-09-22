"""Offline tests: a fake WDS client replays a real API response (tests/fixtures)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from nl_labour import warehouse
from nl_labour.cli import verify_series
from nl_labour.series import ALL_INDUSTRIES, Series, load_series
from nl_labour.statcan import StatCanError, flatten

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "wds_latest_3.json").read_text())

NL = "Newfoundland and Labrador"
SERIES = [
    Series(2062999, "14-10-0287-01", NL, "Labour force", ALL_INDUSTRIES, None, None),
    Series(2063003, "14-10-0287-01", NL, "Unemployment", ALL_INDUSTRIES, None, None),
    Series(2063004, "14-10-0287-01", NL, "Unemployment rate", ALL_INDUSTRIES, None, None),
]
UNEMPLOYMENT_RATE = 2063004


class FakeClient:
    """Returns the recorded response; tests edit `objects` to simulate StatCan changes."""

    def __init__(self):
        self.objects = [r["object"] for r in copy.deepcopy(FIXTURE)]
        self.fail = False

    def latest_data(self, vector_ids, latest_n):
        if self.fail:
            raise StatCanError("simulated outage")
        return copy.deepcopy(self.objects)

    def points(self, vector_id):
        return next(o for o in self.objects if o["vectorId"] == vector_id)["vectorDataPoint"]


@pytest.fixture
def con():
    c = warehouse.connect(":memory:")
    yield c
    c.close()


@pytest.fixture
def client():
    return FakeClient()


def scalar(con, sql, *params):
    return con.execute(sql, list(params)).fetchone()[0]


def check(con, name):
    return next(r for r in warehouse.run_checks(con) if r.name == name)


def test_flatten_one_row_per_point():
    rows = flatten([r["object"] for r in FIXTURE])
    assert len(rows) == 9
    assert rows[0]["vector_id"] == 2062999
    assert rows[0]["ref_period"] == "2026-06-01"
    assert rows[0]["value"] == 265.6


def test_config_series_titles():
    series = load_series()
    assert len(series) == 28
    by_id = {s.vector_id: s for s in series}
    assert by_id[2063004].expected_title == (
        "Newfoundland and Labrador;Unemployment rate;Total - Gender;"
        "15 years and over;Estimate;Seasonally adjusted")
    assert by_id[2057636].expected_title == (
        "Newfoundland and Labrador;Health care and social assistance;"
        "Estimate;Seasonally adjusted")


def test_verify_series_flags_a_moved_vector(capsys):
    class InfoClient:
        def series_info(self, ids):
            return [{"vectorId": v, "SeriesTitleEn": s.expected_title}
                    for v, s in ((s.vector_id, s) for s in load_series())
                    if v != 2063004] + [{"vectorId": 2063004, "SeriesTitleEn": "Canada;All-items"}]

    assert verify_series(InfoClient()) is False
    assert "MISMATCH 2063004" in capsys.readouterr().out


def test_first_run_loads_everything(con, client):
    result = warehouse.run_batch(con, client, SERIES)
    assert (result.mode, result.rows_landed, result.facts_inserted, result.facts_revised) == \
        ("full", 9, 9, 0)
    assert scalar(con, "SELECT count(*) FROM marts.dim_date") == 3
    assert all(r.passed for r in warehouse.run_checks(con) if r.severity == "error")


def test_rerun_with_no_changes_writes_nothing(con, client):
    warehouse.run_batch(con, client, SERIES)
    result = warehouse.run_batch(con, client, SERIES)
    assert result.mode == "incremental"
    assert result.rows_landed == 9          # raw keeps every batch
    assert not result.changed               # the fact table does not move
    assert scalar(con, "SELECT count(*) FROM marts.fact_labour_market") == 9
    assert scalar(con, "SELECT max(last_changed_batch) FROM marts.fact_labour_market") == 1


def test_revision_updates_fact_and_is_logged(con, client):
    warehouse.run_batch(con, client, SERIES)
    client.points(UNEMPLOYMENT_RATE)[0]["value"] = 8.4    # June revised 8.2 -> 8.4
    result = warehouse.run_batch(con, client, SERIES)

    assert (result.facts_inserted, result.facts_revised) == (0, 1)
    assert scalar(con, "SELECT value FROM marts.fact_labour_market "
                       "WHERE vector_id = ? AND date_key = 202606", UNEMPLOYMENT_RATE) == 8.4
    assert con.execute("SELECT old_value, new_value, batch_id FROM marts.fact_revision"
                       ).fetchall() == [(8.2, 8.4, 2)]
    # Both published versions stay in raw.
    assert scalar(con, "SELECT count(DISTINCT value) FROM raw.observation "
                       "WHERE vector_id = ? AND ref_period = '2026-06-01'", UNEMPLOYMENT_RATE) == 2


def test_value_becoming_suppressed_counts_as_revision(con, client):
    warehouse.run_batch(con, client, SERIES)
    client.points(UNEMPLOYMENT_RATE)[1]["value"] = None
    assert warehouse.run_batch(con, client, SERIES).facts_revised == 1


def test_new_month_is_inserted(con, client):
    warehouse.run_batch(con, client, SERIES)
    for obj in client.objects:
        pt = copy.deepcopy(obj["vectorDataPoint"][-1])
        pt["refPer"] = "2026-09-01"
        obj["vectorDataPoint"].append(pt)
    result = warehouse.run_batch(con, client, SERIES)
    assert (result.facts_inserted, result.facts_revised) == (3, 0)
    assert scalar(con, "SELECT max(date_key) FROM marts.dim_date") == 202609


def test_failed_fetch_marks_batch_failed_and_lands_nothing(con, client):
    warehouse.run_batch(con, client, SERIES)
    client.fail = True
    with pytest.raises(StatCanError):
        warehouse.run_batch(con, client, SERIES)
    assert scalar(con, "SELECT status FROM raw.load_batch WHERE batch_id = 2") == "failed"
    assert scalar(con, "SELECT count(*) FROM raw.observation WHERE batch_id = 2") == 0


def test_checks_catch_inconsistent_rate(con, client):
    client.points(UNEMPLOYMENT_RATE)[2]["value"] = 12.0   # 23.0 / 268.1 is 8.6%, not 12
    warehouse.run_batch(con, client, SERIES)
    assert check(con, "unemployment_rate_consistent").violations == 1


def test_checks_catch_rate_out_of_range(con, client):
    client.points(UNEMPLOYMENT_RATE)[2]["value"] = 150.0
    warehouse.run_batch(con, client, SERIES)
    assert check(con, "rates_in_range").violations == 1


def test_checks_catch_missing_month(con, client):
    del client.points(UNEMPLOYMENT_RATE)[1]
    warehouse.run_batch(con, client, SERIES)
    assert check(con, "monthly_gaps").violations == 1

"""Client for the Statistics Canada Web Data Service (WDS).

API guide: https://www.statcan.gc.ca/en/developers/wds/user-guide
The WDS needs no authentication. Each POST endpoint takes a JSON list of
requests and returns a list of {"status": ..., "object": ...} results, one per
request, so a single bad vector does not fail the whole call.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://www150.statcan.gc.ca/t1/wds/rest"
MAX_RETRIES = 4


class StatCanError(RuntimeError):
    pass


class StatCanClient:
    def __init__(self, base_url: str = BASE_URL, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _post(self, endpoint: str, body: list[dict]) -> list[dict]:
        url = f"{self.base_url}/{endpoint}"
        delay = 1.0
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.post(url, json=body, timeout=self.timeout)
                resp.raise_for_status()
                return resp.json()
            except (requests.RequestException, ValueError) as exc:
                if attempt == MAX_RETRIES:
                    raise StatCanError(f"{endpoint} failed after {attempt} attempts") from exc
                log.warning("%s attempt %d failed (%s), retrying in %.0fs",
                            endpoint, attempt, exc, delay)
                time.sleep(delay)
                delay *= 2
        raise AssertionError("unreachable")

    @staticmethod
    def _unwrap(results: list[dict]) -> list[dict]:
        failed = [r for r in results if r.get("status") != "SUCCESS"]
        if failed:
            raise StatCanError(f"{len(failed)} request(s) failed: {failed[:3]}")
        return [r["object"] for r in results]

    def series_info(self, vector_ids: Iterable[int]) -> list[dict]:
        body = [{"vectorId": int(v)} for v in vector_ids]
        return self._unwrap(self._post("getSeriesInfoFromVector", body))

    def latest_data(self, vector_ids: Iterable[int], latest_n: int) -> list[dict]:
        body = [{"vectorId": int(v), "latestN": int(latest_n)} for v in vector_ids]
        return self._unwrap(self._post("getDataFromVectorsAndLatestNPeriods", body))


def flatten(objects: list[dict]) -> list[dict]:
    """One row per (vector, reference month), in the landing table's column order."""
    rows = []
    for obj in objects:
        for dp in obj.get("vectorDataPoint", []):
            rows.append({
                "vector_id": obj["vectorId"],
                "ref_period": dp["refPer"],
                "value": dp["value"],
                "decimals": dp.get("decimals"),
                "scalar_factor_code": dp.get("scalarFactorCode"),
                "symbol_code": dp.get("symbolCode"),
                "status_code": dp.get("statusCode"),
                "release_time": dp.get("releaseTime"),
            })
    return rows

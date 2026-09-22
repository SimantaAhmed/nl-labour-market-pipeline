"""Series catalogue: which StatCan vectors the pipeline loads, and what they mean."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "series.yaml"

ALL_INDUSTRIES = "Total, all industries"
RATE_INDICATORS = {"Unemployment rate", "Participation rate", "Employment rate"}


@dataclass(frozen=True)
class Series:
    vector_id: int
    table: str
    geography: str
    indicator: str
    industry: str
    naics: str | None
    sector: str | None

    @property
    def is_rate(self) -> bool:
        return self.indicator in RATE_INDICATORS

    @property
    def unit(self) -> str:
        return "Percent" if self.is_rate else "Persons (thousands)"

    @property
    def expected_title(self) -> str:
        """The SeriesTitleEn StatCan returns for this vector."""
        if self.industry == ALL_INDUSTRIES:
            return (
                f"{self.geography};{self.indicator};Total - Gender;"
                "15 years and over;Estimate;Seasonally adjusted"
            )
        return f"{self.geography};{self.industry};Estimate;Seasonally adjusted"


def load_series(path: Path = DEFAULT_CONFIG) -> list[Series]:
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    lfs = cfg["labour_force"]
    out = [
        Series(
            vector_id=s["vector_id"],
            table=lfs["table"],
            geography=s["geography"],
            indicator=s["indicator"],
            industry=ALL_INDUSTRIES,
            naics=None,
            sector=None,
        )
        for s in lfs["series"]
    ]

    ind = cfg["employment_by_industry"]
    out += [
        Series(
            vector_id=s["vector_id"],
            table=ind["table"],
            geography=ind["geography"],
            indicator=ind["indicator"],
            industry=s["industry"],
            naics=s["naics"],
            sector=s["sector"],
        )
        for s in ind["series"]
    ]

    ids = [s.vector_id for s in out]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate vector IDs in {path}")
    return out

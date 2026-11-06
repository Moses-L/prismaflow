"""Data model, CSV I/O and validation for PRISMA 2020 flow diagrams."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

# Count fields accepted in the CSV ``data`` column.
COUNT_FIELDS = [
    # previous version of the review
    "previous_studies",
    "previous_reports",
    # identification: databases and registers
    "identified_databases",
    "identified_registers",
    "duplicates",
    "excluded_automatic",
    "excluded_other",
    # screening
    "excluded_screening",
    "not_retrieved",
    # inclusion (new studies / reports)
    "new_studies",
    "new_reports",
    # other methods
    "other_websites",
    "other_organisations",
    "other_citation_searching",
    "other_sought",
    "other_not_retrieved",
]

# Derived boxes: these accept a url/tooltip in the CSV but their count is computed.
LINK_ONLY_FIELDS = [
    "screened",
    "sought",
    "assessed",
    "excluded_fulltext",
    "other_assessed",
    "other_excluded",
    "total_studies",
]

REASON_DB = "reason_db"
REASON_OTHER = "reason_other"

TEMPLATE_ROWS = [
    ("previous_studies", "", "", "", "Studies included in previous version of review"),
    ("previous_reports", "", "", "", "Reports of studies included in previous version"),
    ("identified_databases", "", "", "", "Records identified from databases"),
    ("identified_registers", "", "", "", "Records identified from registers"),
    ("duplicates", "", "", "", "Duplicate records removed"),
    ("excluded_automatic", "", "", "", "Records marked ineligible by automation tools"),
    ("excluded_other", "", "", "", "Records removed for other reasons"),
    ("excluded_screening", "", "", "", "Records excluded at title/abstract screening"),
    ("not_retrieved", "", "", "", "Reports not retrieved"),
    ("reason_db", "Wrong population", "", "", "One row per full-text exclusion reason"),
    ("reason_db", "Wrong outcome", "", "", ""),
    ("new_studies", "", "", "", "New studies included in review"),
    ("new_reports", "", "", "", "Reports of new included studies"),
    ("other_websites", "", "", "", "Other methods: records from websites (optional)"),
    ("other_organisations", "", "", "", "Other methods: records from organisations (optional)"),
    ("other_citation_searching", "", "", "", "Other methods: citation searching (optional)"),
    ("other_sought", "", "", "", "Other methods: reports sought (defaults to total identified)"),
    ("other_not_retrieved", "", "", "", "Other methods: reports not retrieved"),
    ("reason_other", "Wrong design", "", "", "Other methods: one row per exclusion reason"),
]


@dataclass
class PrismaData:
    """Counts, exclusion reasons, hyperlinks and tooltips for one diagram.

    Optional arms are switched on automatically when their inputs are given:
    ``previous_studies`` enables the previous-version arm and any ``other_*``
    count enables the "other methods" arm.
    """

    counts: Dict[str, int] = field(default_factory=dict)
    reasons_db: Dict[str, int] = field(default_factory=dict)
    reasons_other: Dict[str, int] = field(default_factory=dict)
    urls: Dict[str, str] = field(default_factory=dict)
    tooltips: Dict[str, str] = field(default_factory=dict)

    # ------------------------------------------------------------------ access
    def get(self, key: str, default: int = 0) -> int:
        return int(self.counts.get(key, default))

    def has(self, key: str) -> bool:
        return key in self.counts

    @property
    def use_previous(self) -> bool:
        return self.has("previous_studies") or self.has("previous_reports")

    @property
    def use_other(self) -> bool:
        return any(
            self.has(k)
            for k in ("other_websites", "other_organisations", "other_citation_searching", "other_sought")
        )

    # ------------------------------------------------------------ derived values
    @property
    def identified_total(self) -> int:
        return self.get("identified_databases") + self.get("identified_registers")

    @property
    def screened(self) -> int:
        return (
            self.identified_total
            - self.get("duplicates")
            - self.get("excluded_automatic")
            - self.get("excluded_other")
        )

    @property
    def sought(self) -> int:
        return self.screened - self.get("excluded_screening")

    @property
    def assessed(self) -> int:
        return self.sought - self.get("not_retrieved")

    @property
    def excluded_fulltext(self) -> int:
        return sum(self.reasons_db.values())

    @property
    def other_identified(self) -> int:
        return (
            self.get("other_websites")
            + self.get("other_organisations")
            + self.get("other_citation_searching")
        )

    @property
    def other_sought(self) -> int:
        return self.get("other_sought", self.other_identified)

    @property
    def other_assessed(self) -> int:
        return self.other_sought - self.get("other_not_retrieved")

    @property
    def other_excluded(self) -> int:
        return sum(self.reasons_other.values())

    @property
    def new_studies(self) -> int:
        return self.get("new_studies")

    @property
    def total_studies(self) -> int:
        return self.get("previous_studies") + self.new_studies

    @property
    def total_reports(self) -> int:
        return self.get("previous_reports") + self.get("new_reports")

    # ---------------------------------------------------------------- validation
    def validate(self) -> list[str]:
        """Raise ``ValueError`` on impossible counts; return soft warnings."""
        problems, warnings = [], []
        for k, v in self.counts.items():
            if v < 0:
                problems.append(f"{k} is negative ({v})")
        derived = {
            "records screened": self.screened,
            "reports sought for retrieval": self.sought,
            "reports assessed for eligibility": self.assessed,
        }
        if self.use_other:
            derived["other-methods reports assessed"] = self.other_assessed
        for name, val in derived.items():
            if val < 0:
                problems.append(f"{name} would be negative ({val}); check the preceding counts")
        if self.assessed >= 0 and self.excluded_fulltext > self.assessed:
            problems.append(
                f"full-text exclusions ({self.excluded_fulltext}) exceed reports assessed ({self.assessed})"
            )
        if self.use_other and self.other_assessed >= 0 and self.other_excluded > self.other_assessed:
            problems.append(
                f"other-methods exclusions ({self.other_excluded}) exceed reports assessed ({self.other_assessed})"
            )
        if not self.has("new_studies"):
            warnings.append("new_studies not supplied; the final box will show 0")
        if self.has("new_reports"):
            expected = max(self.assessed - self.excluded_fulltext, 0)
            if self.use_other:
                expected += max(self.other_assessed - self.other_excluded, 0)
            if self.get("new_reports") != expected:
                warnings.append(
                    f"new_reports ({self.get('new_reports')}) differs from reports assessed minus "
                    f"exclusions ({expected}); check the counts"
                )
        if self.has("new_studies") and self.has("new_reports") and self.new_studies > self.get("new_reports"):
            warnings.append("new_studies exceeds new_reports; a study needs at least one report")
        if problems:
            raise ValueError("Invalid PRISMA counts: " + "; ".join(problems))
        return warnings

    # ----------------------------------------------------------------------- I/O
    @classmethod
    def from_csv(cls, path: str | Path) -> "PrismaData":
        """Read the template CSV (columns: data, label, n, url, tooltip, [notes])."""
        obj = cls()
        with open(path, newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                key = (row.get("data") or "").strip()
                if not key or key.startswith("#"):
                    continue
                label = (row.get("label") or "").strip()
                n_raw = (row.get("n") or "").strip()
                url = (row.get("url") or "").strip()
                tip = (row.get("tooltip") or "").strip()
                if key in (REASON_DB, REASON_OTHER):
                    if not label or n_raw == "":
                        continue
                    target = obj.reasons_db if key == REASON_DB else obj.reasons_other
                    target[label] = _to_int(n_raw, key)
                    continue
                if key not in COUNT_FIELDS and key not in LINK_ONLY_FIELDS:
                    valid = ", ".join(COUNT_FIELDS + LINK_ONLY_FIELDS)
                    raise ValueError(f"Unknown data item '{key}'. Valid items: {valid}")
                if n_raw != "" and key in COUNT_FIELDS:
                    obj.counts[key] = _to_int(n_raw, key)
                if url:
                    obj.urls[key] = url
                if tip:
                    obj.tooltips[key] = tip
        return obj

    @staticmethod
    def write_template(path: str | Path) -> None:
        """Write a blank template CSV that users can fill in."""
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["data", "label", "n", "url", "tooltip", "notes"])
            for key, label, n, url, note in TEMPLATE_ROWS:
                w.writerow([key, label, n, url, "", note])


def _to_int(raw: str, key: str) -> int:
    try:
        return int(float(raw.replace(",", "")))
    except ValueError as exc:
        raise ValueError(f"Value for '{key}' is not a number: {raw!r}") from exc


def example_data() -> PrismaData:
    """A complete worked example (invented numbers) with all arms enabled."""
    return PrismaData(
        counts={
            "previous_studies": 12,
            "previous_reports": 15,
            "identified_databases": 1200,
            "identified_registers": 40,
            "duplicates": 250,
            "excluded_automatic": 10,
            "excluded_other": 0,
            "excluded_screening": 900,
            "not_retrieved": 5,
            "new_studies": 40,
            "new_reports": 47,
            "other_websites": 30,
            "other_organisations": 10,
            "other_citation_searching": 25,
            "other_sought": 50,
            "other_not_retrieved": 4,
        },
        reasons_db={"Wrong population": 20, "No outcome of interest": 25, "Wrong design": 15},
        reasons_other={"Wrong population": 8, "Wrong design": 6},
        tooltips={"identified_databases": "PubMed, Embase, Cochrane CENTRAL; searched 1 Nov 2026"},
        urls={"identified_databases": "https://pubmed.ncbi.nlm.nih.gov/"},
    )

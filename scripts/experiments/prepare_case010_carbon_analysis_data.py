"""Create the minimal, hashable analysis extract for Case010.

Requires ``pyreadstat``.  The input Stata file is immutable; only explicitly
listed firm-year fields are copied to a UTF-8 CSV.  No outcome-based filtering
or model estimation happens here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyreadstat


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = (
    ROOT
    / "experiments/fixtures/case010_mendeley_carbon_green_innovation_candidate_v1.dta"
)
DEFAULT_OUTPUT = (
    ROOT / "experiments/fixtures/case010_mendeley_analysis_extract_v1.csv"
)
EXPECTED_SOURCE_SHA256 = (
    "15bbce1ca0b7f3ab2adf8381c0fa57c335c6fcd42fd99285b0a3f59a5b7d819e"
)

SOURCE_FIELDS = [
    "Symbol",
    "year",
    "PROVINCECODE",
    "CITYCODE",
    "IndustryCode",
    "carbon_post",
    "green_patent1",
    "green_patent2",
    "green_patent3",
    "green_patent4",
    "green_patent5",
    "green_patent6",
    "FC_index",
    "KZ_index",
    "SA_index",
    "WW_index",
    "Size",
    "SOE",
    "Lev",
    "ROA",
    "HHI_A",
]

RENAME = {
    "Symbol": "firm_id",
    "year": "year",
    "PROVINCECODE": "province_code",
    "CITYCODE": "city_code",
    "IndustryCode": "industry_code",
    "carbon_post": "source_policy_post",
    "green_patent1": "green_patent_independent_all",
    "green_patent2": "green_invention_independent",
    "green_patent3": "green_utility_independent",
    "green_patent4": "green_patent_joint_all",
    "green_patent5": "green_invention_joint",
    "green_patent6": "green_utility_joint",
    "FC_index": "financing_constraint_fc",
    "KZ_index": "financing_constraint_kz",
    "SA_index": "financing_constraint_sa",
    "WW_index": "financing_constraint_ww",
    "Size": "total_assets",
    "SOE": "state_ownership_code",
    "Lev": "leverage",
    "ROA": "return_on_assets",
    "HHI_A": "industry_hhi_a",
}


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_firm_id(value: object) -> str:
    if pd.isna(value):
        return ""
    try:
        return f"{int(float(value)):06d}"
    except (TypeError, ValueError, OverflowError):
        return str(value).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    source_hash = file_hash(args.source)
    if source_hash != EXPECTED_SOURCE_SHA256:
        raise ValueError(f"source SHA-256 mismatch: {source_hash}")

    data, _ = pyreadstat.read_dta(
        args.source,
        usecols=SOURCE_FIELDS,
        encoding="latin1",
        apply_value_formats=False,
        formats_as_category=False,
    )
    data = data.rename(columns=RENAME)
    data["firm_id"] = data["firm_id"].map(normalize_firm_id)
    data["year"] = pd.to_numeric(data["year"], errors="raise").astype("int64")
    data = data.sort_values(["firm_id", "year"], kind="stable").reset_index(drop=True)

    if data["firm_id"].eq("").any():
        raise ValueError("blank firm_id after normalization")
    if data.duplicated(["firm_id", "year"]).any():
        raise ValueError("firm_id-year key is not unique")
    if not data["source_policy_post"].dropna().isin([0, 1]).all():
        raise ValueError("source_policy_post is not binary")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(args.output, index=False, encoding="utf-8", lineterminator="\n")

    manifest = {
        "schema_version": "case010-analysis-extract/1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "path": args.source.resolve().relative_to(ROOT.resolve()).as_posix(),
            "sha256": source_hash,
            "persistent_id": "doi:10.17632/rrfwny7byp.1",
            "license": "CC BY 4.0",
        },
        "output": {
            "path": args.output.resolve().relative_to(ROOT.resolve()).as_posix(),
            "sha256": file_hash(args.output),
            "rows": int(len(data)),
            "columns": list(data.columns),
            "unique_firms": int(data["firm_id"].nunique()),
            "year_min": int(data["year"].min()),
            "year_max": int(data["year"].max()),
            "duplicate_firm_year_rows": int(data.duplicated(["firm_id", "year"]).sum()),
        },
        "transformation": {
            "selected_source_fields": SOURCE_FIELDS,
            "renamed_fields": RENAME,
            "row_filter": "none",
            "outcome_filter": "none",
            "sort": ["firm_id", "year"],
            "encoding": "utf-8",
        },
        "environment": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "pyreadstat": pyreadstat.__version__,
        },
    }
    manifest_path = args.output.with_suffix(".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest["output"], ensure_ascii=False, indent=2))
    print(f"manifest={manifest_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

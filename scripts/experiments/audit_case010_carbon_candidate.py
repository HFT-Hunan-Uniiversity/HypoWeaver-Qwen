"""Audit the public firm-year candidate dataset for Case010.

The source is immutable and is never edited.  The script reads only a bounded
set of fields needed to decide whether the dataset can identify the effect of
China's national carbon market on high-quality green innovation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyreadstat


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA = (
    ROOT
    / "experiments/fixtures/case010_mendeley_carbon_green_innovation_candidate_v1.dta"
)
DEFAULT_OUTPUT = (
    ROOT / "output/experiments/case010_carbon_market_adaptive_v1/source_audit.json"
)

EXPECTED_SHA256 = "15bbce1ca0b7f3ab2adf8381c0fa57c335c6fcd42fd99285b0a3f59a5b7d819e"

FIELDS = [
    "Symbol",
    "year",
    "ListedCoID",
    "SecurityID",
    "PROVINCECODE",
    "CITYCODE",
    "IndustryCode",
    "id",
    "carbon_post",
    "pol",
    "pol2",
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
    "HHI_B",
    "HHI_C",
    "HHI_D",
    "industry",
]


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def repair_label(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def clean_scalar(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value)
    return str(value)


def grouped_summary(data: pd.DataFrame, field: str) -> list[dict[str, Any]]:
    rows = (
        data.groupby("year", dropna=False)[field]
        .agg(["count", "mean", "min", "max", "nunique"])
        .reset_index()
        .to_dict("records")
    )
    return [{key: clean_scalar(value) for key, value in row.items()} for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    actual_hash = file_hash(args.data)
    if actual_hash != EXPECTED_SHA256:
        raise ValueError(f"source SHA-256 mismatch: {actual_hash}")

    metadata_frame, metadata = pyreadstat.read_dta(
        args.data,
        metadataonly=True,
        encoding="latin1",
    )
    del metadata_frame
    missing_fields = sorted(set(FIELDS) - set(metadata.column_names))
    if missing_fields:
        raise ValueError(f"required audit fields missing: {missing_fields}")

    data, _ = pyreadstat.read_dta(
        args.data,
        usecols=FIELDS,
        encoding="latin1",
        apply_value_formats=False,
        formats_as_category=False,
    )

    years = sorted(float(value) for value in data["year"].dropna().unique())
    duplicate_symbol_year = int(data.duplicated(["Symbol", "year"]).sum())
    post_2021_rows = int((pd.to_numeric(data["year"], errors="coerce") > 2021).sum())
    carbon_post_varies_within_year = any(
        int(value) > 1
        for value in data.groupby("year", dropna=False)["carbon_post"].nunique(dropna=True)
    )
    numeric_year = pd.to_numeric(data["year"], errors="coerce")
    numeric_policy = pd.to_numeric(data["carbon_post"], errors="coerce")
    policy_order = data.assign(_year=numeric_year, _policy=numeric_policy).sort_values(
        ["Symbol", "_year"]
    )
    policy_reversals = int(
        policy_order.groupby("Symbol", dropna=False)["_policy"]
        .diff()
        .lt(0)
        .fillna(False)
        .sum()
    )
    first_treated_year = (
        policy_order.loc[policy_order["_policy"].eq(1)]
        .groupby("Symbol", dropna=False)["_year"]
        .min()
    )

    # Public launch years for the eight regional pilots.  This is only a
    # diagnostic: a mismatch does not rewrite the source variable.
    province_start = {11: 2013, 12: 2013, 31: 2013, 44: 2013, 42: 2014, 50: 2014, 35: 2016}
    province_code = pd.to_numeric(data["PROVINCECODE"], errors="coerce")
    expected_regional_post = pd.Series(0.0, index=data.index)
    for code, start in province_start.items():
        expected_regional_post.loc[province_code.eq(code) & numeric_year.ge(start)] = 1.0
    regional_post_match_rate = float(
        expected_regional_post.eq(numeric_policy).where(numeric_policy.notna()).mean()
    )

    national_market_requirements = {
        "contains_post_2021_outcomes": post_2021_rows > 0,
        "carbon_post_is_firm_specific_within_year": carbon_post_varies_within_year,
        "unique_firm_year_key": duplicate_symbol_year == 0,
        "high_quality_green_patent_field_present": "green_patent2" in data.columns,
        "financing_constraint_field_present": "SA_index" in data.columns,
        "official_national_ets_firm_list_bound": False,
    }
    can_support_national_ets_claim = all(national_market_requirements.values())

    result: dict[str, Any] = {
        "schema_version": "case010-source-audit/1.0.0",
        "source": {
            "title": "Industry Peer Effect of Corporate Green Innovation",
            "persistent_id": "doi:10.17632/rrfwny7byp.1",
            "source_url": "https://data.mendeley.com/datasets/rrfwny7byp/1",
            "license": "CC BY 4.0",
            "local_path": args.data.resolve().relative_to(ROOT.resolve()).as_posix(),
            "sha256": actual_hash,
            "bytes": args.data.stat().st_size,
        },
        "data_profile": {
            "rows": int(len(data)),
            "columns_in_source": int(metadata.number_columns),
            "columns_audited": len(FIELDS),
            "year_min": min(years) if years else None,
            "year_max": max(years) if years else None,
            "year_values": years,
            "year_counts": {
                str(clean_scalar(key)): int(value)
                for key, value in data["year"].value_counts(dropna=False).sort_index().items()
            },
            "unique_symbol": int(data["Symbol"].nunique(dropna=True)),
            "unique_id": int(data["id"].nunique(dropna=True)),
            "duplicate_symbol_year_rows": duplicate_symbol_year,
            "duplicate_id_year_rows": int(data.duplicated(["id", "year"]).sum()),
            "policy_reversal_rows": policy_reversals,
            "missing_rate": {
                field: round(float(data[field].isna().mean()), 6) for field in FIELDS
            },
        },
        "variable_dictionary": {
            field: repair_label(metadata.column_names_to_labels.get(field)) for field in FIELDS
        },
        "policy_field_diagnostics": {
            "carbon_post_by_year": grouped_summary(data, "carbon_post"),
            "pol_by_year": grouped_summary(data, "pol"),
            "pol2_by_year": grouped_summary(data, "pol2"),
            "first_treated_year_counts": {
                str(clean_scalar(key)): int(value)
                for key, value in first_treated_year.value_counts().sort_index().items()
            },
            "never_treated_firms": int(data["Symbol"].nunique() - first_treated_year.size),
            "public_regional_pilot_encoding_match_rate": round(
                regional_post_match_rate, 6
            ),
            "encoding_interpretation": (
                "carbon_post does not exactly encode a simple headquarters-province "
                "regional-pilot post indicator; a source codebook or author protocol is "
                "required before treating it as direct firm exposure."
                if regional_post_match_rate < 0.99
                else "carbon_post matches the public regional-pilot province timing rule."
            ),
        },
        "national_market_readiness": {
            "requirements": national_market_requirements,
            "can_support_national_ets_claim": can_support_national_ets_claim,
            "status": "eligible" if can_support_national_ets_claim else "blocked",
            "blockers": [
                label
                for label, passed in national_market_requirements.items()
                if not passed
            ],
            "decision": (
                "The dataset may enter a frozen national-ETS estimation protocol."
                if can_support_national_ets_claim
                else "Do not estimate or claim a national-ETS effect from this dataset."
            ),
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["national_market_readiness"], ensure_ascii=False, indent=2))
    print(f"output={args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

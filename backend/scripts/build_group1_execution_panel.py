from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify(path: Path, expected: str, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    actual = _sha256(path)
    if actual != expected:
        raise ValueError(f"{label} SHA-256 mismatch: {actual} != {expected}")


def _safe_output(path: Path, runtime_root: Path) -> Path:
    resolved = path.resolve()
    root = runtime_root.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"generated output must stay under {root}: {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _last_pre_location(
    history: pd.DataFrame,
    cohort_year: int,
) -> pd.DataFrame:
    return (
        history.loc[history["year"] < cohort_year]
        .sort_values(["firm_id", "year"])
        .drop_duplicates("firm_id", keep="last")
        .set_index("firm_id")[["cityname", "provincename"]]
    )


def _finite_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    result = frame.dropna(subset=columns).copy()
    finite = np.isfinite(result[columns].to_numpy(dtype=float)).all(axis=1)
    return result.loc[finite].copy()


def build(args: argparse.Namespace) -> dict[str, Any]:
    config_path = Path(args.config).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    sources = config["sources"]

    greenwashing_path = Path(args.greenwashing_dta).resolve()
    emissions_path = Path(args.emissions_dta).resolve()
    pku_workbook_path = Path(args.pku_workbook).resolve()
    pku_city_path = Path(args.pku_city_csv).resolve()
    _verify(greenwashing_path, sources["greenwashing"]["sha256"], "greenwashing source")
    _verify(emissions_path, sources["firm_emissions"]["sha256"], "emissions source")
    _verify(pku_workbook_path, sources["digital_capacity"]["sha256"], "PKU workbook")
    _verify(
        pku_city_path,
        sources["digital_capacity"]["city_extract_sha256"],
        "PKU city extract",
    )

    greenwashing = pd.read_stata(greenwashing_path, convert_categoricals=False)
    emissions = pd.read_stata(emissions_path, convert_categoricals=False)
    pku = pd.read_csv(pku_city_path, encoding="utf-8")

    if greenwashing.duplicated(["stkcd", "year"]).any():
        raise ValueError("greenwashing source has duplicate stock-year rows")
    if emissions.duplicated(["id", "year"]).any():
        raise ValueError("emissions source has duplicate stock-year rows")

    emissions_fields = [
        "id",
        "year",
        "cityname",
        "provincename",
        "lncarbon_emission",
    ]
    joined = greenwashing.merge(
        emissions[emissions_fields],
        left_on=["stkcd", "year"],
        right_on=["id", "year"],
        how="inner",
        validate="one_to_one",
    )
    joined = joined.loc[
        joined["operatingrevenue"].gt(0)
        & joined["gws_esg"].notna()
        & joined["lncarbon_emission"].notna()
    ].copy()
    joined["firm_id"] = joined["id"].astype(np.int64).map(lambda value: f"{value:06d}")
    joined["year"] = joined["year"].astype(np.int64)
    joined["greenwashing_gap"] = joined["gws_esg"].astype(float)
    joined["firm_emission_intensity"] = (
        joined["lncarbon_emission"].astype(float)
        - np.log(joined["operatingrevenue"].astype(float))
    )
    joined["direct_firm_log_emissions"] = joined["lncarbon_emission"].astype(float)
    joined["emission_intensity_denominator"] = "operating_revenue"
    joined["firm_size"] = joined["SIZE"]
    joined["leverage"] = joined["LEV"]
    joined["return_on_assets"] = joined["ROA"]
    joined["sales_growth"] = joined["SALESG"]
    joined["cash_ratio"] = joined["CASH"]
    joined["state_owned"] = joined["SOEs"]

    history = emissions.loc[emissions["id"].isin(joined["id"].unique())].copy()
    history["firm_id"] = history["id"].astype(np.int64).map(
        lambda value: f"{value:06d}"
    )
    history["year"] = history["year"].astype(np.int64)

    policy_lookup = {
        (item["province"].strip(), item["city"].strip()): (
            int(item["cohort_year"]),
            str(item["boundary_precision"]),
            str(item.get("pilot_area") or item["city"]),
        )
        for item in config["pilot_locations"]
    }
    all_cohorts = sorted({int(item["cohort_year"]) for item in config["pilot_locations"]})
    locations_by_cohort = {
        cohort: _last_pre_location(history, cohort) for cohort in all_cohorts
    }

    assigned_cohort: dict[str, int] = {}
    assigned_precision: dict[str, str] = {}
    assigned_pilot_area: dict[str, str] = {}
    for firm_id in sorted(joined["firm_id"].unique()):
        for cohort in all_cohorts:
            locations = locations_by_cohort[cohort]
            if firm_id not in locations.index:
                continue
            location = locations.loc[firm_id]
            match = policy_lookup.get(
                (str(location["provincename"]).strip(), str(location["cityname"]).strip())
            )
            if match is not None and match[0] == cohort:
                assigned_cohort[firm_id] = cohort
                assigned_precision[firm_id] = match[1]
                assigned_pilot_area[firm_id] = match[2]
                break

    pku = pku.rename(columns={"pref_name_year18": "cityname"})
    pku["cityname"] = pku["cityname"].astype(str).str.strip()
    pku["year"] = pku["year"].astype(np.int64)
    analysis = config["analysis"]
    controls = [str(value) for value in analysis["controls"]]
    numeric_required = [
        "greenwashing_gap",
        "firm_emission_intensity",
        "direct_firm_log_emissions",
        *controls,
    ]
    stacked_frames: list[pd.DataFrame] = []
    cohort_diagnostics: list[dict[str, Any]] = []

    for cohort in [int(value) for value in analysis["estimated_cohorts"]]:
        event_min = int(analysis["event_time_min"])
        event_max = int(analysis["event_time_max"])
        window_start = cohort + event_min
        window_end = min(cohort + event_max, int(joined["year"].max()))
        location = locations_by_cohort[cohort]
        capacity = (
            pku.loc[pku["year"].lt(cohort) & pku["index_aggregate"].notna()]
            .groupby("cityname", observed=True)
            .agg(
                prepolicy_digital_fintech_capacity=("index_aggregate", "mean"),
                capacity_year_count=("year", "nunique"),
                capacity_source_start_year=("year", "min"),
                capacity_source_end_year=("year", "max"),
                region_id=("pref_code_year18", "last"),
            )
        )
        metadata: list[dict[str, Any]] = []
        for firm_id in sorted(joined["firm_id"].unique()):
            treatment_cohort = assigned_cohort.get(firm_id)
            eligible = (
                treatment_cohort == cohort
                or treatment_cohort is None
                or treatment_cohort > window_end
            )
            if not eligible or firm_id not in location.index:
                continue
            location_row = location.loc[firm_id]
            city = str(location_row["cityname"]).strip()
            if city not in capacity.index:
                continue
            capacity_row = capacity.loc[city]
            if int(capacity_row["capacity_year_count"]) < int(
                analysis["minimum_capacity_years"]
            ):
                continue
            metadata.append(
                {
                    "firm_id": firm_id,
                    "treatment_cohort_year": treatment_cohort,
                    "assignment_city": city,
                    "assignment_province": str(location_row["provincename"]).strip(),
                    "region_id": int(capacity_row["region_id"]),
                    "prepolicy_digital_fintech_capacity": float(
                        capacity_row["prepolicy_digital_fintech_capacity"]
                    ),
                    "capacity_year_count": int(capacity_row["capacity_year_count"]),
                    "capacity_source_start_year": int(
                        capacity_row["capacity_source_start_year"]
                    ),
                    "capacity_source_end_year": int(
                        capacity_row["capacity_source_end_year"]
                    ),
                    "assignment_boundary_precision": assigned_precision.get(
                        firm_id, "control"
                    ),
                    "pilot_area": assigned_pilot_area.get(firm_id, ""),
                }
            )
        metadata_frame = pd.DataFrame(metadata)
        stack = joined.loc[
            joined["year"].between(window_start, window_end, inclusive="both")
        ].merge(metadata_frame, on="firm_id", how="inner", validate="many_to_one")
        stack = _finite_columns(stack, numeric_required)
        observation_counts = stack.groupby("firm_id", observed=True).agg(
            pre_observations=("year", lambda values: int(values.lt(cohort).sum())),
            post_observations=("year", lambda values: int(values.gt(cohort).sum())),
        )
        eligible_entities = observation_counts.loc[
            observation_counts["pre_observations"].ge(
                int(analysis["minimum_pre_observations"])
            )
            & observation_counts["post_observations"].ge(
                int(analysis["minimum_post_observations"])
            )
        ].index
        stack = stack.loc[stack["firm_id"].isin(eligible_entities)].copy()
        stack["stack_cohort_year"] = cohort
        stack["event_time"] = stack["year"] - cohort
        stack["transition_year"] = stack["event_time"].eq(0).astype(np.int64)
        stack["treated"] = stack["treatment_cohort_year"].eq(cohort).astype(np.int64)
        stack["post"] = stack["year"].gt(cohort).astype(np.int64)
        stack["gfripz_exposure"] = stack["treated"] * stack["post"]
        stack["stack_entity_id"] = (
            stack["stack_cohort_year"].astype(str) + ":" + stack["firm_id"]
        )
        stack["stack_time_id"] = (
            stack["stack_cohort_year"].astype(str)
            + ":"
            + stack["year"].astype(str)
        )
        stack["paired_outcome_complete"] = 1
        stack["source_greenwashing_sha256"] = sources["greenwashing"]["sha256"]
        stack["source_emissions_sha256"] = sources["firm_emissions"]["sha256"]
        stack["source_capacity_sha256"] = sources["digital_capacity"]["sha256"]
        treated_entities = stack.loc[stack["treated"].eq(1), "firm_id"].nunique()
        control_entities = stack.loc[stack["treated"].eq(0), "firm_id"].nunique()
        precision_counts = (
            stack.loc[stack["treated"].eq(1)]
            .drop_duplicates("firm_id")["assignment_boundary_precision"]
            .value_counts()
            .sort_index()
            .astype(int)
            .to_dict()
        )
        cohort_diagnostics.append(
            {
                "cohort_year": cohort,
                "rows": int(len(stack)),
                "entities": int(stack["firm_id"].nunique()),
                "treated_entities": int(treated_entities),
                "control_entities": int(control_entities),
                "boundary_precision_treated_entities": precision_counts,
                "observed_year_min": int(stack["year"].min()),
                "observed_year_max": int(stack["year"].max()),
                "scientific_minimum_treated_entities": int(
                    analysis["scientific_minimum_treated_entities_per_cohort"]
                ),
                "below_scientific_treated_entity_minimum": bool(
                    treated_entities
                    < int(analysis["scientific_minimum_treated_entities_per_cohort"])
                ),
            }
        )
        stacked_frames.append(stack)

    if not stacked_frames:
        raise ValueError("no cohort stack could be constructed")
    output = pd.concat(stacked_frames, ignore_index=True)
    output = output.sort_values(["stack_cohort_year", "firm_id", "year"]).reset_index(
        drop=True
    )
    if output.duplicated(["stack_cohort_year", "firm_id", "year"]).any():
        raise ValueError("derived stacked panel has duplicate stack-firm-year rows")
    if not output["capacity_source_end_year"].lt(output["stack_cohort_year"]).all():
        raise ValueError("capacity source window leaks into or past a treatment cohort")
    expected_exposure = output["treated"] * output["year"].gt(
        output["stack_cohort_year"]
    ).astype(np.int64)
    if not output["gfripz_exposure"].eq(expected_exposure).all():
        raise ValueError("derived GFRIPZ exposure violates the frozen transition rule")

    selected_columns = [
        "stack_cohort_year",
        "stack_entity_id",
        "stack_time_id",
        "firm_id",
        "year",
        "event_time",
        "transition_year",
        "treated",
        "post",
        "gfripz_exposure",
        "treatment_cohort_year",
        "region_id",
        "assignment_city",
        "assignment_province",
        "assignment_boundary_precision",
        "pilot_area",
        "prepolicy_digital_fintech_capacity",
        "capacity_year_count",
        "capacity_source_start_year",
        "capacity_source_end_year",
        "greenwashing_gap",
        "firm_emission_intensity",
        "direct_firm_log_emissions",
        "emission_intensity_denominator",
        "paired_outcome_complete",
        *controls,
        "source_greenwashing_sha256",
        "source_emissions_sha256",
        "source_capacity_sha256",
    ]
    output = output[selected_columns]
    runtime_root = Path(args.runtime_root)
    output_path = _safe_output(Path(args.output), runtime_root)
    manifest_path = _safe_output(Path(args.manifest), runtime_root)
    temporary_output = output_path.with_suffix(output_path.suffix + ".tmp")
    output.to_csv(temporary_output, index=False, encoding="utf-8", float_format="%.12g")
    os.replace(temporary_output, output_path)
    output_sha256 = _sha256(output_path)

    scientific_blockers: list[str] = []
    if any(
        item["below_scientific_treated_entity_minimum"] for item in cohort_diagnostics
    ):
        scientific_blockers.append(
            "At least one policy cohort is below the preregistered treated-entity minimum."
        )
    if any(
        item["boundary_precision_treated_entities"].get("prefecture_proxy", 0) > 0
        for item in cohort_diagnostics
    ):
        scientific_blockers.append(
            "Sub-prefecture pilot areas are represented by auditable prefecture proxies; "
            "firm-address boundary matching is required before a publishable causal claim."
        )
    scientific_blockers.extend(
        [
            "Third-party-content licensing must be reviewed before redistributing the joined panel.",
            "The revenue-scaled log-emissions construction must be confirmed against the source authors' exact carbon transformation before publication.",
        ]
    )
    manifest = {
        "schema_version": "group1-stacked-panel-manifest-v1",
        "source_config_sha256": _sha256(config_path),
        "source_files": {
            "greenwashing": sources["greenwashing"],
            "firm_emissions": sources["firm_emissions"],
            "digital_capacity": sources["digital_capacity"],
        },
        "join": {
            "key": ["stock_code", "year"],
            "greenwashing_rows": int(len(greenwashing)),
            "emissions_rows": int(len(emissions)),
            "paired_rows_before_stacking": int(len(joined)),
            "paired_firms_before_stacking": int(joined["firm_id"].nunique()),
        },
        "output": {
            "path": str(output_path),
            "filename": output_path.name,
            "sha256": output_sha256,
            "size_bytes": output_path.stat().st_size,
            "rows": int(len(output)),
            "columns": int(len(output.columns)),
            "stack_firm_year_key_unique": True,
            "paired_outcome_complete": True,
        },
        "cohorts": cohort_diagnostics,
        "transition_year_mode": analysis["transition_year_mode"],
        "capacity_timing_verified": True,
        "scientific_release_ready": False,
        "scientific_release_blockers": scientific_blockers,
    }
    temporary_manifest = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    temporary_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_manifest, manifest_path)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the immutable paired-outcome Group1 stacked policy panel."
    )
    parser.add_argument(
        "--config",
        default="backend/config/group1_execution_sources.json",
    )
    parser.add_argument(
        "--greenwashing-dta",
        default="backend/var/source_intake/mendeley_4yckzvjzcc_v1/Data.dta",
    )
    parser.add_argument(
        "--emissions-dta",
        default="backend/var/source_intake/mendeley_n8k6ss8hcg_v2/China listed firms with emissions.dta",
    )
    parser.add_argument(
        "--pku-workbook",
        default="backend/var/source_intake/pku_dfiic_2011_2023/PKU_DFIIC_2011_2023.xlsx",
    )
    parser.add_argument(
        "--pku-city-csv",
        default="backend/var/source_intake/pku_dfiic_2011_2023/Prefecture_Level_Cities.csv",
    )
    parser.add_argument(
        "--runtime-root",
        default="backend/var",
    )
    parser.add_argument(
        "--output",
        default="backend/var/group1_execution/group1_paired_stacked_panel.csv",
    )
    parser.add_argument(
        "--manifest",
        default="backend/var/group1_execution/group1_paired_stacked_panel.manifest.json",
    )
    return parser.parse_args()


if __name__ == "__main__":
    result = build(parse_args())
    print(json.dumps(result, ensure_ascii=False, indent=2))

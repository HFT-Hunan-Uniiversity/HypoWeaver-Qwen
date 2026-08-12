from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import pandas as pd
from linearmodels.iv import AbsorbingLS
from scipy.stats import chi2, norm

from .models import ModelSpec


GROUP1_STAGGERED_DDD_REGISTRY_VERSION = "group1-staggered-ddd-v1"
GROUP1_PRIMARY_IMPLEMENTATION_ID = "linearmodels-stacked-cohort-ddd-v1"
GROUP1_REPRODUCTION_IMPLEMENTATION_ID = "numpy-stacked-cohort-ddd-v1"

_DESIGN_REQUIRED_KEYS = frozenset(
    {
        "entity_field",
        "time_field",
        "stack_cohort_field",
        "assigned_cohort_field",
        "moderator_field",
        "moderator_source_end_field",
        "paired_outcomes",
        "treated_field",
        "exposure_field",
        "fixed_effects",
        "cluster_field",
        "transition_year_mode",
        "event_time_min",
        "event_time_max",
        "event_reference",
        "policy_term",
        "capacity_time_term",
        "policy_capacity_term",
        "scientific_minimum_treated_entities",
    }
)
_DESIGN_OPTIONAL_KEYS = frozenset(
    {
        "boundary_precision_field",
        "capacity_source_count_field",
        "engineering_minimum_treated_entities",
    }
)
_WITHIN_TOLERANCE = 1e-9
_WITHIN_MAX_ITERATIONS = 10_000


class Group1StaggeredDDDError(ValueError):
    """Base error for the frozen Group 1 stacked-cohort DDD contract."""


class Group1StaggeredDDDContractError(Group1StaggeredDDDError):
    """Raised before data are read when the model contract is malformed."""


class Group1StaggeredDDDEstimationError(Group1StaggeredDDDError):
    """Raised when the frozen panel cannot identify the requested estimand."""


@dataclass(frozen=True)
class Group1StaggeredDDDDesign:
    entity_field: str
    time_field: str
    stack_cohort_field: str
    assigned_cohort_field: str
    moderator_field: str
    moderator_source_end_field: str
    capacity_source_count_field: str | None
    paired_outcomes: tuple[str, ...]
    treated_field: str
    exposure_field: str
    fixed_effects: tuple[str, ...]
    cluster_field: str
    transition_year_mode: str
    event_time_min: int
    event_time_max: int
    event_reference: int
    policy_term: str
    capacity_time_term: str
    policy_capacity_term: str
    boundary_precision_field: str | None
    engineering_minimum_treated_entities: int
    scientific_minimum_treated_entities: int


@dataclass(frozen=True)
class _FitResult:
    estimates: tuple[dict[str, Any], ...]
    terms: tuple[str, ...]
    covariance: np.ndarray
    nobs: int
    diagnostics: Mapping[str, Any]


@dataclass(frozen=True)
class _PreparedData:
    baseline_frame: pd.DataFrame
    event_frame: pd.DataFrame
    design: Group1StaggeredDDDDesign
    diagnostics: Mapping[str, Any]
    treated_capacity_support: tuple[float, float]
    treated_capacity_quantiles: tuple[float, float]


def parse_group1_staggered_ddd_design(
    model: ModelSpec,
) -> Group1StaggeredDDDDesign:
    raw = model.parameters.get("staggered_ddd_design")
    if not isinstance(raw, dict):
        raise Group1StaggeredDDDContractError(
            "ModelSpec.parameters.staggered_ddd_design must be a dictionary."
        )
    keys = frozenset(raw)
    missing = sorted(_DESIGN_REQUIRED_KEYS - keys)
    unknown = sorted(keys - _DESIGN_REQUIRED_KEYS - _DESIGN_OPTIONAL_KEYS)
    if missing:
        raise Group1StaggeredDDDContractError(
            "staggered_ddd_design is missing required keys: " + ", ".join(missing)
        )
    if unknown:
        raise Group1StaggeredDDDContractError(
            "staggered_ddd_design contains unknown keys: " + ", ".join(unknown)
        )

    entity_field = _strict_name(raw["entity_field"], "entity_field")
    time_field = _strict_name(raw["time_field"], "time_field")
    stack_cohort_field = _strict_name(
        raw["stack_cohort_field"], "stack_cohort_field"
    )
    assigned_cohort_field = _strict_name(
        raw["assigned_cohort_field"], "assigned_cohort_field"
    )
    moderator_field = _strict_name(raw["moderator_field"], "moderator_field")
    moderator_source_end_field = _strict_name(
        raw["moderator_source_end_field"], "moderator_source_end_field"
    )
    capacity_source_count_field = (
        _strict_name(raw["capacity_source_count_field"], "capacity_source_count_field")
        if raw.get("capacity_source_count_field") is not None
        else None
    )
    paired_outcomes = _strict_name_list(raw["paired_outcomes"], "paired_outcomes")
    treated_field = _strict_name(raw["treated_field"], "treated_field")
    exposure_field = _strict_name(raw["exposure_field"], "exposure_field")
    fixed_effects = _strict_name_list(raw["fixed_effects"], "fixed_effects")
    cluster_field = _strict_name(raw["cluster_field"], "cluster_field")
    transition_year_mode = str(raw["transition_year_mode"])
    event_time_min = _strict_int(raw["event_time_min"], "event_time_min")
    event_time_max = _strict_int(raw["event_time_max"], "event_time_max")
    event_reference = _strict_int(raw["event_reference"], "event_reference")
    policy_term = _strict_name(raw["policy_term"], "policy_term")
    capacity_time_term = _strict_name(
        raw["capacity_time_term"], "capacity_time_term"
    )
    policy_capacity_term = _strict_name(
        raw["policy_capacity_term"], "policy_capacity_term"
    )
    boundary_precision_field = (
        _strict_name(raw["boundary_precision_field"], "boundary_precision_field")
        if raw.get("boundary_precision_field") is not None
        else None
    )
    engineering_minimum = _strict_int(
        raw.get("engineering_minimum_treated_entities", 1),
        "engineering_minimum_treated_entities",
    )
    scientific_minimum = _strict_int(
        raw["scientific_minimum_treated_entities"],
        "scientific_minimum_treated_entities",
    )

    if model.outcome not in paired_outcomes:
        raise Group1StaggeredDDDContractError(
            "ModelSpec.outcome must be one of staggered_ddd_design.paired_outcomes."
        )
    if len(paired_outcomes) != 2:
        raise Group1StaggeredDDDContractError(
            "Group 1 v1 requires exactly two paired outcomes."
        )
    if len(fixed_effects) != 2:
        raise Group1StaggeredDDDContractError(
            "Group 1 v1 requires stack-entity and stack-time fixed effects."
        )
    if tuple(model.fixed_effects) != fixed_effects:
        raise Group1StaggeredDDDContractError(
            "staggered_ddd_design.fixed_effects must match ModelSpec.fixed_effects."
        )
    if transition_year_mode != "exclude":
        raise Group1StaggeredDDDContractError(
            "Group 1 v1 requires transition_year_mode='exclude'."
        )
    if not event_time_min < event_reference < event_time_max:
        raise Group1StaggeredDDDContractError(
            "event_reference must be strictly inside the event-time window."
        )
    if event_reference != -1:
        raise Group1StaggeredDDDContractError(
            "Group 1 v1 freezes event_reference=-1."
        )
    if engineering_minimum < 1:
        raise Group1StaggeredDDDContractError(
            "engineering_minimum_treated_entities must be positive."
        )
    if scientific_minimum < engineering_minimum:
        raise Group1StaggeredDDDContractError(
            "scientific minimum cannot be below the engineering minimum."
        )
    if len({policy_term, capacity_time_term, policy_capacity_term}) != 3:
        raise Group1StaggeredDDDContractError(
            "the three derived baseline term names must be unique."
        )
    expected_targets = {policy_term, policy_capacity_term}
    if set(model.treatments_or_exposures) != expected_targets:
        raise Group1StaggeredDDDContractError(
            "ModelSpec.treatments_or_exposures must contain the frozen policy and DDD terms."
        )

    return Group1StaggeredDDDDesign(
        entity_field=entity_field,
        time_field=time_field,
        stack_cohort_field=stack_cohort_field,
        assigned_cohort_field=assigned_cohort_field,
        moderator_field=moderator_field,
        moderator_source_end_field=moderator_source_end_field,
        capacity_source_count_field=capacity_source_count_field,
        paired_outcomes=paired_outcomes,
        treated_field=treated_field,
        exposure_field=exposure_field,
        fixed_effects=fixed_effects,
        cluster_field=cluster_field,
        transition_year_mode=transition_year_mode,
        event_time_min=event_time_min,
        event_time_max=event_time_max,
        event_reference=event_reference,
        policy_term=policy_term,
        capacity_time_term=capacity_time_term,
        policy_capacity_term=policy_capacity_term,
        boundary_precision_field=boundary_precision_field,
        engineering_minimum_treated_entities=engineering_minimum,
        scientific_minimum_treated_entities=scientific_minimum,
    )


def estimate_group1_staggered_ddd(path: Path, model: ModelSpec) -> dict[str, Any]:
    return _estimate(
        Path(path),
        model,
        implementation_id=GROUP1_PRIMARY_IMPLEMENTATION_ID,
        fitter=_fit_absorbing_ls,
    )


def reproduce_group1_staggered_ddd(path: Path, model: ModelSpec) -> dict[str, Any]:
    return _estimate(
        Path(path),
        model,
        implementation_id=GROUP1_REPRODUCTION_IMPLEMENTATION_ID,
        fitter=_fit_numpy_within,
    )


def inspect_group1_staggered_support(path: Path, model: ModelSpec) -> dict[str, Any]:
    design = parse_group1_staggered_ddd_design(model)
    return dict(_prepare_data(Path(path), model, design).diagnostics)


def _estimate(
    path: Path,
    model: ModelSpec,
    *,
    implementation_id: str,
    fitter: Callable[[pd.DataFrame, Group1StaggeredDDDDesign, str, Sequence[str]], _FitResult],
) -> dict[str, Any]:
    design = parse_group1_staggered_ddd_design(model)
    prepared = _prepare_data(path, model, design)
    baseline_terms = [
        design.policy_term,
        design.capacity_time_term,
        design.policy_capacity_term,
        *model.controls,
    ]
    baseline = fitter(
        prepared.baseline_frame,
        design,
        model.outcome or "",
        baseline_terms,
    )
    for target in (design.policy_term, design.policy_capacity_term):
        if target not in baseline.terms:
            raise Group1StaggeredDDDEstimationError(
                f"frozen target term {target!r} is absorbed or collinear."
            )
    event_study = _event_study(prepared, model, fitter)
    marginal_effects = _marginal_effects(prepared, baseline)
    return {
        "implementation_id": implementation_id,
        "outcome": model.outcome,
        "estimates": list(baseline.estimates),
        "event_study": event_study,
        "marginal_effects": marginal_effects,
        "diagnostics": {
            **prepared.diagnostics,
            "outcome": model.outcome,
            "fixed_effects": list(design.fixed_effects),
            "cluster_field": design.cluster_field,
            "fit_diagnostics": dict(baseline.diagnostics),
        },
    }


def _prepare_data(
    path: Path,
    model: ModelSpec,
    design: Group1StaggeredDDDDesign,
) -> _PreparedData:
    if not path.is_file():
        raise Group1StaggeredDDDEstimationError(f"stacked panel CSV does not exist: {path}")
    required = list(
        dict.fromkeys(
            [
                design.entity_field,
                design.time_field,
                design.stack_cohort_field,
                design.assigned_cohort_field,
                design.moderator_field,
                design.moderator_source_end_field,
                design.treated_field,
                design.exposure_field,
                *design.paired_outcomes,
                *design.fixed_effects,
                design.cluster_field,
                *model.controls,
                *(
                    [design.capacity_source_count_field]
                    if design.capacity_source_count_field is not None
                    else []
                ),
                *(
                    [design.boundary_precision_field]
                    if design.boundary_precision_field is not None
                    else []
                ),
            ]
        )
    )
    frame = _read_csv(path, required)
    missing = [field for field in required if field not in frame]
    if missing:
        raise Group1StaggeredDDDEstimationError(
            "data are missing frozen Group 1 fields: " + ", ".join(missing)
        )
    rows_input = len(frame)
    numeric = [
        design.time_field,
        design.stack_cohort_field,
        design.assigned_cohort_field,
        design.moderator_field,
        design.moderator_source_end_field,
        design.treated_field,
        design.exposure_field,
        *design.paired_outcomes,
        *model.controls,
        *(
            [design.capacity_source_count_field]
            if design.capacity_source_count_field is not None
            else []
        ),
    ]
    for field in numeric:
        frame[field] = pd.to_numeric(frame[field], errors="coerce")
    complete_required = [field for field in required if field != design.assigned_cohort_field]
    frame = frame.dropna(subset=complete_required).copy()
    if frame.empty:
        raise Group1StaggeredDDDEstimationError("no complete paired observations remain.")
    finite_fields = [
        design.time_field,
        design.stack_cohort_field,
        design.moderator_field,
        design.moderator_source_end_field,
        design.treated_field,
        design.exposure_field,
        *design.paired_outcomes,
        *model.controls,
    ]
    finite_mask = np.isfinite(frame[finite_fields].to_numpy(dtype=float)).all(axis=1)
    frame = frame.loc[finite_mask].copy()
    if frame.empty:
        raise Group1StaggeredDDDEstimationError("no finite paired observations remain.")

    for field in (design.time_field, design.stack_cohort_field):
        values = frame[field].to_numpy(dtype=float)
        if not np.equal(values, np.floor(values)).all():
            raise Group1StaggeredDDDEstimationError(f"{field} must contain integer years.")
        frame[field] = values.astype(np.int64)
    assigned = frame[design.assigned_cohort_field]
    assigned_nonmissing = assigned.dropna().to_numpy(dtype=float)
    if not np.equal(assigned_nonmissing, np.floor(assigned_nonmissing)).all():
        raise Group1StaggeredDDDEstimationError(
            "assigned treatment cohorts must be integer years or missing."
        )
    duplicate_rows = int(
        frame.duplicated(
            [design.stack_cohort_field, design.entity_field, design.time_field],
            keep=False,
        ).sum()
    )
    if duplicate_rows:
        raise Group1StaggeredDDDEstimationError(
            f"stack-cohort/entity/time key contains {duplicate_rows} duplicate rows."
        )
    if not frame[design.moderator_source_end_field].lt(
        frame[design.stack_cohort_field]
    ).all():
        raise Group1StaggeredDDDEstimationError(
            "moderator source end year must be strictly before every stack cohort."
        )
    invalid_treated = sorted(
        set(frame[design.treated_field].unique()) - {0.0, 1.0}
    )
    invalid_exposure = sorted(
        set(frame[design.exposure_field].unique()) - {0.0, 1.0}
    )
    if invalid_treated or invalid_exposure:
        raise Group1StaggeredDDDEstimationError(
            "treated and exposure fields must contain only 0 and 1."
        )
    expected_treated = frame[design.assigned_cohort_field].eq(
        frame[design.stack_cohort_field]
    ).astype(float)
    expected_exposure = expected_treated * frame[design.time_field].gt(
        frame[design.stack_cohort_field]
    ).astype(float)
    if not frame[design.treated_field].eq(expected_treated).all():
        raise Group1StaggeredDDDEstimationError(
            "treated field disagrees with assigned and stack cohorts."
        )
    if not frame[design.exposure_field].eq(expected_exposure).all():
        raise Group1StaggeredDDDEstimationError(
            "exposure field disagrees with the frozen post-adoption transition rule."
        )

    frame["__event_time"] = (
        frame[design.time_field] - frame[design.stack_cohort_field]
    )
    if not frame["__event_time"].between(
        design.event_time_min, design.event_time_max, inclusive="both"
    ).all():
        raise Group1StaggeredDDDEstimationError(
            "source rows fall outside the frozen event-time window."
        )
    entity_stack = [design.stack_cohort_field, design.entity_field]
    constant_fields = [
        design.assigned_cohort_field,
        design.moderator_field,
        design.moderator_source_end_field,
    ]
    for field in constant_fields:
        if frame.groupby(entity_stack, observed=True)[field].nunique(dropna=False).gt(1).any():
            raise Group1StaggeredDDDEstimationError(
                f"{field} changes within a frozen stack entity."
            )
    stack_end = frame.groupby(design.stack_cohort_field, observed=True)[
        design.time_field
    ].max()
    controls = frame.loc[expected_treated.eq(0)].copy()
    control_end = controls[design.stack_cohort_field].map(stack_end)
    contaminated = controls[design.assigned_cohort_field].notna() & controls[
        design.assigned_cohort_field
    ].le(control_end)
    if contaminated.any():
        raise Group1StaggeredDDDEstimationError(
            "comparison rows include units treated inside the frozen stack window."
        )

    entity_capacity = frame.drop_duplicates(entity_stack)[
        [design.stack_cohort_field, design.entity_field, design.moderator_field]
    ].copy()
    capacity_stats = entity_capacity.groupby(
        design.stack_cohort_field, observed=True
    )[design.moderator_field].agg(["mean", "std"])
    if capacity_stats["std"].isna().any() or capacity_stats["std"].le(0).any():
        raise Group1StaggeredDDDEstimationError(
            "each cohort stack requires non-zero moderator variation."
        )
    means = frame[design.stack_cohort_field].map(capacity_stats["mean"])
    stds = frame[design.stack_cohort_field].map(capacity_stats["std"])
    frame["__capacity_z"] = (frame[design.moderator_field] - means) / stds
    frame["__post"] = frame[design.time_field].gt(
        frame[design.stack_cohort_field]
    ).astype(float)
    frame[design.policy_term] = frame[design.exposure_field].astype(float)
    frame[design.capacity_time_term] = frame["__post"] * frame["__capacity_z"]
    frame[design.policy_capacity_term] = (
        frame[design.exposure_field].astype(float) * frame["__capacity_z"]
    )

    treated_entities = frame.loc[frame[design.treated_field].eq(1)].drop_duplicates(
        entity_stack
    )
    treated_capacity = treated_entities["__capacity_z"].to_numpy(dtype=float)
    if treated_capacity.size < 1:
        raise Group1StaggeredDDDEstimationError("no treated stack entities remain.")
    treated_counts = (
        treated_entities.groupby(design.stack_cohort_field, observed=True)[
            design.entity_field
        ]
        .nunique()
        .sort_index()
    )
    control_counts = (
        frame.loc[frame[design.treated_field].eq(0)]
        .drop_duplicates(entity_stack)
        .groupby(design.stack_cohort_field, observed=True)[design.entity_field]
        .nunique()
        .sort_index()
    )
    below_engineering = [
        int(cohort)
        for cohort, count in treated_counts.items()
        if int(count) < design.engineering_minimum_treated_entities
    ]
    if below_engineering:
        raise Group1StaggeredDDDEstimationError(
            "cohorts below the engineering treated-entity minimum: "
            + ", ".join(map(str, below_engineering))
        )
    below_scientific = [
        int(cohort)
        for cohort, count in treated_counts.items()
        if int(count) < design.scientific_minimum_treated_entities
    ]
    boundary_counts: dict[str, int] = {}
    if design.boundary_precision_field is not None:
        boundary_counts = {
            str(label): int(count)
            for label, count in treated_entities[
                design.boundary_precision_field
            ].value_counts().sort_index().items()
        }
    baseline_frame = frame.loc[frame["__event_time"].ne(0)].copy().reset_index(
        drop=True
    )
    event_frame = frame.copy().reset_index(drop=True)
    if baseline_frame.empty:
        raise Group1StaggeredDDDEstimationError(
            "transition-year exclusion leaves no baseline rows."
        )
    cluster_count = int(baseline_frame[design.cluster_field].nunique())
    if cluster_count < 2:
        raise Group1StaggeredDDDEstimationError(
            "firm-clustered inference requires at least two clusters."
        )
    stack_rows = {
        str(int(cohort)): int(count)
        for cohort, count in frame[design.stack_cohort_field]
        .value_counts()
        .sort_index()
        .items()
    }
    diagnostics = {
        "rows_input": rows_input,
        "rows_pair_complete": int(len(frame)),
        "rows_used": int(len(baseline_frame)),
        "rows_transition_excluded": int(frame["__event_time"].eq(0).sum()),
        "duplicate_stack_entity_time_rows": duplicate_rows,
        "paired_outcomes": list(design.paired_outcomes),
        "paired_outcome_sample_identical": True,
        "stack_cohorts": [int(value) for value in sorted(frame[design.stack_cohort_field].unique())],
        "stack_row_counts": stack_rows,
        "treated_entities_by_cohort": {
            str(int(key)): int(value) for key, value in treated_counts.items()
        },
        "control_entities_by_cohort": {
            str(int(key)): int(value) for key, value in control_counts.items()
        },
        "cohorts_below_scientific_treated_entity_minimum": below_scientific,
        "scientific_treated_entity_minimum": design.scientific_minimum_treated_entities,
        "boundary_precision_treated_entities": boundary_counts,
        "prefecture_proxy_treated_entities": int(
            boundary_counts.get("prefecture_proxy", 0)
        ),
        "capacity_source_end_max_by_cohort": {
            str(int(key)): int(value)
            for key, value in frame.groupby(
                design.stack_cohort_field, observed=True
            )[design.moderator_source_end_field].max().items()
        },
        "capacity_timing_verified": True,
        "capacity_standardization": "entity_weighted_within_stack_prepolicy",
        "event_time_min": design.event_time_min,
        "event_time_max": design.event_time_max,
        "event_reference": design.event_reference,
        "transition_year_mode": design.transition_year_mode,
        "cluster_count": cluster_count,
        "cluster_field": design.cluster_field,
        "comparison_group": "not_yet_treated_through_stack_end_or_never_treated",
        "scientific_release_ready": not below_scientific
        and boundary_counts.get("prefecture_proxy", 0) == 0,
    }
    return _PreparedData(
        baseline_frame=baseline_frame,
        event_frame=event_frame,
        design=design,
        diagnostics=diagnostics,
        treated_capacity_support=(
            float(np.min(treated_capacity)),
            float(np.max(treated_capacity)),
        ),
        treated_capacity_quantiles=(
            float(np.quantile(treated_capacity, 0.25)),
            float(np.quantile(treated_capacity, 0.75)),
        ),
    )


def _event_study(
    prepared: _PreparedData,
    model: ModelSpec,
    fitter: Callable[[pd.DataFrame, Group1StaggeredDDDDesign, str, Sequence[str]], _FitResult],
) -> dict[str, Any]:
    frame = prepared.event_frame.copy()
    design = prepared.design
    main_terms: list[str] = []
    interaction_terms: list[str] = []
    common_terms: list[str] = []
    for event_time in range(design.event_time_min, design.event_time_max + 1):
        if event_time == design.event_reference:
            continue
        label = _event_label(event_time)
        indicator = frame["__event_time"].eq(event_time).astype(float)
        common = f"capacity_event_{label}"
        main = f"treated_event_{label}"
        interaction = f"treated_event_{label}_x_capacity"
        frame[common] = indicator * frame["__capacity_z"]
        frame[main] = indicator * frame[design.treated_field]
        frame[interaction] = frame[main] * frame["__capacity_z"]
        common_terms.append(common)
        main_terms.append(main)
        interaction_terms.append(interaction)
    fit = fitter(
        frame,
        design,
        model.outcome or "",
        [*common_terms, *main_terms, *interaction_terms, *model.controls],
    )
    target_terms = set(main_terms + interaction_terms)
    estimates = [item for item in fit.estimates if item["term"] in target_terms]
    pre_terms = [
        term
        for event_time, main, interaction in zip(
            [
                value
                for value in range(design.event_time_min, design.event_time_max + 1)
                if value != design.event_reference
            ],
            main_terms,
            interaction_terms,
            strict=True,
        )
        if event_time < design.event_reference
        for term in (main, interaction)
    ]
    return {
        "status": "succeeded",
        "reference_event_time": design.event_reference,
        "estimates": estimates,
        "joint_pretrend": _joint_zero_test(fit, pre_terms),
        "requested_terms": main_terms + interaction_terms,
        "dropped_terms": [
            term for term in main_terms + interaction_terms if term not in fit.terms
        ],
        "fit_diagnostics": dict(fit.diagnostics),
    }


def _marginal_effects(
    prepared: _PreparedData,
    fit: _FitResult,
) -> dict[str, Any]:
    design = prepared.design
    policy_index = fit.terms.index(design.policy_term)
    interaction_index = fit.terms.index(design.policy_capacity_term)
    coefficient_map = {
        str(item["term"]): float(item["coefficient"]) for item in fit.estimates
    }
    beta_policy = coefficient_map[design.policy_term]
    beta_interaction = coefficient_map[design.policy_capacity_term]
    covariance = fit.covariance[
        np.ix_([policy_index, interaction_index], [policy_index, interaction_index])
    ]

    def effect(label: str, capacity_z: float) -> dict[str, Any]:
        contrast = np.asarray([1.0, capacity_z], dtype=float)
        estimate = float(beta_policy + beta_interaction * capacity_z)
        variance = float(contrast @ covariance @ contrast)
        standard_error = float(np.sqrt(max(variance, 0.0)))
        return {
            "label": label,
            "capacity_z": float(capacity_z),
            **_estimate_record(
                "marginal_policy_effect",
                estimate,
                standard_error,
                fit.nobs,
            ),
        }

    low, high = prepared.treated_capacity_quantiles
    support_low, support_high = prepared.treated_capacity_support
    zero_crossing = None
    if abs(beta_interaction) > np.finfo(float).eps:
        value = float(-beta_policy / beta_interaction)
        zero_crossing = {
            "capacity_z": value,
            "inside_treated_support": bool(support_low <= value <= support_high),
        }
    return {
        "capacity_scale": "within-stack standardized strict pre-policy PKU index",
        "treated_capacity_support_z": [support_low, support_high],
        "low_capacity": effect("treated_q25", low),
        "high_capacity": effect("treated_q75", high),
        "zero_crossing": zero_crossing,
    }


def _fit_absorbing_ls(
    frame: pd.DataFrame,
    design: Group1StaggeredDDDDesign,
    outcome: str,
    terms: Sequence[str],
) -> _FitResult:
    absorb = pd.DataFrame(index=frame.index)
    for field in design.fixed_effects:
        absorb[field] = pd.Categorical(frame[field])
    clusters, _ = pd.factorize(frame[design.cluster_field], sort=True)
    try:
        result = AbsorbingLS(
            frame[outcome].astype(float),
            frame[list(terms)].astype(float),
            absorb=absorb,
            drop_absorbed=True,
        ).fit(
            cov_type="clustered",
            clusters=pd.Series(clusters, index=frame.index),
            debiased=True,
            method="hdfe",
            absorb_options={
                "compute_degrees": False,
                "residualize_method": "map",
                "options": {
                    "transform": "symmetric",
                    "acceleration": "cg",
                    "tol": _WITHIN_TOLERANCE,
                    "iteration_limit": _WITHIN_MAX_ITERATIONS,
                },
            },
            use_cache=True,
        )
    except Exception as error:
        raise Group1StaggeredDDDEstimationError(
            f"AbsorbingLS stacked DDD failed: {error}"
        ) from error
    kept_terms = tuple(str(value) for value in result.params.index)
    if not kept_terms:
        raise Group1StaggeredDDDEstimationError("all stacked DDD regressors were absorbed.")
    covariance = np.asarray(
        result.cov.loc[list(kept_terms), list(kept_terms)], dtype=float
    )
    absorbed_degrees = _absorbed_degrees(frame, design.fixed_effects)
    residual_degrees = int(result.nobs) - len(kept_terms) - absorbed_degrees
    if residual_degrees <= 0:
        raise Group1StaggeredDDDEstimationError(
            "absorbed effects exhaust residual degrees of freedom."
        )
    absorbed_df_correction = (int(result.nobs) - len(kept_terms)) / residual_degrees
    covariance *= absorbed_df_correction
    standard_errors = np.sqrt(np.clip(np.diag(covariance), 0.0, np.inf))
    return _FitResult(
        estimates=tuple(
            _estimate_record(
                term,
                float(result.params[term]),
                float(standard_errors[index]),
                int(result.nobs),
            )
            for index, term in enumerate(kept_terms)
        ),
        terms=kept_terms,
        covariance=covariance,
        nobs=int(result.nobs),
        diagnostics={
            "absorbed_effects": list(design.fixed_effects),
            "absorbed_degrees_of_freedom": absorbed_degrees,
            "absorbed_df_correction": absorbed_df_correction,
            "cluster_count": int(np.unique(clusters).size),
            "covariance": "firm_clustered_debiased",
            "dropped_terms": [term for term in terms if term not in kept_terms],
            "residual_degrees_of_freedom": residual_degrees,
        },
    )


def _fit_numpy_within(
    frame: pd.DataFrame,
    design: Group1StaggeredDDDDesign,
    outcome: str,
    terms: Sequence[str],
) -> _FitResult:
    values = np.column_stack(
        [frame[outcome].to_numpy(dtype=float)]
        + [frame[term].to_numpy(dtype=float) for term in terms]
    )
    fixed_effect_codes = [
        pd.factorize(frame[field], sort=True)[0].astype(np.int64)
        for field in design.fixed_effects
    ]
    within, iterations = _alternating_multiway_demean(values, fixed_effect_codes)
    y = within[:, 0]
    x_all = within[:, 1:]
    kept_indexes = _independent_columns(x_all)
    if not kept_indexes:
        raise Group1StaggeredDDDEstimationError("all stacked DDD regressors were absorbed.")
    kept_terms = tuple(terms[index] for index in kept_indexes)
    x = x_all[:, kept_indexes]
    coefficients = np.linalg.lstsq(x, y, rcond=None)[0]
    residuals = y - x @ coefficients
    clusters, _ = pd.factorize(frame[design.cluster_field], sort=True)
    covariance = _clustered_covariance(x, residuals, clusters.astype(np.int64))
    absorbed_degrees = _absorbed_degrees(frame, design.fixed_effects)
    residual_degrees = len(frame) - len(kept_terms) - absorbed_degrees
    if residual_degrees <= 0:
        raise Group1StaggeredDDDEstimationError(
            "absorbed effects exhaust residual degrees of freedom."
        )
    absorbed_df_correction = (len(frame) - len(kept_terms)) / residual_degrees
    covariance *= absorbed_df_correction
    standard_errors = np.sqrt(np.clip(np.diag(covariance), 0.0, np.inf))
    return _FitResult(
        estimates=tuple(
            _estimate_record(
                term,
                float(coefficients[index]),
                float(standard_errors[index]),
                len(frame),
            )
            for index, term in enumerate(kept_terms)
        ),
        terms=kept_terms,
        covariance=covariance,
        nobs=len(frame),
        diagnostics={
            "absorbed_effects": list(design.fixed_effects),
            "absorbed_degrees_of_freedom": absorbed_degrees,
            "absorbed_df_correction": absorbed_df_correction,
            "within_iterations": iterations,
            "cluster_count": int(np.unique(clusters).size),
            "covariance": "manual_firm_cluster_finite_sample",
            "dropped_terms": [
                term for index, term in enumerate(terms) if index not in kept_indexes
            ],
            "residual_degrees_of_freedom": residual_degrees,
        },
    )


def _joint_zero_test(fit: _FitResult, requested: Sequence[str]) -> dict[str, Any]:
    available = [term for term in requested if term in fit.terms]
    unavailable = [term for term in requested if term not in fit.terms]
    if not available:
        return {
            "status": "not_testable",
            "reason": "no requested pre-policy event term is estimable",
            "terms": [],
            "unavailable_terms": unavailable,
        }
    indexes = [fit.terms.index(term) for term in available]
    coefficient_map = {
        str(item["term"]): float(item["coefficient"]) for item in fit.estimates
    }
    coefficients = np.asarray([coefficient_map[term] for term in available])
    covariance = fit.covariance[np.ix_(indexes, indexes)]
    degrees = int(np.linalg.matrix_rank(covariance))
    if degrees < 1:
        return {
            "status": "not_testable",
            "reason": "pre-policy covariance has zero rank",
            "terms": available,
            "unavailable_terms": unavailable,
        }
    statistic = float(coefficients.T @ np.linalg.pinv(covariance) @ coefficients)
    return {
        "status": "tested" if not unavailable else "partially_tested",
        "null_hypothesis": "all estimable pre-policy main and capacity-slope terms equal zero",
        "terms": available,
        "unavailable_terms": unavailable,
        "statistic": statistic,
        "degrees_of_freedom": degrees,
        "p_value": float(chi2.sf(statistic, degrees)),
    }


def _absorbed_degrees(frame: pd.DataFrame, fixed_effects: Sequence[str]) -> int:
    levels = sum(int(frame[field].nunique()) for field in fixed_effects)
    return levels - (len(fixed_effects) - 1)


def _alternating_multiway_demean(
    values: np.ndarray,
    fixed_effect_codes: Sequence[np.ndarray],
) -> tuple[np.ndarray, int]:
    current = np.asarray(values, dtype=float).copy()
    for iteration in range(1, _WITHIN_MAX_ITERATIONS + 1):
        previous = current.copy()
        for codes in fixed_effect_codes:
            current = _group_demean(current, codes)
        if float(np.max(np.abs(current - previous))) <= _WITHIN_TOLERANCE:
            return current, iteration
    raise Group1StaggeredDDDEstimationError(
        f"multi-way within transform did not converge in {_WITHIN_MAX_ITERATIONS} iterations."
    )


def _group_demean(values: np.ndarray, codes: np.ndarray) -> np.ndarray:
    group_count = int(codes.max()) + 1
    counts = np.bincount(codes, minlength=group_count).astype(float)
    totals = np.zeros((group_count, values.shape[1]), dtype=float)
    np.add.at(totals, codes, values)
    return values - totals[codes] / counts[codes, None]


def _independent_columns(values: np.ndarray) -> list[int]:
    kept: list[int] = []
    current_rank = 0
    for index in range(values.shape[1]):
        candidate = values[:, [*kept, index]]
        rank = int(np.linalg.matrix_rank(candidate))
        if rank > current_rank:
            kept.append(index)
            current_rank = rank
    return kept


def _clustered_covariance(
    x: np.ndarray,
    residuals: np.ndarray,
    cluster_codes: np.ndarray,
) -> np.ndarray:
    nobs, nvar = x.shape
    groups = np.unique(cluster_codes)
    if len(groups) <= 1 or nobs <= nvar:
        raise Group1StaggeredDDDEstimationError(
            "too little support for manual firm-clustered covariance."
        )
    bread = np.linalg.pinv(x.T @ x)
    scores = x * residuals[:, None]
    group_scores = np.zeros((len(groups), nvar), dtype=float)
    np.add.at(group_scores, cluster_codes, scores)
    meat = group_scores.T @ group_scores
    correction = (len(groups) / (len(groups) - 1)) * ((nobs - 1) / (nobs - nvar))
    covariance = bread @ meat @ bread * correction
    return (covariance + covariance.T) / 2


def _estimate_record(
    term: str,
    coefficient: float,
    standard_error: float,
    nobs: int,
) -> dict[str, Any]:
    if standard_error > 0 and np.isfinite(standard_error):
        statistic = coefficient / standard_error
        p_value = float(2 * norm.sf(abs(statistic)))
        interval = [
            float(coefficient - 1.959963984540054 * standard_error),
            float(coefficient + 1.959963984540054 * standard_error),
        ]
    else:
        statistic = None
        p_value = None
        interval = [None, None]
    return {
        "term": term,
        "coefficient": float(coefficient),
        "standard_error": float(standard_error),
        "t_statistic": None if statistic is None else float(statistic),
        "p_value": p_value,
        "confidence_interval_95": interval,
        "nobs": int(nobs),
    }


def _read_csv(path: Path, required: Sequence[str]) -> pd.DataFrame:
    last_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return pd.read_csv(
                path,
                encoding=encoding,
                usecols=lambda name: name in required,
                dtype={"firm_id": "string"},
            )
        except UnicodeDecodeError as error:
            last_error = error
    raise Group1StaggeredDDDEstimationError(
        "stacked panel CSV must be UTF-8 or GB18030."
    ) from last_error


def _event_label(value: int) -> str:
    return f"m{abs(value)}" if value < 0 else f"p{value}"


def _strict_name(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Group1StaggeredDDDContractError(f"{field} must be a non-empty string.")
    return value.strip()


def _strict_name_list(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise Group1StaggeredDDDContractError(f"{field} must be a non-empty list.")
    result = tuple(_strict_name(item, field) for item in value)
    if len(result) != len(set(result)):
        raise Group1StaggeredDDDContractError(f"{field} must contain unique names.")
    return result


def _strict_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise Group1StaggeredDDDContractError(f"{field} must be an integer.")
    return value

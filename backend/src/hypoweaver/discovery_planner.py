"""Qwen planning and deterministic compilation for online discovery."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import Field

from .adapters import QwenModelGateway
from .discovery_bridge import evidence_bundle_to_research_graph
from .discovery_pipeline import (
    DiscoveryBuildRequest,
    DiscoveryReleasePreview,
    ReviewedGraphPatch,
    build_discovery_release_preview,
)
from .knowledge_models import EvidenceBundle, KnowledgeSearchRequest
from .knowledge_client import KnowledgeClient
from .models import (
    CompiledDatasetCandidate,
    CompiledIdentificationStrategy,
    CompiledVariableDictionaryEntry,
    DiscoveryConstructDraft,
    DiscoveryDatasetResource,
    DiscoveryEntityDraft,
    DiscoveryExecutionReadiness,
    DiscoveryPlan,
    QuestionPlanConsistencyReview,
    StrictModel,
)


MAX_PLANNER_EVIDENCE_HITS = 20
MAX_PLANNER_CHARS_PER_HIT = 8_000


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


class DiscoveryResearcherContext(StrictModel):
    goal: str = Field(default="", max_length=4000)
    unit_of_analysis: str = Field(default="", max_length=500)
    sample_period: str = Field(default="", max_length=500)
    constraints: list[str] = Field(default_factory=list, max_length=30)
    dataset_resources: list[DiscoveryDatasetResource] = Field(
        default_factory=list,
        max_length=20,
    )


class DiscoveryConsistencyRepairDirective(StrictModel):
    """Bounded Reviewer feedback supplied only to the second planning round."""

    schema_version: Literal["discovery-consistency-repair/1.0.0"] = (
        "discovery-consistency-repair/1.0.0"
    )
    original_question: str = Field(min_length=2, max_length=4000)
    missing_concepts: list[str] = Field(min_length=1, max_length=20)
    requery_terms: list[str] = Field(min_length=1, max_length=20)
    reviewer_rationale: str = Field(min_length=10, max_length=4000)
    previous_candidate_research_question: str = Field(min_length=5, max_length=4000)
    previous_hypothesis_statement: str = Field(min_length=10, max_length=4000)
    previous_construct_labels: list[str] = Field(min_length=2, max_length=30)
    instruction: Literal[
        "rewrite_primary_plan_preserving_original_exposure_outcome_and_qualifiers"
    ] = "rewrite_primary_plan_preserving_original_exposure_outcome_and_qualifiers"


class DiscoveryPlanGenerationRequest(StrictModel):
    search: KnowledgeSearchRequest
    context: DiscoveryResearcherContext = Field(
        default_factory=DiscoveryResearcherContext
    )
    experiment_seed: int | None = Field(default=None, ge=0, le=2_147_483_647)
    temperature: float = Field(default=0.0, ge=0.0, lt=2.0)


class DiscoveryRetrievalRound(StrictModel):
    round_index: int = Field(ge=1, le=2)
    query: str
    bundle_id: str
    evidence_hit_count: int = Field(ge=0)
    unique_document_count: int = Field(ge=0)
    diversity_gate_passed: bool
    candidate_research_question: str = ""
    hypothesis_statement: str = ""
    construct_labels: list[str] = Field(default_factory=list, max_length=30)
    consistency_decision: Literal["pass", "requery"] | None = None
    repair_feedback_applied: bool = False
    repair_directive_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )


class DiscoveryPlanGeneration(StrictModel):
    schema_version: str = "discovery-plan-generation/1.2.0"
    original_question: str = "legacy-unspecified"
    evidence_bundle: EvidenceBundle
    plan: DiscoveryPlan
    model_usage: dict[str, Any]
    consistency_reviews: list[QuestionPlanConsistencyReview] = Field(
        default_factory=list,
        max_length=2,
    )
    retrieval_rounds: list[DiscoveryRetrievalRound] = Field(
        default_factory=list,
        max_length=2,
    )
    repair_count: int = Field(default=0, ge=0, le=1)
    final_consistency_passed: bool = False
    execution_readiness: DiscoveryExecutionReadiness | None = None
    warnings: list[str] = Field(default_factory=list)


class DiscoveryPlanReviewRequest(StrictModel):
    evidence_bundle: EvidenceBundle
    plan: DiscoveryPlan
    consistency_review: QuestionPlanConsistencyReview | None = None
    execution_readiness: DiscoveryExecutionReadiness | None = None
    review_note: str = Field(min_length=10, max_length=4000)


class DiscoveryPlanLaunchRequest(DiscoveryPlanReviewRequest):
    approve_h0: Literal[True]
    approval_reason: str = Field(min_length=10, max_length=4000)
    mode: Literal["research", "fixture"] = "research"
    research_model_provider: Literal["qwen", "code_owned"] = "code_owned"


def _planner_payload(
    bundle: EvidenceBundle,
    context: DiscoveryResearcherContext,
    consistency_repair: DiscoveryConsistencyRepairDirective | None = None,
) -> dict[str, Any]:
    hits = []
    for hit in bundle.evidence_hits[:MAX_PLANNER_EVIDENCE_HITS]:
        hits.append(
            {
                "document_id": hit.document_id,
                "chunk_id": hit.chunk_id,
                "title": hit.title,
                "text_excerpt": hit.text[:MAX_PLANNER_CHARS_PER_HIT],
                "content_sha256": hit.content_sha256,
                "source_locator": hit.source_locator.model_dump(mode="json"),
                "publication_year": hit.publication_year,
                "evidence_status": hit.evidence_status,
            }
        )
    payload = {
        "question": bundle.question,
        "as_of": bundle.as_of.isoformat(),
        "corpus_snapshot_id": bundle.corpus_snapshot_id,
        "researcher_context": context.model_dump(mode="json"),
        "evidence_hits": hits,
        "rag_graph_candidates": [
            edge.model_dump(mode="json") for edge in bundle.graph_edges[:50]
        ],
        "corpus_warnings": bundle.warnings,
        "planner_limits": {
            "evidence_hit_count": len(hits),
            "max_chars_per_hit": MAX_PLANNER_CHARS_PER_HIT,
            "rag_graph_is_non_authoritative": True,
        },
    }
    if consistency_repair is not None:
        payload["consistency_repair"] = consistency_repair.model_dump(mode="json")
    return payload


def _plan_chunk_ids(plan: DiscoveryPlan) -> set[str]:
    result: set[str] = set()
    for collection in (
        plan.findings,
        plan.constructs,
        plan.mechanisms,
        plan.datasets,
        plan.methods,
        plan.models,
        plan.identification_strategies,
        plan.mechanism_chain,
    ):
        for item in collection:
            result.update(item.evidence_chunk_ids)
    return result


def validate_plan_evidence(plan: DiscoveryPlan, bundle: EvidenceBundle) -> None:
    available = {item.chunk_id for item in bundle.evidence_hits}
    missing = sorted(_plan_chunk_ids(plan) - available)
    if missing:
        raise ValueError(
            "DiscoveryPlan references evidence chunks outside the EvidenceBundle: "
            + ", ".join(missing)
        )


def _normalized_binding_label(value: str) -> str:
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", value.casefold())


def compile_execution_readiness(
    plan: DiscoveryPlan,
    context: DiscoveryResearcherContext,
    *,
    consistency_review: QuestionPlanConsistencyReview | None = None,
) -> DiscoveryExecutionReadiness:
    """Compile prose requirements into fail-closed H1 execution inputs."""

    blockers: list[str] = []
    warnings: list[str] = []
    dataset_candidates: list[CompiledDatasetCandidate] = []
    resources = context.dataset_resources
    if not resources:
        blockers.append("未提供带不可变哈希、许可、粒度、时间键和连接键的数据资产")
        for index, required_input in enumerate(plan.required_inputs, 1):
            dataset_candidates.append(
                CompiledDatasetCandidate(
                    candidate_id=f"required-input:{index:02d}",
                    required_input=required_input,
                    label=required_input,
                    license_status="unknown",
                    status="blocked",
                    blockers=["required input has no bound immutable dataset resource"],
                )
            )
    else:
        for resource in resources:
            resource_blockers: list[str] = []
            if resource.license_status == "unknown":
                resource_blockers.append("dataset license or access permission is unverified")
            if (
                context.unit_of_analysis
                and _normalized_binding_label(context.unit_of_analysis)
                != _normalized_binding_label(resource.granularity)
            ):
                resource_blockers.append(
                    "dataset granularity does not match the declared unit of analysis"
                )
            candidate = CompiledDatasetCandidate(
                candidate_id=f"dataset-candidate:{resource.resource_id}",
                resource_id=resource.resource_id,
                label=resource.label,
                filename=resource.filename,
                mime_type=resource.mime_type,
                sha256=resource.sha256,
                size_bytes=resource.size_bytes,
                license_status=resource.license_status,
                granularity=resource.granularity,
                time_key=resource.time_key,
                join_keys=resource.join_keys,
                status="blocked" if resource_blockers else "ready",
                blockers=resource_blockers,
            )
            dataset_candidates.append(candidate)
            blockers.extend(
                f"{resource.resource_id}: {item}" for item in resource_blockers
            )
        warnings.append(
            f"{len(plan.required_inputs)} prose required inputs were compiled against "
            f"{len(resources)} declared dataset resources"
        )

    ready_resource_ids = {
        item.resource_id
        for item in dataset_candidates
        if item.status == "ready" and item.resource_id
    }
    resource_by_id = {item.resource_id: item for item in resources}
    variable_dictionary: list[CompiledVariableDictionaryEntry] = []
    for construct in plan.constructs:
        targets = {
            _normalized_binding_label(construct.key),
            _normalized_binding_label(construct.label),
        }
        match: tuple[DiscoveryDatasetResource, Any] | None = None
        for resource_id in sorted(ready_resource_ids):
            resource = resource_by_id[resource_id]
            for field in resource.fields:
                labels = {
                    _normalized_binding_label(field.name),
                    _normalized_binding_label(field.label),
                    *(_normalized_binding_label(item) for item in field.aliases),
                }
                if targets & labels:
                    match = (resource, field)
                    break
            if match is not None:
                break
        if match is None:
            blocker = f"构念“{construct.label}”未精确绑定到许可数据字段"
            blockers.append(blocker)
            variable_dictionary.append(
                CompiledVariableDictionaryEntry(
                    construct_key=construct.key,
                    construct_label=construct.label,
                    role=construct.role,
                    granularity=construct.granularity,
                    status="unbound",
                    blocker=blocker,
                )
            )
        else:
            resource, field = match
            variable_dictionary.append(
                CompiledVariableDictionaryEntry(
                    construct_key=construct.key,
                    construct_label=construct.label,
                    role=construct.role,
                    granularity=construct.granularity,
                    resource_id=resource.resource_id,
                    field_name=field.name,
                    field_label=field.label,
                    status="bound",
                )
            )

    identification_strategies: list[CompiledIdentificationStrategy] = []
    components_ready = bool(ready_resource_ids) and all(
        item.status == "bound" for item in variable_dictionary
    )
    if not plan.identification_strategies:
        blocker = "未形成有证据引用的 Identification Strategy"
        blockers.append(blocker)
        identification_strategies.append(
            CompiledIdentificationStrategy(
                strategy_id="identification:unresolved",
                label="Identification strategy unresolved",
                description="H1 cannot execute until an identification strategy is reviewed.",
                status="blocked",
                blocker=blocker,
            )
        )
    else:
        for strategy in plan.identification_strategies:
            blocker = None if components_ready else "dataset or variable bindings are incomplete"
            identification_strategies.append(
                CompiledIdentificationStrategy(
                    strategy_id=f"identification:{strategy.key}",
                    label=strategy.label,
                    description=strategy.description,
                    evidence_chunk_ids=strategy.evidence_chunk_ids,
                    status=(
                        "candidate_ready_for_h1_review" if blocker is None else "blocked"
                    ),
                    blocker=blocker,
                )
            )
            if blocker:
                blockers.append(f"{strategy.label}: {blocker}")

    if consistency_review is not None and consistency_review.decision != "pass":
        blockers.append("问题—计划一致性 Reviewer 未通过，禁止进入 H1 执行")
    unique_blockers = sorted(set(blockers))
    can_execute = not unique_blockers
    return DiscoveryExecutionReadiness(
        status="ready" if can_execute else "blocked",
        can_execute=can_execute,
        dataset_candidates=dataset_candidates,
        variable_dictionary=variable_dictionary,
        identification_strategies=identification_strategies,
        blockers=unique_blockers,
        warnings=sorted(set(warnings)),
    )


def _consistency_payload(
    original_question: str,
    context: DiscoveryResearcherContext,
    plan: DiscoveryPlan,
) -> dict[str, Any]:
    return {
        "original_question": original_question,
        "researcher_context": context.model_dump(mode="json", exclude={"dataset_resources"}),
        "candidate_research_question": plan.candidate_research_question,
        "hypothesis_statement": plan.hypothesis_statement,
        "constructs": [
            {
                "key": item.key,
                "label": item.label,
                "definition": item.definition,
                "role": item.role,
            }
            for item in plan.constructs
        ],
        "boundary_conditions": plan.boundary_conditions,
        "baseline_specification": plan.baseline_specification,
        "required_inputs": plan.required_inputs,
    }


async def review_question_plan_consistency(
    original_question: str,
    context: DiscoveryResearcherContext,
    plan: DiscoveryPlan,
    *,
    gateway: QwenModelGateway,
) -> QuestionPlanConsistencyReview:
    return await gateway.generate(
        "discovery_consistency_review",
        _consistency_payload(original_question, context, plan),
        QuestionPlanConsistencyReview,
    )


async def generate_discovery_plan(
    bundle: EvidenceBundle,
    context: DiscoveryResearcherContext,
    *,
    gateway: QwenModelGateway | None = None,
    consistency_repair: DiscoveryConsistencyRepairDirective | None = None,
) -> DiscoveryPlanGeneration:
    if not bundle.evidence_hits:
        raise ValueError("cannot plan discovery without source-located evidence")
    owned_model = gateway is None
    model = gateway or QwenModelGateway()
    try:
        plan = await model.generate(
            "discovery_planning",
            _planner_payload(bundle, context, consistency_repair),
            DiscoveryPlan,
        )
        available_chunk_ids = {item.chunk_id for item in bundle.evidence_hits}
        invalid_chunk_ids = sorted(_plan_chunk_ids(plan) - available_chunk_ids)
        reference_repaired = False
        if invalid_chunk_ids:
            repair_payload = _planner_payload(bundle, context, consistency_repair)
            repair_payload["reference_validation_failure"] = {
                "invalid_chunk_ids": invalid_chunk_ids,
                "allowed_chunk_ids": sorted(available_chunk_ids),
                "instruction": (
                    "Regenerate the complete DiscoveryPlan. Every evidence_chunk_ids value "
                    "must be copied exactly from allowed_chunk_ids; do not guess adjacent IDs."
                ),
                "previous_plan": plan.model_dump(mode="json"),
            }
            plan = await model.generate(
                "discovery_planning",
                repair_payload,
                DiscoveryPlan,
            )
            reference_repaired = True
        validate_plan_evidence(plan, bundle)
        warnings = list(bundle.warnings)
        if reference_repaired:
            warnings.append(
                "planner required one bounded evidence-reference repair before validation"
            )
        if consistency_repair is not None:
            warnings.append(
                "planner applied one bounded Reviewer-directed consistency repair"
            )
        if len(bundle.evidence_hits) > MAX_PLANNER_EVIDENCE_HITS:
            warnings.append(
                f"planner used the first {MAX_PLANNER_EVIDENCE_HITS} ranked evidence hits"
            )
        return DiscoveryPlanGeneration(
            original_question=bundle.question,
            evidence_bundle=bundle,
            plan=plan,
            model_usage=model.budget.snapshot(),
            execution_readiness=compile_execution_readiness(plan, context),
            warnings=sorted(set(warnings)),
        )
    finally:
        if owned_model:
            await model.http_client.aclose()


async def generate_reviewed_discovery_plan(
    request: DiscoveryPlanGenerationRequest,
    *,
    knowledge_client: KnowledgeClient | None = None,
    gateway: QwenModelGateway | None = None,
    max_consistency_repairs: int = 1,
) -> DiscoveryPlanGeneration:
    """Retrieve, plan, review consistency, and perform at most one repair retrieval."""

    if max_consistency_repairs not in (0, 1):
        raise ValueError("max_consistency_repairs must be 0 or 1")

    client = knowledge_client or KnowledgeClient()
    owned_model = gateway is None
    model = gateway or QwenModelGateway(
        seed=request.experiment_seed,
        temperature=request.temperature,
    )
    original_question = request.search.question
    search = request.search
    reviews: list[QuestionPlanConsistencyReview] = []
    rounds: list[DiscoveryRetrievalRound] = []
    latest: DiscoveryPlanGeneration | None = None
    repair_directive: DiscoveryConsistencyRepairDirective | None = None
    try:
        for round_index in range(1, max_consistency_repairs + 2):
            bundle = await client.search(search)
            latest = await generate_discovery_plan(
                bundle,
                request.context,
                gateway=model,
                consistency_repair=repair_directive,
            )
            repair_directive_sha256 = (
                _canonical_sha256(repair_directive.model_dump(mode="json"))
                if repair_directive is not None
                else None
            )
            rounds.append(
                DiscoveryRetrievalRound(
                    round_index=round_index,
                    query=search.question,
                    bundle_id=bundle.bundle_id,
                    evidence_hit_count=len(bundle.evidence_hits),
                    unique_document_count=(
                        bundle.retrieval_diagnostics.unique_document_count
                    ),
                    diversity_gate_passed=(
                        bundle.retrieval_diagnostics.diversity_gate_passed
                    ),
                    repair_feedback_applied=repair_directive is not None,
                    repair_directive_sha256=repair_directive_sha256,
                )
            )
            consistency = await review_question_plan_consistency(
                original_question,
                request.context,
                latest.plan,
                gateway=model,
            )
            reviews.append(consistency)
            rounds[-1] = rounds[-1].model_copy(
                update={
                    "candidate_research_question": latest.plan.candidate_research_question,
                    "hypothesis_statement": latest.plan.hypothesis_statement,
                    "construct_labels": [item.label for item in latest.plan.constructs],
                    "consistency_decision": consistency.decision,
                }
            )
            readiness = compile_execution_readiness(
                latest.plan,
                request.context,
                consistency_review=consistency,
            )
            if consistency.decision == "pass":
                return latest.model_copy(
                    update={
                        "original_question": original_question,
                        "model_usage": model.budget.snapshot(),
                        "consistency_reviews": reviews,
                        "retrieval_rounds": rounds,
                        "repair_count": round_index - 1,
                        "final_consistency_passed": True,
                        "execution_readiness": readiness,
                    }
                )
            if round_index <= max_consistency_repairs:
                missing_concepts = consistency.missing_concepts or consistency.requery_terms
                repair_directive = DiscoveryConsistencyRepairDirective(
                    original_question=original_question,
                    missing_concepts=missing_concepts,
                    requery_terms=consistency.requery_terms,
                    reviewer_rationale=consistency.rationale,
                    previous_candidate_research_question=(
                        latest.plan.candidate_research_question
                    ),
                    previous_hypothesis_statement=latest.plan.hypothesis_statement,
                    previous_construct_labels=[
                        item.label for item in latest.plan.constructs
                    ],
                )
                terms = "；".join(consistency.requery_terms)
                repaired_query = (
                    f"{original_question}\n补充检索必须保留的概念：{terms}"
                )[:4000]
                search = search.model_copy(update={"question": repaired_query})
        if latest is None:
            raise RuntimeError("discovery planning produced no generation")
        warnings = [
            *latest.warnings,
            "bounded consistency repair was exhausted; H0/H1 compilation remains blocked",
        ]
        return latest.model_copy(
            update={
                "original_question": original_question,
                "model_usage": model.budget.snapshot(),
                "consistency_reviews": reviews,
                "retrieval_rounds": rounds,
                "repair_count": max_consistency_repairs,
                "final_consistency_passed": False,
                "execution_readiness": compile_execution_readiness(
                    latest.plan,
                    request.context,
                    consistency_review=reviews[-1],
                ),
                "warnings": sorted(set(warnings)),
            }
        )
    finally:
        if owned_model:
            await model.http_client.aclose()


def _node_id(kind: str, key: str) -> str:
    return f"{kind}:{key}"


def _edge_id(source: str, relation: str, target: str) -> str:
    digest = hashlib.sha256(
        f"{source}\x1f{relation}\x1f{target}".encode("utf-8")
    ).hexdigest()
    return f"edge:{digest[:20]}"


def _evidence_ids(
    chunk_ids: list[str],
    chunk_to_evidence_id: dict[str, str],
) -> list[str]:
    return sorted({chunk_to_evidence_id[item] for item in chunk_ids})


def _reviewed_node(
    *,
    node_id: str,
    node_type: str,
    label: str,
    description: str,
    evidence_ids: list[str],
    observed_at: str,
    properties: dict[str, Any],
) -> dict[str, Any]:
    layer = "source" if node_type == "dataset" else "knowledge"
    return {
        "id": node_id,
        "type": node_type,
        "layer": layer,
        "label": label,
        "normalized_label": " ".join(label.strip().casefold().split()),
        "aliases": [],
        "description": description,
        "origin": "curated",
        "review_status": "human_verified",
        "confidence": 0.7,
        "version": 1,
        "validity": {
            "observed_at": observed_at,
            "valid_from": None,
            "valid_to": None,
        },
        "source_profile_ids": [],
        "evidence_ids": evidence_ids,
        "derivation": None,
        "properties": properties,
    }


def _reviewed_edge(
    *,
    source: str,
    relation: str,
    target: str,
    evidence_ids: list[str],
    observed_at: str,
    paper_id: str | None = None,
) -> dict[str, Any]:
    return {
        "id": _edge_id(source, relation, target),
        "source": source,
        "target": target,
        "type": relation,
        "layer": "knowledge",
        "origin": "curated",
        "review_status": "human_verified",
        "confidence": 0.7,
        "version": 1,
        "validity": {
            "observed_at": observed_at,
            "valid_from": None,
            "valid_to": None,
        },
        "evidence_ids": evidence_ids,
        "derivation": None,
        "context": {
            "profile_id": None,
            "paper_id": paper_id,
            "policy_document_id": None,
            "report_id": None,
            "snapshot_id": None,
            "variable_roles": [],
            "effect_direction": None,
            "significance": None,
            "identification_strength": "unknown",
            "population_or_subsample": None,
            "conditions": None,
        },
        "properties": {"assertion_kind": "reviewed_discovery_interpretation"},
    }


def _entity_node(
    entity: DiscoveryEntityDraft,
    *,
    node_type: str,
    observed_at: str,
    chunk_to_evidence_id: dict[str, str],
) -> dict[str, Any]:
    return _reviewed_node(
        node_id=_node_id(node_type, entity.key),
        node_type=node_type,
        label=entity.label,
        description=entity.description,
        evidence_ids=_evidence_ids(entity.evidence_chunk_ids, chunk_to_evidence_id),
        observed_at=observed_at,
        properties={
            "definition": entity.description,
            "granularity": "discovery candidate",
        },
    )


def _construct_node(
    construct: DiscoveryConstructDraft,
    *,
    observed_at: str,
    chunk_to_evidence_id: dict[str, str],
) -> dict[str, Any]:
    return _reviewed_node(
        node_id=_node_id("variable", construct.key),
        node_type="variable",
        label=construct.label,
        description=construct.definition,
        evidence_ids=_evidence_ids(construct.evidence_chunk_ids, chunk_to_evidence_id),
        observed_at=observed_at,
        properties={
            "definition": construct.definition,
            "granularity": construct.granularity,
            "discovery_role": construct.role,
        },
    )


def _window(as_of: str) -> dict[str, str]:
    year = int(as_of[:4])
    return {
        "current_from": f"{year - 3}-01-01",
        "current_to": as_of[:10],
        "baseline_from": f"{year - 7}-01-01",
        "baseline_to": f"{year - 4}-12-31",
    }


def _variable_card(construct: DiscoveryConstructDraft) -> dict[str, Any]:
    role_map = {
        "predictor": "independent",
        "outcome": "dependent",
        "mediator": "mediator",
        "moderator": "moderator",
        "control": "control",
    }
    return {
        "graph_node_id": _node_id("variable", construct.key),
        "name": construct.label,
        "definition": construct.definition,
        "role": role_map[construct.role],
        "expected_direction": (
            "unknown"
            if construct.expected_direction == "unspecified"
            else construct.expected_direction
        ),
        "measurement_candidates": [],
    }


def _legacy_novelty_search(
    bundle: EvidenceBundle,
    plan: DiscoveryPlan,
    *,
    bridge_document_ids: dict[str, str],
) -> dict[str, Any]:
    nearest = []
    seen_documents: set[str] = set()
    for hit in bundle.evidence_hits:
        if hit.document_id in seen_documents or hit.publication_year is None:
            continue
        seen_documents.add(hit.document_id)
        nearest.append(
            {
                "paper_id": bridge_document_ids[hit.document_id],
                "title": hit.title,
                "year": hit.publication_year,
                "overlap": "Retrieved as a semantically related work in the bounded corpus.",
                "difference": "Overlap and remaining difference require independent reviewer verification.",
                "verification_status": "unverified",
            }
        )
        if len(nearest) >= 10:
            break
    return {
        "schema_version": "0.1.0",
        "searches": [
            {
                "novelty_search_id": "novelty:online_candidate",
                "searched_at": bundle.generated_at.isoformat(),
                "queries": plan.novelty_queries,
                "sources": [f"knowledge-service:{bundle.corpus_snapshot_id}"],
                "query_audit": [
                    {
                        "query": query,
                        "mode": (
                            "exact"
                            if index == 0
                            else "broad"
                            if index == 1
                            else "adjacent"
                        ),
                        "source": f"knowledge-service:{bundle.corpus_snapshot_id}",
                        "hit_count": len(bundle.evidence_hits),
                        "retrieved_at": bundle.generated_at.isoformat(),
                    }
                    for index, query in enumerate(plan.novelty_queries)
                ],
                "nearest_works": nearest,
                "coverage_status": "uncertain",
                "remaining_difference": plan.novelty_remaining_difference,
            }
        ],
    }


def compile_discovery_plan(
    bundle: EvidenceBundle,
    plan: DiscoveryPlan,
    *,
    reviewer: str,
    review_note: str,
    consistency_review: QuestionPlanConsistencyReview | None = None,
    execution_readiness: DiscoveryExecutionReadiness | None = None,
) -> DiscoveryBuildRequest:
    """Compile an H0-reviewed plan into the migrated Group1 contracts."""

    validate_plan_evidence(plan, bundle)
    if consistency_review is not None and consistency_review.decision != "pass":
        raise ValueError(
            "question-plan consistency review failed; repeat retrieval before H0 compilation"
        )
    bridge = evidence_bundle_to_research_graph(bundle)
    observed_at = bundle.generated_at.isoformat()
    chunk_map = bridge.chunk_to_evidence_id
    all_evidence_ids = sorted(chunk_map.values())
    paper_ids = sorted(bridge.document_to_paper_id.values())
    plan_hash = _canonical_sha256(plan.model_dump(mode="json"))

    nodes: list[dict[str, Any]] = []
    nodes.append(
        _reviewed_node(
            node_id="research_field:online_discovery",
            node_type="research_field",
            label=plan.field_label,
            description=plan.stream_description,
            evidence_ids=all_evidence_ids,
            observed_at=observed_at,
            properties={"bounded_corpus": True},
        )
    )
    for finding in plan.findings:
        nodes.append(
            _reviewed_node(
                node_id=_node_id("finding", finding.key),
                node_type="finding",
                label=finding.statement,
                description=finding.statement,
                evidence_ids=_evidence_ids(finding.evidence_chunk_ids, chunk_map),
                observed_at=observed_at,
                properties={
                    "effect_direction": finding.direction,
                    "evidence_role": finding.role,
                },
            )
        )
    nodes.extend(
        _construct_node(item, observed_at=observed_at, chunk_to_evidence_id=chunk_map)
        for item in plan.constructs
    )
    for collection, node_type in (
        (plan.mechanisms, "mechanism"),
        (plan.datasets, "dataset"),
        (plan.methods, "method"),
        (plan.models, "model"),
        (plan.identification_strategies, "identification_strategy"),
    ):
        nodes.extend(
            _entity_node(
                item,
                node_type=node_type,
                observed_at=observed_at,
                chunk_to_evidence_id=chunk_map,
            )
            for item in collection
        )

    hit_by_chunk = {item.chunk_id: item for item in bundle.evidence_hits}
    edges: list[dict[str, Any]] = []
    for finding in plan.findings:
        finding_id = _node_id("finding", finding.key)
        evidence_by_document: dict[str, list[str]] = {}
        for chunk_id in finding.evidence_chunk_ids:
            hit = hit_by_chunk[chunk_id]
            evidence_by_document.setdefault(hit.document_id, []).append(chunk_map[chunk_id])
        for document_id, evidence_ids in evidence_by_document.items():
            paper_id = bridge.document_to_paper_id[document_id]
            edges.append(
                _reviewed_edge(
                    source=paper_id,
                    relation="REPORTS_FINDING",
                    target=finding_id,
                    evidence_ids=sorted(set(evidence_ids)),
                    observed_at=observed_at,
                    paper_id=paper_id,
                )
            )

    support_findings = [
        _node_id("finding", item.key)
        for item in plan.findings
        if item.role == "support"
    ]
    challenge_findings = [
        _node_id("finding", item.key)
        for item in plan.findings
        if item.role == "challenge"
    ]
    support_chunks = sorted(
        {
            chunk
            for item in plan.findings
            if item.role == "support"
            for chunk in item.evidence_chunk_ids
        }
    )
    challenge_chunks = sorted(
        {
            chunk
            for item in plan.findings
            if item.role == "challenge"
            for chunk in item.evidence_chunk_ids
        }
    )
    support_evidence = _evidence_ids(support_chunks, chunk_map)
    challenge_evidence = _evidence_ids(challenge_chunks, chunk_map)
    variable_ids = [_node_id("variable", item.key) for item in plan.constructs]
    mechanism_ids = [_node_id("mechanism", item.key) for item in plan.mechanisms]
    dataset_ids = [_node_id("dataset", item.key) for item in plan.datasets]
    method_ids = [_node_id("method", item.key) for item in plan.methods]
    model_ids = [_node_id("model", item.key) for item in plan.models]
    identification_ids = [
        _node_id("identification_strategy", item.key)
        for item in plan.identification_strategies
    ]
    readiness_blockers = (
        execution_readiness.blockers
        if execution_readiness is not None
        else plan.required_inputs
    )
    execution_ready = bool(
        execution_readiness is not None and execution_readiness.can_execute
    )
    data_status = (
        "feasible"
        if execution_ready
        else "conditional"
        if dataset_ids
        else "unknown"
    )
    method_status = (
        "feasible"
        if execution_ready or method_ids
        else "unknown"
    )
    predictor = next(item for item in plan.constructs if item.role == "predictor")
    outcome = next(item for item in plan.constructs if item.role == "outcome")
    mediators = [item for item in plan.constructs if item.role == "mediator"]
    moderators = [item for item in plan.constructs if item.role == "moderator"]
    controls = [item for item in plan.constructs if item.role == "control"]
    score_values = plan.scores.model_dump()
    overall = round(sum(score_values.values()) / len(score_values), 4)
    signal_type = {
        "mechanism": "untested_mechanism",
        "data": "new_dataset",
        "population": "population_coverage",
        "context": "sparse_relation",
        "method": "method_concentration",
        "model": "model_concentration",
        "policy": "new_policy",
        "controversy": "unresolved_controversy",
        "temporal": "temporal_gap",
        "cross_stream": "cross_stream_bridge",
    }[plan.gap_type]
    controversies = []
    if challenge_findings and len(plan.findings) >= 2:
        distribution: dict[str, int] = {}
        for item in plan.findings:
            distribution[item.direction] = distribution.get(item.direction, 0) + 1
        controversies.append(
            {
                "controversy_id": "controversy:online_evidence_balance",
                "statement": "Retrieved findings contain substantively different evidence roles or directions.",
                "finding_ids": [*support_findings, *challenge_findings],
                "direction_distribution": distribution,
                "evidence_ids": sorted(set([*support_evidence, *challenge_evidence])),
                "confidence": 0.6,
            }
        )

    config: dict[str, Any] = {
        "schema_version": "0.1.0",
        "inferred_entities": [],
        "run": {
            "as_of": observed_at,
            "build_timestamp": observed_at,
            "pipeline_run_id": f"run:online_discovery_{plan_hash[:16]}",
            "corpus_limit_statement": (
                "All gap and novelty statements are bounded to EvidenceBundle "
                f"{bundle.bundle_id} from corpus {bundle.corpus_snapshot_id}."
            ),
            "small_sample_threshold": 10,
            "generator": "hypoweaver.discovery_planner@1.0.0",
            "code_version": "1.0.0",
        },
        "landscape": {
            "window": _window(observed_at),
            "methodology": {
                "eligibility_rule": "Source-located EvidenceBundle papers retained after H0 review.",
                "clustering": {
                    "features": ["graph_entities", "text_embedding"],
                    "algorithm": "single-reviewed-stream",
                    "version": "1.0.0",
                    "parameters": {"automatic_clustering": False},
                },
                "trend_scoring": {
                    "formula_version": "bounded-weighted-components/0.1.0",
                    "component_weights": {
                        "recent_paper_share": 0.4,
                        "growth_rate": 0.2,
                        "method_diversity": 0.4,
                    },
                },
                "llm_labeling": {
                    "model": "qwen-reviewed-at-h0",
                    "prompt_hash": plan_hash,
                    "temperature": 0,
                },
            },
            "cluster_stability": 0.5,
            "warnings": [
                "Single-stream online draft; trend estimates are corpus-bounded.",
                "Novelty coverage remains uncertain until independent source search is reviewed.",
            ],
            "fields": [
                {
                    "field_id": "field:online_discovery",
                    "graph_node_id": "research_field:online_discovery",
                    "label": plan.field_label,
                    "member_paper_ids": paper_ids,
                    "top_topic_ids": [],
                    "top_model_ids": model_ids,
                    "evidence_ids": all_evidence_ids,
                }
            ],
            "streams": [
                {
                    "stream_id": "research_stream:online_discovery",
                    "trend_id": "trend_snapshot:online_discovery",
                    "label": plan.stream_label,
                    "description": plan.stream_description,
                    "label_confidence": 0.7,
                    "confidence": 0.6,
                    "field_ids": ["field:online_discovery"],
                    "member_paper_ids": paper_ids,
                    "core_paper_ids": paper_ids[: min(3, len(paper_ids))],
                    "top_topic_ids": [],
                    "top_theory_ids": [],
                    "top_mechanism_ids": mechanism_ids,
                    "top_variable_ids": variable_ids,
                    "top_method_ids": [*method_ids, *identification_ids],
                    "top_model_ids": model_ids,
                    "evidence_ids": all_evidence_ids,
                }
            ],
            "controversies": controversies,
            "frontier_signals": [],
        },
        "gaps": [
            {
                "gap_id": "research_gap:online_candidate",
                "gap_type": plan.gap_type,
                "title": plan.gap_title,
                "statement": plan.gap_statement,
                "current_state": plan.current_state,
                "missing_piece": plan.missing_piece,
                "why_important": plan.why_important,
                "signals": [
                    {
                        "signal_type": signal_type,
                        "metric_name": "supporting_finding_count",
                        "metric_value": len(support_findings),
                        "threshold": 1,
                        "explanation": plan.gap_statement,
                        "graph_refs": [
                            "trend_snapshot:online_discovery",
                            *support_findings,
                        ],
                        "evidence_ids": support_evidence,
                    }
                ],
                "supporting_graph_refs": [
                    "trend_snapshot:online_discovery",
                    *support_findings,
                ],
                "supporting_evidence_ids": support_evidence,
                "counterevidence_ids": challenge_evidence,
                "novelty_search_id": "novelty:online_candidate",
                "data_feasibility": {
                    "status": data_status,
                    "required_variable_ids": variable_ids,
                    "candidate_data_source_ids": dataset_ids,
                    "blocking_gaps": readiness_blockers,
                    "assessment_as_of": observed_at,
                },
                "candidate_research_questions": [plan.candidate_research_question],
                "scores": {
                    "novelty": plan.scores.novelty,
                    "importance": plan.scores.policy_value,
                    "evidence_strength": plan.scores.evidence,
                    "data_feasibility": plan.scores.data,
                    "method_feasibility": plan.scores.method,
                    "policy_value": plan.scores.policy_value,
                    "overall": overall,
                },
                "status": "needs_human_review",
                "derivation": {
                    "workflow_version": "1.0.0",
                    "detector": "qwen_evidence_synthesis_reviewed_at_h0",
                    "model": "qwen",
                    "prompt_hash": plan_hash,
                    "input_refs": [
                        "trend_snapshot:online_discovery",
                        *support_findings,
                        *challenge_findings,
                    ],
                },
                "review": {
                    "review_status": "accepted",
                    "reviewer": reviewer,
                    "reviewed_at": observed_at,
                    "comments": [review_note],
                },
                "confidence": min(1.0, plan.scores.evidence / 5),
                "graph_links": {
                    "indicator_node_ids": ["trend_snapshot:online_discovery"],
                    "support_node_ids": support_findings,
                    "challenge_node_ids": challenge_findings,
                    "concern_node_ids": [
                        "research_stream:online_discovery",
                        *variable_ids,
                    ],
                    "enabled_by_node_ids": dataset_ids,
                },
            }
        ],
        "hypotheses": [
            {
                "hypothesis_id": "hypothesis:online_candidate",
                "gap_card_ids": ["research_gap:online_candidate"],
                "title": plan.hypothesis_title,
                "hypothesis_statement": plan.hypothesis_statement,
                "falsifiable_form": plan.falsifiable_form,
                "rationale": plan.rationale,
                "mechanism_chain": [
                    {
                        "order": index,
                        "source_node_id": (
                            _node_id("variable", step.source_key)
                            if any(item.key == step.source_key for item in plan.constructs)
                            else _node_id("mechanism", step.source_key)
                        ),
                        "relation": step.relation,
                        "target_node_id": (
                            _node_id("variable", step.target_key)
                            if any(item.key == step.target_key for item in plan.constructs)
                            else _node_id("mechanism", step.target_key)
                        ),
                        "statement": step.statement,
                        "evidence_ids": _evidence_ids(
                            step.evidence_chunk_ids,
                            chunk_map,
                        ),
                    }
                    for index, step in enumerate(plan.mechanism_chain, 1)
                ],
                "variables": {
                    "independent": [_variable_card(predictor)],
                    "dependent": [_variable_card(outcome)],
                    "mediators": [_variable_card(item) for item in mediators],
                    "moderators": [_variable_card(item) for item in moderators],
                    "controls": [_variable_card(item) for item in controls],
                },
                "boundary_conditions": plan.boundary_conditions,
                "predictions": [
                    {
                        "prediction_id": _node_id("prediction", item.key),
                        "statement": item.statement,
                        "observable_pattern": item.observable_pattern,
                        "would_falsify": item.would_falsify,
                    }
                    for item in plan.predictions
                ],
                "evidence_balance": {
                    "supporting_finding_ids": support_findings,
                    "challenging_finding_ids": challenge_findings,
                    "policy_document_ids": [],
                    "unresolved_conflicts": plan.unresolved_conflicts,
                },
                "novelty_check_ref": "novelty:online_candidate",
                "feasibility": {
                    "data_status": data_status,
                    "method_status": method_status,
                    "citation_status": "partially_verified",
                    "blocking_items": readiness_blockers,
                    "assessed_at": observed_at,
                },
                "recommended_design": {
                    "candidate_dataset_ids": dataset_ids,
                    "candidate_method_ids": method_ids,
                    "candidate_model_ids": model_ids,
                    "candidate_identification_strategy_ids": identification_ids,
                    "unit_of_analysis": plan.unit_of_analysis,
                    "baseline_specification": plan.baseline_specification,
                    "major_threats": plan.major_threats,
                },
                "scores": {**score_values, "overall": overall},
                "handoff": {
                    "required_inputs": readiness_blockers,
                    "blocking_questions": plan.blocking_questions,
                    "validation_acceptance_criteria": plan.validation_acceptance_criteria,
                    "evidence_bundle_refs": [
                        "novelty:online_candidate",
                        *all_evidence_ids,
                    ],
                    "reproduction_seed": 42,
                },
                "status": "needs_scientific_review",
                "review": {
                    "green_finance_review": "pending H0 final decision",
                    "data_review": "pending",
                    "method_review": "pending",
                    "citation_review": "partial",
                    "final_decision": "revise",
                },
                "confidence": min(1.0, plan.scores.evidence / 5),
                "graph_links": {
                    "predictor_node_ids": [_node_id("variable", predictor.key)],
                    "outcome_node_ids": [_node_id("variable", outcome.key)],
                    "mediator_node_ids": [
                        _node_id("variable", item.key) for item in mediators
                    ],
                    "moderator_node_ids": [
                        _node_id("variable", item.key) for item in moderators
                    ],
                    "mechanism_node_ids": mechanism_ids,
                    "support_node_ids": support_findings,
                    "challenge_node_ids": challenge_findings,
                    "enabled_by_node_ids": dataset_ids,
                    "recommended_method_ids": method_ids,
                    "recommended_model_ids": model_ids,
                    "recommended_identification_strategy_ids": identification_ids,
                    "recommended_dataset_ids": dataset_ids,
                },
            }
        ],
    }
    novelty = _legacy_novelty_search(
        bundle,
        plan,
        bridge_document_ids=bridge.document_to_paper_id,
    )
    return DiscoveryBuildRequest(
        evidence_bundle=bundle,
        reviewed_graph_patch=ReviewedGraphPatch(
            nodes=nodes,
            edges=edges,
            review_note=review_note,
        ),
        discovery_config=config,
        novelty_search=novelty,
    )


def review_discovery_plan(
    request: DiscoveryPlanReviewRequest,
    *,
    reviewer: str,
) -> DiscoveryReleasePreview:
    build = compile_discovery_plan(
        request.evidence_bundle,
        request.plan,
        reviewer=reviewer,
        review_note=request.review_note,
        consistency_review=request.consistency_review,
        execution_readiness=request.execution_readiness,
    )
    return build_discovery_release_preview(build, reviewer=reviewer)

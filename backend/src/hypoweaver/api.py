from __future__ import annotations

import hmac
import os
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .case_import import (
    CaseUploadStore,
    CaseImportError,
    LocalCaseImporter,
    LocalCaseImportRequest,
    LocalCaseImportResponse,
)
from .benchmark_runner import (
    AgentLaboratoryRunner,
    BaselineRun,
    BaselineRunNotFoundError,
    BaselineRunRequest,
)
from .definition import DEFINITION_VERSION, build_app_a_definition
from .engine import WorkflowEngine, WorkflowTransitionError
from .group1_handoff import (
    bind_group1_execution_panel,
    Group1BridgeResult,
    Group1LocalHandoffRequest,
    Group1RunLaunchResponse,
    Group1VerifiedBundleStatus,
    import_group1_handoff,
    inspect_verified_group1_bundle,
    verified_group1_bundle_request,
)
from .knowledge_client import KnowledgeClient, KnowledgeServiceError
from .knowledge_models import (
    EvidenceBundle,
    KnowledgeCatalogPage,
    KnowledgeDocumentTextSlice,
    KnowledgeSearchRequest,
    KnowledgeServiceStatus,
)
from .literature_reader import (
    LiteratureAskRequest,
    LiteratureAskResponse,
    LiteratureDocument,
    LiteratureDocumentError,
    LiteratureDocumentStore,
    LiteraturePage,
    ask_literature,
)
from .discovery_bridge import EvidenceGraphBridge, evidence_bundle_to_research_graph
from .discovery_pipeline import (
    DiscoveryBuildRequest,
    DiscoveryReleasePreview,
    build_discovery_release_preview,
)
from .discovery_handoff import (
    DiscoveryLaunchRequest,
    DiscoveryRunLaunchResponse,
    create_run_request as create_discovery_run_request,
    discovery_release_to_case,
)
from .discovery_planner import (
    DiscoveryPlanGeneration,
    DiscoveryPlanGenerationRequest,
    DiscoveryPlanLaunchRequest,
    DiscoveryPlanReviewRequest,
    compile_discovery_plan,
    generate_reviewed_discovery_plan,
    review_discovery_plan,
)
from .models import CreateRunRequest, DatasetRef, GateDecisionRequest, RevisionRequest, RunState
from .repository import (
    RunNotFoundError,
    RunRepository,
    TransitionInProgressError,
    VersionConflictError,
)
from .runtime_config import (
    RuntimeConfigStatus,
    RuntimeConfigStore,
    RuntimeConfigUpdate,
    RuntimeConnectionTestRequest,
    RuntimeConnectionTestResult,
    test_runtime_connection,
)
from .plot_agent.renderer import resolve_artifact_uri
from .visualization import FigureBundle
from .storage_limits import LocalStorageLimitError


repository = RunRepository()
engine = WorkflowEngine(repository)
runtime_config_store = RuntimeConfigStore()
case_importer = LocalCaseImporter()
case_upload_store = CaseUploadStore()
literature_store = LiteratureDocumentStore()
baseline_runner = AgentLaboratoryRunner()
app = FastAPI(
    title="HypoWeaver-Qwen Workflow API",
    version="1.0.0",
    description="Code-native workflow runtime. Dify YAML is not loaded at runtime.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://127.0.0.1:5174", "http://127.0.0.1:5175", "http://localhost:5173", "http://localhost:5174", "http://localhost:5175"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def mutation_actor(
    request: Request,
    x_hypoweaver_token: str | None = Header(default=None),
) -> str:
    configured = os.getenv("HYPOWEAVER_API_TOKEN")
    if configured:
        if not x_hypoweaver_token or not hmac.compare_digest(
            configured, x_hypoweaver_token
        ):
            raise HTTPException(status_code=401, detail="invalid workflow API token")
    else:
        host = request.client.host if request.client else ""
        if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
            raise HTTPException(
                status_code=403,
                detail="mutation endpoints are loopback-only unless HYPOWEAVER_API_TOKEN is configured",
            )
    return os.getenv("HYPOWEAVER_ACTOR", "local_researcher")


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "runtime": "code-native", "definition": f"app-a@{DEFINITION_VERSION}"}


@app.get("/api/v1/knowledge/health", response_model=KnowledgeServiceStatus)
async def knowledge_health() -> KnowledgeServiceStatus:
    try:
        return await KnowledgeClient().status()
    except KnowledgeServiceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get(
    "/api/v1/knowledge/catalog/{document_id}/text",
    response_model=KnowledgeDocumentTextSlice,
)
async def knowledge_document_text(
    document_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30_000, ge=1, le=50_000),
    _actor: str = Depends(mutation_actor),
) -> KnowledgeDocumentTextSlice:
    try:
        return await KnowledgeClient().document_text(
            document_id,
            offset=offset,
            limit=limit,
        )
    except KnowledgeServiceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/api/v1/knowledge/catalog", response_model=KnowledgeCatalogPage)
async def knowledge_catalog(
    query: str = Query(default="", max_length=500),
    fulltext_only: bool = False,
    readable_only: bool = False,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    _actor: str = Depends(mutation_actor),
) -> KnowledgeCatalogPage:
    try:
        return await KnowledgeClient().catalog(
            query=query,
            fulltext_only=fulltext_only,
            readable_only=readable_only,
            offset=offset,
            limit=limit,
        )
    except KnowledgeServiceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/api/v1/knowledge/search", response_model=EvidenceBundle)
async def knowledge_search(
    request: KnowledgeSearchRequest,
    _actor: str = Depends(mutation_actor),
) -> EvidenceBundle:
    try:
        return await KnowledgeClient().search(request)
    except KnowledgeServiceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/api/v1/literature/documents", response_model=list[LiteratureDocument])
def list_literature_documents(
    _actor: str = Depends(mutation_actor),
) -> list[LiteratureDocument]:
    literature_store.install_showcase_documents()
    return literature_store.list_documents()


@app.post(
    "/api/v1/literature/documents",
    response_model=LiteratureDocument,
    status_code=201,
)
async def upload_literature_document(
    request: Request,
    filename: str,
    _actor: str = Depends(mutation_actor),
) -> LiteratureDocument:
    try:
        return await literature_store.save(filename, request.stream())
    except LocalStorageLimitError as error:
        raise HTTPException(status_code=409, detail=error.detail()) from error
    except LiteratureDocumentError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.delete("/api/v1/literature/documents/{document_id}")
async def delete_literature_document(
    document_id: str,
    _actor: str = Depends(mutation_actor),
) -> dict[str, str]:
    try:
        deleted = await literature_store.delete(document_id)
    except LiteratureDocumentError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"deleted_document_id": deleted.document_id}


@app.get(
    "/api/v1/literature/documents/{document_id}",
    response_model=LiteratureDocument,
)
def get_literature_document(
    document_id: str,
    _actor: str = Depends(mutation_actor),
) -> LiteratureDocument:
    try:
        return literature_store.get_document(document_id)
    except LiteratureDocumentError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get(
    "/api/v1/literature/documents/{document_id}/pages/{page_number}",
    response_model=LiteraturePage,
)
def get_literature_page(
    document_id: str,
    page_number: int,
    _actor: str = Depends(mutation_actor),
) -> LiteraturePage:
    try:
        return literature_store.get_page(document_id, page_number)
    except LiteratureDocumentError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/v1/literature/documents/{document_id}/pages/{page_number}/image")
def get_literature_page_image(
    document_id: str,
    page_number: int,
    _actor: str = Depends(mutation_actor),
) -> Response:
    try:
        return Response(
            content=literature_store.render_page_png(document_id, page_number),
            media_type="image/png",
            headers={"Cache-Control": "private, max-age=3600"},
        )
    except LiteratureDocumentError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/v1/literature/documents/{document_id}/file")
def get_literature_original_pdf(
    document_id: str,
    _actor: str = Depends(mutation_actor),
) -> FileResponse:
    try:
        path = literature_store.get_original_pdf(document_id)
        return FileResponse(path, media_type="application/pdf")
    except LiteratureDocumentError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post(
    "/api/v1/literature/documents/{document_id}/ask",
    response_model=LiteratureAskResponse,
)
async def ask_literature_document(
    document_id: str,
    request: LiteratureAskRequest,
    _actor: str = Depends(mutation_actor),
) -> LiteratureAskResponse:
    try:
        return await ask_literature(
            document_id,
            request,
            runtime_config_store.resolve(),
            literature_store,
        )
    except LiteratureDocumentError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post(
    "/api/v1/discovery/evidence-preview",
    response_model=EvidenceGraphBridge,
)
async def discovery_evidence_preview(
    request: KnowledgeSearchRequest,
    _actor: str = Depends(mutation_actor),
) -> EvidenceGraphBridge:
    try:
        bundle = await KnowledgeClient().search(request)
        return evidence_bundle_to_research_graph(bundle)
    except KnowledgeServiceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post(
    "/api/v1/discovery/plans/generate",
    response_model=DiscoveryPlanGeneration,
)
async def generate_online_discovery_plan(
    request: DiscoveryPlanGenerationRequest,
    _actor: str = Depends(mutation_actor),
) -> DiscoveryPlanGeneration:
    """Retrieve, plan, consistency-review, and at most once repair the draft."""

    try:
        return await generate_reviewed_discovery_plan(request)
    except KnowledgeServiceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post(
    "/api/v1/discovery/plans/review",
    response_model=DiscoveryReleasePreview,
)
def review_online_discovery_plan(
    request: DiscoveryPlanReviewRequest,
    actor: str = Depends(mutation_actor),
) -> DiscoveryReleasePreview:
    """Compile an explicitly H0-reviewed Qwen draft through the Group1 engine."""

    try:
        return review_discovery_plan(request, reviewer=actor)
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post(
    "/api/v1/discovery/plans/launch",
    response_model=DiscoveryRunLaunchResponse,
    status_code=201,
)
async def launch_online_discovery_plan(
    request: DiscoveryPlanLaunchRequest,
    actor: str = Depends(mutation_actor),
) -> DiscoveryRunLaunchResponse:
    """Record H0 approval and create a plan-only run at the existing H1 gate."""

    try:
        build = compile_discovery_plan(
            request.evidence_bundle,
            request.plan,
            reviewer=actor,
            review_note=request.review_note,
            consistency_review=request.consistency_review,
            execution_readiness=request.execution_readiness,
        )
        release = build_discovery_release_preview(build, reviewer=actor)
        hypothesis_id = "hypothesis:online_candidate"
        case = discovery_release_to_case(
            release,
            hypothesis_id=hypothesis_id,
            approver=actor,
            approval_reason=request.approval_reason,
            execution_readiness=request.execution_readiness,
        )
        launch = DiscoveryLaunchRequest(
            build=build,
            hypothesis_id=hypothesis_id,
            approve_h0=True,
            approval_reason=request.approval_reason,
            mode=request.mode,
            research_model_provider=request.research_model_provider,
        )
        run = await engine.create_run(create_discovery_run_request(case, launch))
        return DiscoveryRunLaunchResponse(
            discovery_release=release,
            case_submission=case,
            run=run,
        )
    except LocalStorageLimitError as error:
        raise HTTPException(status_code=409, detail=error.detail()) from error
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post(
    "/api/v1/discovery/releases/preview",
    response_model=DiscoveryReleasePreview,
)
def discovery_release_preview(
    request: DiscoveryBuildRequest,
    actor: str = Depends(mutation_actor),
) -> DiscoveryReleasePreview:
    try:
        return build_discovery_release_preview(request, reviewer=actor)
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post(
    "/api/v1/discovery/releases/launch",
    response_model=DiscoveryRunLaunchResponse,
    status_code=201,
)
async def launch_discovery_release(
    request: DiscoveryLaunchRequest,
    actor: str = Depends(mutation_actor),
) -> DiscoveryRunLaunchResponse:
    try:
        release = build_discovery_release_preview(request.build, reviewer=actor)
        case = discovery_release_to_case(
            release,
            hypothesis_id=request.hypothesis_id,
            approver=actor,
            approval_reason=request.approval_reason,
        )
        run = await engine.create_run(create_discovery_run_request(case, request))
        return DiscoveryRunLaunchResponse(
            discovery_release=release,
            case_submission=case,
            run=run,
        )
    except LocalStorageLimitError as error:
        raise HTTPException(status_code=409, detail=error.detail()) from error
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/v1/definitions/app-a")
def get_app_a_definition() -> dict:
    return build_app_a_definition()


@app.get("/api/v1/runtime-config", response_model=RuntimeConfigStatus)
def get_runtime_config() -> RuntimeConfigStatus:
    return runtime_config_store.status()


@app.put("/api/v1/runtime-config", response_model=RuntimeConfigStatus)
def update_runtime_config(
    request: RuntimeConfigUpdate,
    _actor: str = Depends(mutation_actor),
) -> RuntimeConfigStatus:
    try:
        return runtime_config_store.update(request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post(
    "/api/v1/runtime-config/tests",
    response_model=RuntimeConnectionTestResult,
)
async def test_runtime_config_connection(
    request: RuntimeConnectionTestRequest,
    _actor: str = Depends(mutation_actor),
) -> RuntimeConnectionTestResult:
    return await test_runtime_connection(request, runtime_config_store)


@app.post(
    "/api/v1/case-imports/local",
    response_model=LocalCaseImportResponse,
)
def import_local_case(
    request: LocalCaseImportRequest,
    _actor: str = Depends(mutation_actor),
) -> LocalCaseImportResponse:
    try:
        return case_importer.import_folder(request.path)
    except CaseImportError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post(
    "/api/v1/group1-handoffs/local/preview",
    response_model=Group1BridgeResult,
)
def preview_group1_handoff(
    request: Group1LocalHandoffRequest,
    _actor: str = Depends(mutation_actor),
) -> Group1BridgeResult:
    try:
        return _group1_bridge_from_request(request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get(
    "/api/v1/group1-handoffs/local/verified-bundle",
    response_model=Group1VerifiedBundleStatus,
)
def get_verified_group1_bundle() -> Group1VerifiedBundleStatus:
    return inspect_verified_group1_bundle()


@app.post(
    "/api/v1/group1-handoffs/local/verified-bundle/runs",
    response_model=Group1RunLaunchResponse,
    status_code=201,
)
async def start_verified_group1_bundle_run(
    _actor: str = Depends(mutation_actor),
) -> Group1RunLaunchResponse:
    try:
        return await _launch_group1_handoff_run(verified_group1_bundle_request())
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LocalStorageLimitError as error:
        raise HTTPException(status_code=409, detail=error.detail()) from error


@app.post(
    "/api/v1/group1-handoffs/local/runs",
    response_model=Group1RunLaunchResponse,
    status_code=201,
)
async def start_group1_handoff_run(
    request: Group1LocalHandoffRequest,
    _actor: str = Depends(mutation_actor),
) -> Group1RunLaunchResponse:
    try:
        return await _launch_group1_handoff_run(request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LocalStorageLimitError as error:
        raise HTTPException(status_code=409, detail=error.detail()) from error


async def _launch_group1_handoff_run(
    request: Group1LocalHandoffRequest,
) -> Group1RunLaunchResponse:
    bridge = _group1_bridge_from_request(request)
    if request.execution_panel_path is not None:
        main_ref = next(
            item
            for item in bridge.case_submission.dataset_refs
            if item.role == "main"
        )
        engine.dataset_registry.register(
            main_ref,
            Path(request.execution_panel_path).expanduser().resolve(strict=True),
        )
    fixture_mode = request.mode == "fixture"
    run = await engine.create_run(
        CreateRunRequest(
            mode=request.mode,
            case=bridge.case_submission,
            model_provider=(
                "fixture" if fixture_mode else request.research_model_provider
            ),
            execution_mode="fixture" if fixture_mode else "external",
        )
    )
    return Group1RunLaunchResponse(bridge=bridge, run=run)


def _group1_bridge_from_request(
    request: Group1LocalHandoffRequest,
) -> Group1BridgeResult:
    bridge = import_group1_handoff(request.path)
    binding = (
        request.execution_panel_path,
        request.execution_manifest_path,
        request.source_config_path,
    )
    if any(value is not None for value in binding):
        if not all(value is not None for value in binding):
            raise ValueError(
                "execution_panel_path, execution_manifest_path, and source_config_path must be supplied together"
            )
        bridge = bind_group1_execution_panel(
            bridge,
            request.execution_panel_path or "",
            request.execution_manifest_path or "",
            request.source_config_path or "",
        )
    return bridge


@app.post(
    "/api/v1/case-imports/upload",
    response_model=LocalCaseImportResponse,
)
async def upload_case_file(
    request: Request,
    filename: str,
    _actor: str = Depends(mutation_actor),
) -> LocalCaseImportResponse:
    try:
        uploaded = await case_upload_store.save(filename, request.stream())
        return case_importer.import_folder(uploaded.parent)
    except LocalStorageLimitError as error:
        raise HTTPException(status_code=409, detail=error.detail()) from error
    except CaseImportError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post(
    "/api/v1/case-imports/assets/upload",
    response_model=DatasetRef,
)
async def upload_case_asset(
    request: Request,
    filename: str,
    _actor: str = Depends(mutation_actor),
) -> DatasetRef:
    try:
        uploaded = await case_upload_store.save(filename, request.stream())
        return case_importer.register_supplementary_asset(uploaded)
    except LocalStorageLimitError as error:
        raise HTTPException(status_code=409, detail=error.detail()) from error
    except CaseImportError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post(
    "/api/v1/baselines/agent-laboratory/runs",
    response_model=BaselineRun,
    status_code=202,
)
def start_agent_laboratory(
    request: BaselineRunRequest,
    _actor: str = Depends(mutation_actor),
) -> BaselineRun:
    try:
        return baseline_runner.start(request)
    except (CaseImportError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get(
    "/api/v1/baselines/agent-laboratory/runs",
    response_model=list[BaselineRun],
)
def list_agent_laboratory_runs(case_id: str | None = None) -> list[BaselineRun]:
    return baseline_runner.list(case_id=case_id)


@app.get(
    "/api/v1/baselines/agent-laboratory/runs/{run_id}",
    response_model=BaselineRun,
)
def get_agent_laboratory_run(run_id: str) -> BaselineRun:
    try:
        return baseline_runner.get(run_id)
    except BaselineRunNotFoundError as error:
        raise HTTPException(status_code=404, detail="baseline run not found") from error


@app.get("/api/v1/runs", response_model=list[RunState])
def list_runs() -> list[RunState]:
    return engine.list_runs()


@app.post("/api/v1/runs", response_model=RunState, status_code=201)
async def create_run(
    request: CreateRunRequest,
    _actor: str = Depends(mutation_actor),
) -> RunState:
    try:
        return await engine.create_run(request)
    except LocalStorageLimitError as error:
        raise HTTPException(status_code=409, detail=error.detail()) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/api/v1/runs/{run_id}", response_model=RunState)
def get_run(run_id: str) -> RunState:
    try:
        return engine.get_run(run_id)
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error


@app.delete("/api/v1/runs/{run_id}")
def delete_run(
    run_id: str,
    _actor: str = Depends(mutation_actor),
) -> dict[str, str]:
    try:
        engine.delete_run(run_id)
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error
    return {"deleted_run_id": run_id}


@app.post("/api/v1/runs/{run_id}/advance", response_model=RunState)
async def advance_run(
    run_id: str,
    _actor: str = Depends(mutation_actor),
) -> RunState:
    try:
        return await engine.advance(run_id)
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error
    except WorkflowTransitionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/v1/runs/{run_id}/writing/retry", response_model=RunState)
async def retry_run_writing(
    run_id: str,
    _actor: str = Depends(mutation_actor),
) -> RunState:
    try:
        return await engine.retry_writing(run_id)
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error
    except (VersionConflictError, TransitionInProgressError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except WorkflowTransitionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/v1/runs/{run_id}/design/retry", response_model=RunState)
async def retry_run_design(
    run_id: str,
    _actor: str = Depends(mutation_actor),
) -> RunState:
    try:
        return await engine.retry_design(run_id)
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error
    except (VersionConflictError, TransitionInProgressError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except WorkflowTransitionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/v1/runs/{run_id}/gates/{gate}", response_model=RunState)
async def decide_gate(
    run_id: str,
    gate: str,
    request: GateDecisionRequest,
    actor: str = Depends(mutation_actor),
) -> RunState:
    try:
        trusted_request = request.model_copy(update={"actor": actor})
        return await engine.decide_gate(run_id, gate, trusted_request)
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error
    except VersionConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except TransitionInProgressError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except WorkflowTransitionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/v1/runs/{run_id}/revisions", response_model=RunState)
async def submit_revision(
    run_id: str,
    request: RevisionRequest,
    actor: str = Depends(mutation_actor),
) -> RunState:
    try:
        trusted_request = request.model_copy(update={"actor": actor})
        return await engine.submit_revision(run_id, trusted_request)
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error
    except (VersionConflictError, TransitionInProgressError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except WorkflowTransitionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/v1/runs/{run_id}/artifacts/{artifact_key}")
def get_artifact(run_id: str, artifact_key: str) -> dict:
    try:
        run = engine.get_run(run_id)
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error
    try:
        return run.artifacts[artifact_key]
    except KeyError as error:
        raise HTTPException(status_code=404, detail="artifact not found") from error


@app.get("/api/v1/runs/{run_id}/figures/{figure_id}/{file_format}")
def get_figure_file(
    run_id: str,
    figure_id: str,
    file_format: str,
) -> FileResponse:
    try:
        run = engine.get_run(run_id)
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error
    for artifact_key in (
        "evidence_figure_bundle",
        "publication_figure_bundle",
    ):
        envelope = run.artifacts.get(artifact_key)
        if not isinstance(envelope, dict):
            continue
        try:
            bundle = FigureBundle.model_validate(envelope.get("payload"))
        except (TypeError, ValueError):
            continue
        for figure in bundle.figures:
            if figure.figure_id != figure_id:
                continue
            file = next(
                (item for item in figure.files if item.format == file_format),
                None,
            )
            if file is None:
                break
            try:
                path = resolve_artifact_uri(
                    file.artifact_uri,
                    expected_sha256=file.sha256,
                )
            except ValueError as error:
                raise HTTPException(
                    status_code=404,
                    detail="figure file not found",
                ) from error
            return FileResponse(
                path,
                media_type=file.mime_type,
            )
    raise HTTPException(status_code=404, detail="figure not found")


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DIST_DIR = PROJECT_ROOT / "dist"
if DIST_DIR.exists():
    assets = DIST_DIR / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}")
    def frontend(path: str) -> FileResponse:
        candidate = (DIST_DIR / path).resolve()
        if path and candidate.is_relative_to(DIST_DIR.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST_DIR / "index.html")

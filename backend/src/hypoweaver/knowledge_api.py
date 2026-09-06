"""Internal FastAPI boundary for vector and graph retrieval."""

from __future__ import annotations

import hmac
import os
import threading

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request

from .knowledge_models import (
    EvidenceBundle,
    KnowledgeCatalogPage,
    KnowledgeDocumentTextSlice,
    KnowledgeSearchRequest,
    KnowledgeServiceStatus,
)
from .knowledge_service import KnowledgeService


app = FastAPI(
    title="HypoWeaver Knowledge Service",
    version="1.0.0",
    description=(
        "Read-only vector and graph retrieval. Graph edges are candidates; "
        "only source-located EvidenceHit records may enter scientific discovery."
    ),
)

_service: KnowledgeService | None = None
_service_lock = threading.Lock()


def get_service() -> KnowledgeService:
    global _service
    if _service is not None:
        return _service
    with _service_lock:
        if _service is None:
            _service = KnowledgeService()
    return _service


def knowledge_reader(
    request: Request,
    authorization: str | None = Header(default=None),
) -> str:
    configured = os.getenv("KNOWLEDGE_SERVICE_TOKEN")
    if configured:
        expected = f"Bearer {configured}"
        if not authorization or not hmac.compare_digest(expected, authorization):
            raise HTTPException(status_code=401, detail="invalid knowledge service token")
    else:
        host = request.client.host if request.client else ""
        if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
            raise HTTPException(
                status_code=403,
                detail=(
                    "knowledge endpoints are loopback-only unless "
                    "KNOWLEDGE_SERVICE_TOKEN is configured"
                ),
            )
    return "knowledge-reader"


@app.get("/v1/health", response_model=KnowledgeServiceStatus)
def health() -> KnowledgeServiceStatus:
    try:
        return get_service().status()
    except (OSError, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/v1/catalog", response_model=KnowledgeCatalogPage)
def catalog(
    query: str = Query(default="", max_length=500),
    fulltext_only: bool = False,
    readable_only: bool = False,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    _reader: str = Depends(knowledge_reader),
) -> KnowledgeCatalogPage:
    try:
        return get_service().catalog(
            query=query,
            fulltext_only=fulltext_only,
            readable_only=readable_only,
            offset=offset,
            limit=limit,
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get(
    "/v1/catalog/{document_id}/text",
    response_model=KnowledgeDocumentTextSlice,
)
def document_text(
    document_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30_000, ge=1, le=50_000),
    _reader: str = Depends(knowledge_reader),
) -> KnowledgeDocumentTextSlice:
    try:
        return get_service().document_text(document_id, offset=offset, limit=limit)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (OSError, RuntimeError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/v1/search", response_model=EvidenceBundle)
def search(
    request: KnowledgeSearchRequest,
    _reader: str = Depends(knowledge_reader),
) -> EvidenceBundle:
    try:
        return get_service().search(request)
    except (OSError, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

"""Workflow-side client for the isolated knowledge service."""

from __future__ import annotations

import os
from urllib.parse import quote, urlsplit

import httpx

from .knowledge_models import (
    EvidenceBundle,
    KnowledgeCatalogPage,
    KnowledgeDocumentTextSlice,
    KnowledgeSearchRequest,
    KnowledgeServiceStatus,
)


class KnowledgeServiceError(RuntimeError):
    pass


class KnowledgeClient:
    def __init__(
        self,
        *,
        url: str | None = None,
        token: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        candidate = (url or os.getenv("KNOWLEDGE_SERVICE_URL") or "").strip().rstrip("/")
        if not candidate:
            raise KnowledgeServiceError(
                "KNOWLEDGE_SERVICE_URL is required before online discovery can search literature"
            )
        parsed = urlsplit(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise KnowledgeServiceError("KNOWLEDGE_SERVICE_URL must be an http:// or https:// URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise KnowledgeServiceError(
                "KNOWLEDGE_SERVICE_URL cannot contain credentials, query, or fragment"
            )
        self.url = candidate
        self.token = token if token is not None else os.getenv("KNOWLEDGE_SERVICE_TOKEN")
        self.transport = transport

    def _headers(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    async def status(self) -> KnowledgeServiceStatus:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            transport=self.transport,
        ) as client:
            try:
                response = await client.get(f"{self.url}/v1/health")
                response.raise_for_status()
            except httpx.HTTPError as error:
                raise KnowledgeServiceError(
                    f"knowledge service health check failed: {type(error).__name__}"
                ) from error
        return KnowledgeServiceStatus.model_validate(response.json())

    async def catalog(
        self,
        *,
        query: str = "",
        fulltext_only: bool = False,
        readable_only: bool = False,
        offset: int = 0,
        limit: int = 20,
    ) -> KnowledgeCatalogPage:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            transport=self.transport,
        ) as client:
            try:
                response = await client.get(
                    f"{self.url}/v1/catalog",
                    headers=self._headers(),
                    params={
                        "query": query,
                        "fulltext_only": str(fulltext_only).casefold(),
                        "readable_only": str(readable_only).casefold(),
                        "offset": offset,
                        "limit": limit,
                    },
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as error:
                detail = ""
                try:
                    detail = str(error.response.json().get("detail") or "")
                except (TypeError, ValueError):
                    pass
                raise KnowledgeServiceError(
                    f"knowledge catalog failed with HTTP {error.response.status_code}"
                    + (f": {detail}" if detail else "")
                ) from error
            except httpx.HTTPError as error:
                raise KnowledgeServiceError(
                    f"knowledge catalog transport failed: {type(error).__name__}"
                ) from error
        return KnowledgeCatalogPage.model_validate(response.json())

    async def document_text(
        self,
        document_id: str,
        *,
        offset: int = 0,
        limit: int = 30_000,
    ) -> KnowledgeDocumentTextSlice:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            transport=self.transport,
        ) as client:
            try:
                response = await client.get(
                    f"{self.url}/v1/catalog/{quote(document_id, safe='')}/text",
                    headers=self._headers(),
                    params={"offset": offset, "limit": limit},
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as error:
                detail = ""
                try:
                    detail = str(error.response.json().get("detail") or "")
                except (TypeError, ValueError):
                    pass
                raise KnowledgeServiceError(
                    f"knowledge document reading failed with HTTP {error.response.status_code}"
                    + (f": {detail}" if detail else "")
                ) from error
            except httpx.HTTPError as error:
                raise KnowledgeServiceError(
                    f"knowledge document reading transport failed: {type(error).__name__}"
                ) from error
        return KnowledgeDocumentTextSlice.model_validate(response.json())

    async def search(self, request: KnowledgeSearchRequest) -> EvidenceBundle:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=30.0),
            transport=self.transport,
        ) as client:
            try:
                response = await client.post(
                    f"{self.url}/v1/search",
                    headers=self._headers(),
                    json=request.model_dump(mode="json"),
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as error:
                detail = ""
                try:
                    detail = str(error.response.json().get("detail") or "")
                except (TypeError, ValueError):
                    pass
                raise KnowledgeServiceError(
                    f"knowledge search failed with HTTP {error.response.status_code}"
                    + (f": {detail}" if detail else "")
                ) from error
            except httpx.HTTPError as error:
                raise KnowledgeServiceError(
                    f"knowledge search transport failed: {type(error).__name__}"
                ) from error
        return EvidenceBundle.model_validate(response.json())

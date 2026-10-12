import asyncio
import httpx
from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from ..db import session
from .models import ConnectionCheck, LLMCall
from .service import get_llm

router = APIRouter(prefix="/api/settings")


async def probe(url, params):
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
        return {"status": "ok"}
    except httpx.HTTPStatusError as exc:
        return {"status": "failed", "reason": f"HTTP {exc.response.status_code}"}
    except httpx.HTTPError as exc:
        return {"status": "failed", "reason": f"网络请求失败（{type(exc).__name__}）"}


@router.get("/status")
async def status(request: Request, db: Session = Depends(session)):
    settings = request.app.state.settings
    usage = db.execute(select(func.count(LLMCall.id), func.sum(LLMCall.input_tokens), func.sum(LLMCall.output_tokens))).one()
    calls = db.scalars(select(LLMCall).order_by(LLMCall.created_at.desc()).limit(20)).all()
    sources = await asyncio.gather(
        probe(settings.openalex_url, {"per_page": 1, "mailto": settings.contact_email}),
        probe(settings.crossref_url, {"rows": 1, "mailto": settings.contact_email}),
    )
    return {"configured": bool(settings.dashscope_api_key and settings.qwen_model), "model": settings.qwen_model,
            "message": "已配置，请测试连接" if settings.dashscope_api_key and settings.qwen_model else "尚未配置模型密钥或模型名",
            "usage": {"calls": usage[0], "input_tokens": usage[1] or 0, "output_tokens": usage[2] or 0},
            "sources": dict(zip(["openalex", "crossref"], sources)),
            "recent_calls": [{c.name: getattr(call, c.name) for c in LLMCall.__table__.columns} for call in calls]}


@router.post("/llm:test")
async def test_connection(llm=Depends(get_llm)):
    return await llm.generate("connection_test", {}, ConnectionCheck)

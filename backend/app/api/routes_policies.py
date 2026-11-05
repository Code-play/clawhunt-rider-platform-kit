"""政策知识库检索端点：回答必须带出处（文档名+版本），无命中转人工。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_db, get_settings, require_permission
from app.config import Settings
from app.db.database import Database
from app.security.tokens import EmployeeContext
from app.services import policies

router = APIRouter(prefix="/policies", tags=["policies"])


@router.get("/search")
async def search_policies(
    q: str = Query(min_length=1, max_length=256),
    employee: EmployeeContext = Depends(require_permission("policy:read")),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    result = await policies.search_policies(
        db, q, min_score=settings.policy_min_score, top_k=settings.policy_top_k
    )
    # 每条回答都必须带出处：文档名 + 版本（缺失则视为不可引用）
    for item in result["items"]:
        assert item["doc_name"] and item["doc_version"]
    return result

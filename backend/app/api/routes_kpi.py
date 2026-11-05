"""KPI 端点：只读 SQL 视图 kpi_summary（与视图同源，页面不得另算）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_db, require_permission
from app.db.database import Database
from app.security.tokens import EmployeeContext
from app.services import kpi as kpi_service

router = APIRouter(prefix="/kpi", tags=["kpi"])


@router.get("/summary")
async def get_kpi_summary(
    employee: EmployeeContext = Depends(require_permission("kpi:read")),
    db: Database = Depends(get_db),
) -> dict:
    metrics = await kpi_service.get_kpi_summary(db)
    return {
        "metrics": metrics,
        "source": "kpi_summary",
        "definition": "全部指标由数据库视图 kpi_summary 单点定义，API 仅原样读数",
    }

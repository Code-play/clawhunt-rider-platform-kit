"""管理端契约 v1 兼容端点（admin 前端使用，JWT + 数据域）。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.api.deps import (
    get_clock,
    get_db,
    get_vault,
    require_permission,
    require_roles,
)
from app.db.database import Database
from app.errors import bad_request
from app.models.schemas import (
    AdminCandidateActionRequest,
    AdminCandidatePatchRequest,
    StationQuotaPatch,
)
from app.security.tokens import EmployeeContext
from app.security.vault import Vault
from app.services import admin as admin_service
from app.services import stations as station_service

router = APIRouter(prefix="/admin", tags=["admin-compat"])


@router.get("/candidates")
async def list_candidates(
    employee: EmployeeContext = Depends(require_permission("candidate:read")),
    db: Database = Depends(get_db),
    vault: Vault = Depends(get_vault),
    q: str | None = Query(default=None, max_length=64),
    status: str | None = Query(default=None),
    source_channel: str | None = Query(default=None),
    station_id: str | None = Query(default=None),
    intent_level: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
) -> dict:
    return await admin_service.admin_list_candidates(
        db,
        vault,
        employee,
        q=q,
        status=status,
        source_channel=source_channel,
        station_id=station_id,
        intent_level=intent_level,
        page=page,
        page_size=page_size,
    )


@router.get("/candidates/{candidate_id}")
async def get_candidate_detail(
    candidate_id: str,
    employee: EmployeeContext = Depends(require_permission("candidate:read")),
    db: Database = Depends(get_db),
    vault: Vault = Depends(get_vault),
    clock: object = Depends(get_clock),
) -> dict:
    return await admin_service.admin_candidate_detail(db, vault, employee, candidate_id, clock)


@router.patch("/candidates/{candidate_id}")
async def patch_candidate(
    candidate_id: str,
    body: AdminCandidatePatchRequest,
    employee: EmployeeContext = Depends(require_permission("candidate:write")),
    db: Database = Depends(get_db),
    vault: Vault = Depends(get_vault),
    clock: object = Depends(get_clock),
) -> dict:
    return await admin_service.admin_patch_candidate(
        db,
        vault,
        clock,
        employee,
        candidate_id,
        fields=body.fields,
        reason=body.reason,
    )


@router.post("/candidates/{candidate_id}/actions")
async def candidate_action(
    candidate_id: str,
    body: AdminCandidateActionRequest,
    employee: EmployeeContext = Depends(require_permission("candidate:write")),
    db: Database = Depends(get_db),
    vault: Vault = Depends(get_vault),
    clock: object = Depends(get_clock),
) -> dict:
    return await admin_service.admin_candidate_action(
        db,
        vault,
        clock,
        employee,
        candidate_id,
        action=body.action,
        reason=body.reason,
        slot_start=body.slot_start,
        fields=body.fields,
    )


def _parse_dt(value: str | None, field: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise bad_request("invalid_datetime", f"{field} 必须是 ISO 8601 时间") from exc
    return parsed


@router.get("/interviews")
async def list_interviews(
    employee: EmployeeContext = Depends(require_permission("candidate:read")),
    db: Database = Depends(get_db),
    vault: Vault = Depends(get_vault),
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    candidate_id: str | None = Query(default=None),
) -> dict:
    return await admin_service.admin_interviews(
        db,
        vault,
        employee=employee,
        from_=_parse_dt(from_, "from"),
        to=_parse_dt(to, "to"),
        candidate_id=candidate_id,
    )


@router.get("/stations")
async def list_stations(
    employee: EmployeeContext = Depends(require_permission("candidate:read")),
    db: Database = Depends(get_db),
    clock: object = Depends(get_clock),
) -> dict:
    items = await station_service.list_stations(db, clock, employee=employee)
    return {"stations": items, "items": items, "total": len(items)}


@router.patch("/stations/{station_id}")
async def patch_station(
    station_id: str,
    body: StationQuotaPatch,
    employee: EmployeeContext = Depends(require_roles("admin", "city_manager")),
    db: Database = Depends(get_db),
    clock: object = Depends(get_clock),
) -> dict:
    from app.errors import not_found, parse_uuid

    station = await db.fetchrow(
        "SELECT * FROM stations WHERE id = $1", str(parse_uuid(station_id, "站点不存在"))
    )
    if station is None:
        raise not_found("站点不存在")
    if employee.city != "*" and station["city"] != employee.city:
        from app.errors import forbidden

        raise forbidden("城市数据域外，禁止调整名额")
    return await admin_service.update_station_quota(
        db, clock, station_id, body.open_quota, employee.username
    )


@router.get("/metrics")
async def get_metrics(
    employee: EmployeeContext = Depends(require_permission("kpi:read")),
    db: Database = Depends(get_db),
) -> dict:
    return await admin_service.admin_metrics(db)


@router.get("/audit/detokenize")
async def detokenize_logs(
    employee: EmployeeContext = Depends(require_permission("vault:detokenize")),
    db: Database = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    return await admin_service.detokenize_logs(db, limit=limit)

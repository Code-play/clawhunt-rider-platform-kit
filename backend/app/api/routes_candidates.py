"""候选人端点：员工端走 Bearer JWT + 数据域；H5 自助走「候选人 id 即 capability」。

H5 只需 GET/PATCH 档案、导出副本、撤回删除，均不携带员工 JWT。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api.deps import (
    get_clock,
    get_db,
    get_settings,
    get_vault,
    optional_employee,
    require_permission,
)
from app.config import Settings
from app.db.database import Database
from app.errors import forbidden
from app.models.schemas import CandidateCreate, CandidatePatch, RevokeRequest, StatusUpdate
from app.security.tokens import EmployeeContext
from app.security.vault import Vault
from app.services import audit, candidates as candidate_service

router = APIRouter(prefix="/candidates", tags=["candidates"])


async def _public_one(db: Database, vault: Vault, row: dict[str, Any]) -> dict[str, Any]:
    return (await candidate_service.reveal_candidates(db, vault, [row]))[0]


def _assert_create_scope(employee: EmployeeContext, city: str, station_id: str | None) -> None:
    if employee.city != "*" and city != employee.city:
        raise forbidden("城市数据域外，禁止写入")
    if employee.role == "station_operator" and (
        station_id is None or station_id not in employee.station_ids
    ):
        raise forbidden("站点数据域外，禁止写入")


async def _load_for_reader(
    db: Database, employee: EmployeeContext | None, candidate_id: str
) -> dict[str, Any]:
    if employee is None:
        return await candidate_service.get_candidate_any(db, candidate_id)
    return await candidate_service.get_candidate_for_employee(db, employee, candidate_id)


@router.post("", status_code=201)
async def create_candidate(
    body: CandidateCreate,
    employee: EmployeeContext = Depends(require_permission("candidate:write")),
    db: Database = Depends(get_db),
    vault: Vault = Depends(get_vault),
    clock: object = Depends(get_clock),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    city = body.city
    if body.station_id and not city:
        from app.errors import parse_uuid

        station = await db.fetchrow(
            "SELECT city FROM stations WHERE id = $1",
            str(parse_uuid(body.station_id, "站点不存在")),
        )
        city = station["city"] if station else None
    _assert_create_scope(employee, city or "上海", body.station_id)
    row = await candidate_service.create_candidate(
        db,
        vault,
        settings,
        clock,
        name=body.name,
        phone=body.phone,
        actor=employee.username,
        birth_ym=body.birth_ym,
        area_text=body.area_text,
        job_type=body.job_type,
        has_ebike=body.has_ebike,
        start_text=body.start_text,
        experience_text=body.experience_text,
        health_cert=body.health_cert,
        source_channel=body.source_channel,
        station_id=body.station_id,
        city=city,
        consent_version=body.consent_version,
    )
    return await _public_one(db, vault, row)


@router.get("")
async def list_candidates(
    employee: EmployeeContext = Depends(require_permission("candidate:read")),
    db: Database = Depends(get_db),
    vault: Vault = Depends(get_vault),
    status: str | None = Query(default=None),
    city: str | None = Query(default=None),
    station_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return await candidate_service.list_candidates(
        db,
        vault,
        employee,
        status=status,
        city=city,
        station_id=station_id,
        limit=limit,
        offset=offset,
    )


@router.get("/{candidate_id}")
async def get_candidate(
    candidate_id: str,
    employee: EmployeeContext | None = Depends(optional_employee),
    db: Database = Depends(get_db),
    vault: Vault = Depends(get_vault),
) -> dict[str, Any]:
    row = await _load_for_reader(db, employee, candidate_id)
    return await _public_one(db, vault, row)


@router.patch("/{candidate_id}")
async def patch_candidate(
    candidate_id: str,
    body: CandidatePatch,
    employee: EmployeeContext | None = Depends(optional_employee),
    db: Database = Depends(get_db),
    vault: Vault = Depends(get_vault),
    clock: object = Depends(get_clock),
) -> dict[str, Any]:
    updates = body.model_dump(exclude_unset=True)
    if employee is not None:
        candidate_service.assert_can_write(employee)
        row = await candidate_service.get_candidate_for_employee(db, employee, candidate_id)
        updated = await candidate_service.update_candidate_fields(
            db, vault, clock, candidate=row, updates=updates, actor=employee.username
        )
    else:
        updated = await candidate_service.update_self_service(
            db, vault, clock, candidate_id=candidate_id, updates=updates
        )
    return await _public_one(db, vault, updated)


@router.post("/{candidate_id}/status")
async def update_candidate_status(
    candidate_id: str,
    body: StatusUpdate,
    employee: EmployeeContext = Depends(require_permission("candidate:write")),
    db: Database = Depends(get_db),
    vault: Vault = Depends(get_vault),
    clock: object = Depends(get_clock),
) -> dict[str, Any]:
    row = await candidate_service.get_candidate_for_employee(db, employee, candidate_id)
    updated = await candidate_service.update_status(
        db, clock, candidate=row, target_status=body.status, actor=employee.username
    )
    return await _public_one(db, vault, updated)


@router.get("/{candidate_id}/export")
async def export_candidate(
    candidate_id: str,
    include_real: bool = Query(default=False),
    employee: EmployeeContext | None = Depends(optional_employee),
    db: Database = Depends(get_db),
    vault: Vault = Depends(get_vault),
) -> dict[str, Any]:
    candidate = await _load_for_reader(db, employee, candidate_id)
    can_view_real = bool(employee is not None and employee.has("vault:detokenize"))
    if include_real and employee is not None:
        async with db.transaction() as conn:
            await audit.append_audit(
                conn,
                actor=employee.username,
                action="candidate.export",
                resource=f"candidate:{candidate_id}",
                payload={"include_real": True, "reason": "导出完整副本"},
            )
    return await candidate_service.export_candidate(
        db,
        vault,
        candidate_id=candidate["id"],
        include_real=include_real,
        can_view_real=can_view_real,
    )


@router.post("/{candidate_id}/revoke")
async def revoke_candidate(
    candidate_id: str,
    body: RevokeRequest | None = None,
    employee: EmployeeContext | None = Depends(optional_employee),
    db: Database = Depends(get_db),
    clock: object = Depends(get_clock),
) -> dict[str, Any]:
    if employee is not None:
        await candidate_service.get_candidate_for_employee(db, employee, candidate_id)
        actor = employee.username
    else:
        await candidate_service.get_candidate_any(db, candidate_id)
        actor = "candidate:self"
    return await candidate_service.revoke_candidate(
        db, clock, candidate_id=candidate_id, actor=actor,
        reason=body.reason if body else None,
    )

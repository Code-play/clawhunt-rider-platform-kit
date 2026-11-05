"""预约端点：库级原子扣名额（不超卖）；H5 无 JWT 可用，员工端走数据域校验。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_clock, get_db, optional_employee, require_permission
from app.db.database import Database
from app.errors import bad_request, forbidden, not_found
from app.models.schemas import BookingCancelRequest, BookingCreate, BookingPatchRequest
from app.security.tokens import EmployeeContext
from app.services import bookings as booking_service
from app.services import candidates as candidate_service
from app.services import stations as station_service

router = APIRouter(prefix="/bookings", tags=["bookings"])


async def _candidate_for_actor(
    db: Database, employee: EmployeeContext | None, candidate_id: str
) -> dict:
    if employee is None:
        return await candidate_service.get_candidate_any(db, candidate_id)
    return await candidate_service.get_candidate_for_employee(db, employee, candidate_id)


def _assert_station_scope(employee: EmployeeContext | None, station: dict) -> None:
    if employee is None:
        return
    if employee.city != "*" and station["city"] != employee.city:
        raise forbidden("城市数据域外，禁止操作该站点")
    if employee.role == "station_operator" and str(station["id"]) not in employee.station_ids:
        raise forbidden("站点数据域外，禁止操作该站点")


async def _with_station(db: Database, clock: object, booking: dict) -> dict:
    station = await db.fetchrow("SELECT * FROM stations WHERE id = $1", booking["station_id"])
    if station is not None:
        booking["station"] = await station_service.station_payload(db, dict(station), clock)
    return booking


@router.post("", status_code=201)
async def create_booking(
    body: BookingCreate,
    employee: EmployeeContext | None = Depends(optional_employee),
    db: Database = Depends(get_db),
    clock: object = Depends(get_clock),
) -> dict:
    candidate = await _candidate_for_actor(db, employee, body.candidate_id)
    from app.errors import parse_uuid

    station = await db.fetchrow(
        "SELECT * FROM stations WHERE id = $1", str(parse_uuid(body.station_id, "站点不存在"))
    )
    if station is None:
        raise not_found("站点不存在")
    _assert_station_scope(employee, dict(station))
    booking = await booking_service.create_booking(
        db,
        clock,
        candidate=candidate,
        station_id=body.station_id,
        slot_start=body.slot_start,
        actor=employee.username if employee else "candidate:self",
    )
    return await _with_station(db, clock, booking)


@router.get("")
async def list_bookings(
    employee: EmployeeContext | None = Depends(optional_employee),
    db: Database = Depends(get_db),
    candidate_id: str | None = None,
    limit: int = 50,
) -> dict:
    if employee is None and not candidate_id:
        raise forbidden("匿名请求必须指定 candidate_id")
    if candidate_id:
        await _candidate_for_actor(db, employee, candidate_id)
    items = await booking_service.list_bookings(db, candidate_id=candidate_id, limit=limit)
    return {"items": items, "total": len(items)}


@router.get("/{booking_id}")
async def get_booking(
    booking_id: str,
    employee: EmployeeContext | None = Depends(optional_employee),
    db: Database = Depends(get_db),
    clock: object = Depends(get_clock),
) -> dict:
    booking = await booking_service.get_booking(db, booking_id)
    await _candidate_for_actor(db, employee, booking["candidate_id"])
    return await _with_station(db, clock, booking)


@router.patch("/{booking_id}")
async def patch_booking(
    booking_id: str,
    body: BookingPatchRequest,
    employee: EmployeeContext | None = Depends(optional_employee),
    db: Database = Depends(get_db),
    clock: object = Depends(get_clock),
) -> dict:
    booking = await booking_service.get_booking(db, booking_id)
    await _candidate_for_actor(db, employee, booking["candidate_id"])
    if body.slot_start is not None:
        updated = await booking_service.reschedule_booking(
            db,
            clock,
            booking_id=booking_id,
            slot_start=body.slot_start,
            actor=employee.username if employee else "candidate:self",
        )
        return await _with_station(db, clock, updated)
    if body.status is not None:
        if employee is None or not employee.has("booking:write"):
            raise forbidden("到面登记需要员工权限")
        updated = await booking_service.set_booking_status(
            db, clock, booking_id=booking_id, status=body.status, actor=employee.username
        )
        return await _with_station(db, clock, updated)
    raise bad_request("no_changes", "请提供 slot_start（改约）或 status（到面登记）")


@router.post("/{booking_id}/cancel")
async def cancel_booking(
    booking_id: str,
    body: BookingCancelRequest | None = None,
    employee: EmployeeContext | None = Depends(optional_employee),
    db: Database = Depends(get_db),
    clock: object = Depends(get_clock),
) -> dict:
    booking = await booking_service.get_booking(db, booking_id)
    await _candidate_for_actor(db, employee, booking["candidate_id"])
    updated = await booking_service.cancel_booking(
        db,
        clock,
        booking_id=booking_id,
        actor=employee.username if employee else "candidate:self",
        reason=body.reason if body else None,
    )
    return await _with_station(db, clock, updated)

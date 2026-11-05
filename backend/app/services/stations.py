"""站点读取与展示载荷（H5 站点卡需要 distance/已约/可约时段；管理端需要名额）。"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.security.tokens import EmployeeContext

SLOT_TIMES: tuple[tuple[int, int], ...] = ((9, 0), (13, 30), (16, 0))
SLOT_DAYS = 3


async def build_station_slots(db: Any, station: dict[str, Any], clock: Any) -> list[dict[str, Any]]:
    """未来 3 天 x 3 个时段的档期；容量取站点 slot_capacity。"""
    now = clock.now()
    booked_rows = await db.fetch(
        """
        SELECT slot_start, count(*) AS booked
        FROM bookings
        WHERE station_id = $1 AND status = 'booked'
        GROUP BY slot_start
        """,
        station["id"],
    )
    booked_map = {row["slot_start"]: int(row["booked"]) for row in booked_rows}
    capacity = int(station.get("slot_capacity") or 3)
    slots: list[dict[str, Any]] = []
    for day_offset in range(1, SLOT_DAYS + 1):
        day = (now + timedelta(days=day_offset)).replace(hour=0, minute=0, second=0, microsecond=0)
        for hour, minute in SLOT_TIMES:
            slot_start = day.replace(hour=hour, minute=minute)
            booked = booked_map.get(slot_start, 0)
            slots.append(
                {
                    "slot_start": slot_start.isoformat(),
                    "capacity": capacity,
                    "booked": booked,
                    "available": booked < capacity,
                }
            )
    return slots


async def station_payload(db: Any, station: dict[str, Any], clock: Any) -> dict[str, Any]:
    booked_count = await db.fetchval(
        "SELECT count(*) FROM bookings WHERE station_id = $1 AND status = 'booked'",
        station["id"],
    )
    open_quota = int(station["open_quota"])
    return {
        "id": str(station["id"]),
        "name": station["name"],
        "city": station["city"],
        "area": station["area"],
        "address": station.get("address"),
        "lat": station.get("lat"),
        "lng": station.get("lng"),
        "distance_km": station.get("distance_km") or 0,
        "open_quota": open_quota,
        "booked_count": int(booked_count),
        "booked": int(booked_count),
        "remaining": open_quota,
        "status": "active" if open_quota > 0 else "full",
        "manager_virtual_no": station.get("manager_virtual_no"),
        "manager_display_no": station.get("manager_display_no"),
        "slots": await build_station_slots(db, station, clock),
    }


async def list_stations(
    db: Any,
    clock: Any,
    *,
    employee: EmployeeContext | None = None,
    only_available: bool = False,
) -> list[dict[str, Any]]:
    rows = await db.fetch(
        """
        SELECT * FROM stations
        WHERE ($1::text = '*' OR city = $1)
          AND ($2::uuid[] IS NULL OR id = ANY($2))
          AND ($3::boolean IS FALSE OR open_quota > 0)
        ORDER BY distance_km, name
        """,
        employee.city if employee else "*",
        list(employee.station_ids)
        if employee is not None and employee.role == "station_operator" and employee.station_ids
        else None,
        only_available,
    )
    return [await station_payload(db, dict(row), clock) for row in rows]


async def get_station(db: Any, clock: Any, station_id: str) -> dict[str, Any]:
    from app.errors import not_found, parse_uuid

    row = await db.fetchrow("SELECT * FROM stations WHERE id = $1", str(parse_uuid(station_id, "站点不存在")))
    if row is None:
        raise not_found("站点不存在")
    return await station_payload(db, dict(row), clock)


async def assignable_stations(db: Any, employee: EmployeeContext | None = None) -> list[dict[str, Any]]:
    """分派规则可用站点：按名称稳定排序。"""
    rows = await db.fetch(
        """
        SELECT id, name, city, area, open_quota
        FROM stations
        WHERE ($1::text = '*' OR city = $1)
        ORDER BY distance_km, name
        """,
        employee.city if employee else "*",
    )
    return [dict(row) for row in rows]

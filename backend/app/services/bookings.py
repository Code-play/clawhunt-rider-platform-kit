"""预约：库级原子扣名额（条件 UPDATE），绝不应用层「先查后写」。"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from contextlib import asynccontextmanager

import asyncpg

from app.errors import conflict, not_found, parse_uuid
from app.events import outbox
from app.services import audit


@asynccontextmanager
async def _maybe_transaction(db: Any, conn: Any | None):
    """有外部连接时复用其事务（避免同连接/跨连接重复加锁导致死锁）。"""
    if conn is not None:
        yield conn
    else:
        async with db.transaction() as tx:
            yield tx


def _booking_public(row: asyncpg.Record | dict[str, Any]) -> dict[str, Any]:
    updated_at = row.get("updated_at") if isinstance(row, dict) else row["updated_at"]
    return {
        "id": str(row["id"]),
        "candidate_id": str(row["candidate_id"]),
        "station_id": str(row["station_id"]),
        "slot_start": row["slot_start"].isoformat(),
        "slot_label": row["slot_start"].isoformat(),
        "status": row["status"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": (updated_at or row["created_at"]).isoformat(),
    }


async def get_booking(db: Any, booking_id: str) -> dict[str, Any]:
    from app.errors import parse_uuid

    row = await db.fetchrow("SELECT * FROM bookings WHERE id = $1", str(parse_uuid(booking_id)))
    if row is None:
        raise not_found("预约不存在")
    return _booking_public(row)


async def create_booking(
    db: Any,
    clock: Any,
    *,
    candidate: dict[str, Any],
    station_id: str,
    slot_start: datetime,
    actor: str,
    conn: Any | None = None,
) -> dict[str, Any]:
    now = clock.now()
    async with _maybe_transaction(db, conn) as conn:
        locked = await conn.fetchrow(
            "SELECT * FROM candidates WHERE id = $1 FOR UPDATE", candidate["id"]
        )
        if locked["status"] != "complete":
            raise conflict(
                "candidate_not_ready",
                f"候选人状态为 {locked['status']}，只有 complete 状态可以预约",
            )

        station = await conn.fetchrow(
            "SELECT * FROM stations WHERE id = $1 FOR UPDATE",
            str(parse_uuid(station_id, "站点不存在")),
        )
        if station is None:
            raise not_found("站点不存在")
        slot_booked = await conn.fetchval(
            """
            SELECT count(*) FROM bookings
            WHERE station_id = $1 AND slot_start = $2 AND status = 'booked'
            """,
            station["id"],
            slot_start,
        )
        if int(slot_booked) >= int(station["slot_capacity"] or 3):
            raise conflict("slot_full", "该时段已约满，请选择其他时段")
        station = await conn.fetchrow(
            """
            UPDATE stations
            SET open_quota = open_quota - 1
            WHERE id = $1 AND open_quota > 0
            RETURNING id, name, city, open_quota
            """,
            station["id"],
        )
        if station is None:
            exists = await conn.fetchval("SELECT 1 FROM stations WHERE id = $1", station_id)
            if not exists:
                raise not_found("站点不存在")
            raise conflict("sold_out", "该站点预约名额已满")

        try:
            booking = await conn.fetchrow(
                """
                INSERT INTO bookings (candidate_id, station_id, slot_start, status, created_at)
                VALUES ($1, $2, $3, 'booked', $4)
                RETURNING *
                """,
                locked["id"],
                station["id"],
                slot_start,
                now,
            )
        except asyncpg.UniqueViolationError as exc:
            raise conflict("duplicate_booking", "该候选人已有有效预约") from exc

        await conn.execute(
            """
            UPDATE candidates
            SET status = 'booked', station_id = $2, city = $3, updated_at = $4
            WHERE id = $1
            """,
            locked["id"],
            station["id"],
            station["city"],
            now,
        )
        payload = {
            "booking_id": str(booking["id"]),
            "candidate_id": str(locked["id"]),
            "station_id": str(station["id"]),
            "slot_start": slot_start.isoformat(),
        }
        await outbox.emit_event(
            conn,
            event_type="booking.created",
            aggregate_type="booking",
            aggregate_id=booking["id"],
            payload=payload,
            now=now,
        )
        await outbox.emit_event(
            conn,
            event_type="candidate.updated",
            aggregate_type="candidate",
            aggregate_id=locked["id"],
            payload={"candidate_id": str(locked["id"]), "status": "booked"},
            now=now,
        )
        await audit.append_audit(
            conn,
            actor=actor,
            action="booking.create",
            resource=f"booking:{booking['id']}",
            payload={"candidate_id": str(locked["id"]), "station_id": str(station["id"])},
        )
        return _booking_public(booking)


async def cancel_booking(
    db: Any, clock: Any, *, booking_id: str, actor: str, reason: str | None = None
) -> dict[str, Any]:
    now = clock.now()
    async with db.transaction() as conn:
        booking = await conn.fetchrow("SELECT * FROM bookings WHERE id = $1 FOR UPDATE", booking_id)
        if booking is None:
            raise not_found("预约不存在")
        if booking["status"] != "booked":
            raise conflict("invalid_booking_status", f"当前预约状态为 {booking['status']}，不可取消")
        await conn.execute(
            "UPDATE bookings SET status = 'cancelled', updated_at = $2 WHERE id = $1",
            booking_id,
            now,
        )
        await conn.execute(
            "UPDATE stations SET open_quota = open_quota + 1 WHERE id = $1", booking["station_id"]
        )
        candidate = await conn.fetchrow(
            "SELECT * FROM candidates WHERE id = $1 FOR UPDATE", booking["candidate_id"]
        )
        if candidate is not None and candidate["status"] == "booked":
            await conn.execute(
                "UPDATE candidates SET status = 'complete', updated_at = $2 WHERE id = $1",
                candidate["id"],
                now,
            )
        await outbox.emit_event(
            conn,
            event_type="booking.cancelled",
            aggregate_type="booking",
            aggregate_id=booking["id"],
            payload={
                "booking_id": str(booking["id"]),
                "candidate_id": str(booking["candidate_id"]),
                "reason": reason,
            },
            now=now,
        )
        await audit.append_audit(
            conn,
            actor=actor,
            action="booking.cancel",
            resource=f"booking:{booking['id']}",
            payload={"reason": reason},
        )
        updated = await conn.fetchrow("SELECT * FROM bookings WHERE id = $1", booking_id)
        return _booking_public(updated)


async def set_booking_status(
    db: Any, clock: Any, *, booking_id: str, status: str, actor: str
) -> dict[str, Any]:
    if status not in ("done", "no_show"):
        raise conflict("invalid_booking_status", "只支持 done / no_show")
    now = clock.now()
    async with db.transaction() as conn:
        booking = await conn.fetchrow("SELECT * FROM bookings WHERE id = $1 FOR UPDATE", booking_id)
        if booking is None:
            raise not_found("预约不存在")
        if booking["status"] != "booked":
            raise conflict("invalid_booking_status", f"当前预约状态为 {booking['status']}")
        updated = await conn.fetchrow(
            "UPDATE bookings SET status = $2, updated_at = $3 WHERE id = $1 RETURNING *",
            booking_id,
            status,
            now,
        )
        await audit.append_audit(
            conn,
            actor=actor,
            action="booking.attendance",
            resource=f"booking:{booking_id}",
            payload={"status": status},
        )
        return _booking_public(updated)


async def reschedule_booking(
    db: Any,
    clock: Any,
    *,
    booking_id: str,
    slot_start: datetime,
    actor: str,
) -> dict[str, Any]:
    """改约：只换时段，不改变站点名额（名额是站点级，不随时段增减）。"""
    now = clock.now()
    async with db.transaction() as conn:
        booking = await conn.fetchrow("SELECT * FROM bookings WHERE id = $1 FOR UPDATE", booking_id)
        if booking is None:
            raise not_found("预约不存在")
        if booking["status"] != "booked":
            raise conflict("invalid_booking_status", f"当前预约状态为 {booking['status']}，不支持改约")
        station = await conn.fetchrow(
            "SELECT * FROM stations WHERE id = $1 FOR UPDATE", booking["station_id"]
        )
        if station is None:
            raise not_found("站点不存在")
        if booking["slot_start"] != slot_start:
            slot_booked = await conn.fetchval(
                """
                SELECT count(*) FROM bookings
                WHERE station_id = $1 AND slot_start = $2 AND status = 'booked'
                """,
                station["id"],
                slot_start,
            )
            if int(slot_booked) >= int(station["slot_capacity"] or 3):
                raise conflict("slot_full", "该时段已约满，请选择其他时段")
        updated = await conn.fetchrow(
            "UPDATE bookings SET slot_start = $2, updated_at = $3 WHERE id = $1 RETURNING *",
            booking_id,
            slot_start,
            now,
        )
        await audit.append_audit(
            conn,
            actor=actor,
            action="booking.reschedule",
            resource=f"booking:{booking_id}",
            payload={
                "from": booking["slot_start"].isoformat(),
                "to": slot_start.isoformat(),
            },
        )
        return _booking_public(updated)


async def list_bookings(db: Any, *, candidate_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    rows = await db.fetch(
        """
        SELECT * FROM bookings
        WHERE ($1::uuid IS NULL OR candidate_id = $1)
        ORDER BY created_at DESC
        LIMIT $2
        """,
        candidate_id,
        limit,
    )
    return [_booking_public(row) for row in rows]

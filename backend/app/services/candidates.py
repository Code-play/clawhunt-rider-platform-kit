"""候选人领域：状态机、令牌化写入、掩码视图、数据域校验。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg

from app.errors import ApiError, conflict, forbidden, not_found
from app.security.masking import mask_name, mask_phone
from app.security.tokens import EmployeeContext
from app.security.vault import Vault
from app.services import audit
from app.events import outbox

CANDIDATE_STATUSES = (
    "new",
    "collecting",
    "complete",
    "booked",
    "interviewed",
    "hired",
    "rejected",
    "handoff",
)

# 状态机：唯一合法流转定义（测试会遍历全部 8x8 状态对）
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "new": frozenset({"collecting"}),
    "collecting": frozenset({"complete", "rejected", "handoff"}),
    "complete": frozenset({"booked", "rejected", "handoff"}),
    "booked": frozenset({"interviewed", "rejected", "complete", "handoff"}),
    "interviewed": frozenset({"hired", "rejected", "handoff"}),
    "hired": frozenset({"handoff"}),
    "handoff": frozenset(),
    "rejected": frozenset(),
}

TERMINAL_RETENTION_STATUSES = frozenset({"hired", "handoff"})

JOB_TYPES = ("fulltime", "parttime", "undecided")
HEALTH_CERT_VALUES = ("none", "holding", "processing", "unknown")
# 管理端历史字段值（yes/no/unsure）与契约枚举互转
HEALTH_CERT_ALIASES = {
    "yes": "holding",
    "no": "none",
    "unsure": "unknown",
    "none": "none",
    "holding": "holding",
    "processing": "processing",
    "unknown": "unknown",
}
HEALTH_CERT_DISPLAY = {"holding": "yes", "none": "no", "processing": "unsure", "unknown": "unsure"}


def is_transition_allowed(source: str, target: str) -> bool:
    return target in ALLOWED_TRANSITIONS.get(source, frozenset())


def age_in_years(birth_ym: str, now: datetime) -> int:
    year, month = (int(part) for part in birth_ym.split("-"))
    age = now.year - year
    if now.month < month:
        age -= 1
    return age


def is_minor(birth_ym: str | None, now: datetime) -> bool:
    if not birth_ym:
        return False
    return age_in_years(birth_ym, now) < 18


def retention_deadline(*, now: datetime, minor: bool, unhired_days: int, minor_hours: int) -> datetime:
    if minor:
        return now + timedelta(hours=minor_hours)
    return now + timedelta(days=unhired_days)


async def _resolve_city(
    conn: asyncpg.Connection, city: str | None, station_id: str | None
) -> tuple[str, str | None]:
    if station_id:
        station = await conn.fetchrow("SELECT id, city FROM stations WHERE id = $1", station_id)
        if station is None:
            raise not_found("站点不存在")
        return city or station["city"], str(station["id"])
    return city or "上海", None


async def create_candidate(
    db: Any,
    vault: Vault,
    settings: Any,
    clock: Any,
    *,
    name: str | None = None,
    phone: str | None = None,
    name_token: str | None = None,
    phone_token: str | None = None,
    actor: str,
    birth_ym: str | None = None,
    area_text: str | None = None,
    job_type: str | None = None,
    has_ebike: bool | None = None,
    start_text: str | None = None,
    experience_text: str | None = None,
    health_cert: str | None = None,
    source_channel: str = "manual",
    station_id: str | None = None,
    city: str | None = None,
    status: str = "new",
    consent_version: str = "v1",
    consent_at: datetime | None = None,
) -> dict[str, Any]:
    now = clock.now()
    async with db.transaction() as conn:
        city_value, station_value = await _resolve_city(conn, city, station_id)
        if name_token is None and name:
            name_token = await vault.tokenize(conn, "name", name)
        if phone_token is None and phone:
            phone_token = await vault.tokenize(conn, "phone", phone)
        minor = is_minor(birth_ym, now)
        retention_until = (
            None
            if status in TERMINAL_RETENTION_STATUSES
            else retention_deadline(
                now=now,
                minor=minor,
                unhired_days=settings.retention_unhired_days,
                minor_hours=settings.retention_minor_hours,
            )
        )
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO candidates
                    (name_token, phone_token, birth_ym, area_text, job_type, has_ebike, start_text,
                     experience_text, health_cert, source_channel, station_id, city, status, is_minor,
                     consent_version, consent_at, retention_until, created_at, updated_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$16,$16)
                RETURNING *
                """,
                name_token,
                phone_token,
                birth_ym,
                area_text,
                job_type,
                has_ebike,
                start_text,
                experience_text,
                health_cert or "unknown",
                source_channel,
                station_value,
                city_value,
                status,
                minor,
                consent_version,
                consent_at or now,
                retention_until,
            )
        except asyncpg.UniqueViolationError as exc:
            raise conflict("duplicate_candidate", "该手机号已存在候选人记录") from exc

        await outbox.emit_event(
            conn,
            event_type="candidate.created",
            aggregate_type="candidate",
            aggregate_id=row["id"],
            payload={
                "candidate_id": str(row["id"]),
                "status": row["status"],
                "station_id": str(row["station_id"]) if row["station_id"] else None,
                "city": row["city"],
                "source_channel": row["source_channel"],
            },
            now=now,
        )
        await audit.append_audit(
            conn,
            actor=actor,
            action="candidate.create",
            resource=f"candidate:{row['id']}",
            payload={"source_channel": source_channel, "city": city_value},
        )
        return dict(row)


async def fetch_candidate(conn: asyncpg.Connection, candidate_id: str) -> dict[str, Any] | None:
    from app.errors import parse_uuid

    row = await conn.fetchrow("SELECT * FROM candidates WHERE id = $1", str(parse_uuid(candidate_id)))
    return dict(row) if row else None


def assert_can_access(employee: EmployeeContext, candidate: dict[str, Any]) -> None:
    if not employee.can_access_city(candidate["city"]):
        raise not_found("候选人不存在")
    if not employee.can_access_station(
        str(candidate["station_id"]) if candidate["station_id"] else None
    ):
        raise not_found("候选人不存在")


async def get_candidate_for_employee(
    db: Any, employee: EmployeeContext, candidate_id: str
) -> dict[str, Any]:
    candidate = await fetch_candidate(db, candidate_id)
    if candidate is None:
        raise not_found("候选人不存在")
    assert_can_access(employee, candidate)
    return candidate


async def reveal_candidates(
    db: Any, vault: Vault, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    tokens: list[str] = []
    for row in rows:
        if row.get("name_token"):
            tokens.append(row["name_token"])
        if row.get("phone_token"):
            tokens.append(row["phone_token"])
    ciphertexts = await vault.fetch_ciphertexts(db, tokens)
    public_rows = []
    for row in rows:
        name = vault.decrypt_ciphertext(ciphertexts.get(row.get("name_token") or "")) or ""
        phone = vault.decrypt_ciphertext(ciphertexts.get(row.get("phone_token") or "")) or ""
        public_rows.append(to_public(row, name=name, phone=phone))
    return public_rows


def to_public(row: dict[str, Any], *, name: str, phone: str) -> dict[str, Any]:
    name_masked = mask_name(name) if name else "**"
    phone_masked = mask_phone(phone) if phone else "***"
    return {
        "id": str(row["id"]),
        "name": name_masked,
        "name_masked": name_masked,
        "phone": phone_masked,
        "phone_masked": phone_masked,
        "name_token": row["name_token"],
        "phone_token": row["phone_token"],
        "birth_ym": row["birth_ym"],
        "area_text": row["area_text"],
        "job_type": row["job_type"],
        "has_ebike": row["has_ebike"],
        "start_text": row["start_text"],
        "experience_text": row["experience_text"],
        "health_cert": row["health_cert"],
        "source_channel": row["source_channel"],
        "station_id": str(row["station_id"]) if row["station_id"] else None,
        "city": row["city"],
        "status": row["status"],
        "profile_complete": row["profile_complete"],
        "consent_version": row["consent_version"],
        "consent_at": row["consent_at"].isoformat() if row["consent_at"] else None,
        "retention_until": row["retention_until"].isoformat() if row["retention_until"] else None,
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


async def list_candidates(
    db: Any,
    vault: Vault,
    employee: EmployeeContext,
    *,
    status: str | None = None,
    city: str | None = None,
    station_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    if status is not None and status not in CANDIDATE_STATUSES:
        raise ApiError(422, "invalid_status", f"未知状态: {status}")
    scope_city = employee.city
    city_filter = city if city and scope_city == "*" else scope_city
    rows = await db.fetch(
        """
        SELECT * FROM candidates
        WHERE ($1::text = '*' OR city = $1)
          AND ($2::text IS NULL OR status = $2)
          AND ($3::uuid IS NULL OR station_id = $3)
          AND ($4::uuid[] IS NULL OR station_id = ANY($4))
        ORDER BY created_at DESC, id
        LIMIT $5 OFFSET $6
        """,
        city_filter,
        status,
        station_id,
        list(employee.station_ids) if employee.role == "station_operator" and employee.station_ids else None,
        limit,
        offset,
    )
    total = await db.fetchval(
        """
        SELECT count(*) FROM candidates
        WHERE ($1::text = '*' OR city = $1)
          AND ($2::text IS NULL OR status = $2)
          AND ($3::uuid IS NULL OR station_id = $3)
          AND ($4::uuid[] IS NULL OR station_id = ANY($4))
        """,
        city_filter,
        status,
        station_id,
        list(employee.station_ids) if employee.role == "station_operator" and employee.station_ids else None,
    )
    items = await reveal_candidates(db, vault, [dict(row) for row in rows])
    return {"items": items, "total": int(total), "limit": limit, "offset": offset}


async def update_status(
    db: Any,
    clock: Any,
    *,
    candidate: dict[str, Any],
    target_status: str,
    actor: str,
) -> dict[str, Any]:
    if target_status not in CANDIDATE_STATUSES:
        raise ApiError(422, "invalid_status", f"未知状态: {target_status}")
    source_status = candidate["status"]
    if not is_transition_allowed(source_status, target_status):
        raise conflict(
            "invalid_transition", f"非法状态流转: {source_status} -> {target_status}"
        )
    now = clock.now()
    async with db.transaction() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM candidates WHERE id = $1 FOR UPDATE", candidate["id"]
        )
        if row["status"] != source_status:  # 并发下状态已变化
            raise conflict("stale_transition", "候选状态已被其他请求修改，请重试")
        retention_until = (
            None if target_status in TERMINAL_RETENTION_STATUSES else row["retention_until"]
        )
        updated = await conn.fetchrow(
            """
            UPDATE candidates
            SET status = $2, retention_until = $3, updated_at = $4
            WHERE id = $1
            RETURNING *
            """,
            row["id"],
            target_status,
            retention_until,
            now,
        )
        event_type = {
            "complete": "candidate.completed",
            "handoff": "handoff.requested",
        }.get(target_status, "candidate.updated")
        await outbox.emit_event(
            conn,
            event_type=event_type,
            aggregate_type="candidate",
            aggregate_id=row["id"],
            payload={
                "candidate_id": str(row["id"]),
                "from_status": source_status,
                "to_status": target_status,
            },
            now=now,
        )
        await audit.append_audit(
            conn,
            actor=actor,
            action="candidate.status.update",
            resource=f"candidate:{row['id']}",
            payload={"from": source_status, "to": target_status},
        )
        return dict(updated)


async def update_candidate_fields(
    db: Any,
    vault: Vault,
    clock: Any,
    *,
    candidate: dict[str, Any],
    updates: dict[str, Any],
    actor: str,
    reason: str | None = None,
) -> dict[str, Any]:
    allowed = {
        "birth_ym",
        "area_text",
        "job_type",
        "has_ebike",
        "start_text",
        "experience_text",
        "health_cert",
        "station_id",
        "city",
        "name",
        "phone",
    }
    unknown = set(updates) - allowed
    if unknown:
        raise ApiError(422, "invalid_field", f"不允许更新的字段: {', '.join(sorted(unknown))}")

    now = clock.now()
    async with db.transaction() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM candidates WHERE id = $1 FOR UPDATE", candidate["id"]
        )
        values: dict[str, Any] = {}
        if "birth_ym" in updates:
            values["birth_ym"] = updates["birth_ym"]
            values["is_minor"] = is_minor(updates["birth_ym"], now)
        for field in ("area_text", "job_type", "has_ebike", "start_text", "experience_text", "city"):
            if field in updates:
                values[field] = updates[field]
        if "name" in updates and updates["name"]:
            values["name_token"] = await vault.tokenize(conn, "name", updates["name"])
        if "phone" in updates and updates["phone"]:
            values["phone_token"] = await vault.tokenize(conn, "phone", updates["phone"])
        if "health_cert" in updates and updates["health_cert"] is not None:
            values["health_cert"] = HEALTH_CERT_ALIASES.get(
                str(updates["health_cert"]).lower(), str(updates["health_cert"])
            )
        if "station_id" in updates:
            if updates["station_id"]:
                station = await conn.fetchrow(
                    "SELECT id, city FROM stations WHERE id = $1", updates["station_id"]
                )
                if station is None:
                    raise not_found("站点不存在")
                values["station_id"] = station["id"]
                values.setdefault("city", station["city"])
            else:
                values["station_id"] = None
        values["updated_at"] = now
        set_clause = ", ".join(f"{column} = ${index + 2}" for index, column in enumerate(values))
        updated = await conn.fetchrow(
            f"UPDATE candidates SET {set_clause} WHERE id = $1 RETURNING *",
            row["id"],
            *values.values(),
        )
        await outbox.emit_event(
            conn,
            event_type="candidate.updated",
            aggregate_type="candidate",
            aggregate_id=row["id"],
            payload={"candidate_id": str(row["id"]), "changed_fields": sorted(values)},
            now=now,
        )
        await audit.append_audit(
            conn,
            actor=actor,
            action="candidate.update",
            resource=f"candidate:{row['id']}",
            payload={"changed_fields": sorted(values), "reason": reason},
        )
        return dict(updated)


def assert_can_write(employee: EmployeeContext) -> None:
    if not employee.has("candidate:write"):
        raise forbidden("当前角色无写入候选人权限")


# ---------------------------------------------------------------------------
# H5 兼容层：先同意后建档、对话补齐字段、自助更正/导出/撤回
# ---------------------------------------------------------------------------
SELF_SERVICE_FIELDS = (
    "birth_ym",
    "area_text",
    "job_type",
    "has_ebike",
    "start_text",
    "experience_text",
    "health_cert",
    "name",
    "phone",
)


def slot_values_complete(row: dict[str, Any]) -> bool:
    return bool(
        row.get("name_token")
        and row.get("phone_token")
        and row.get("birth_ym")
        and row.get("area_text")
        and row.get("job_type")
        and row.get("has_ebike") is not None
        and row.get("start_text")
    )


def slots_complete(slots: dict[str, Any]) -> bool:
    return bool(
        slots.get("name_token")
        and slots.get("phone_token")
        and slots.get("birth_ym")
        and slots.get("area_text")
        and slots.get("job_type")
        and slots.get("has_ebike") is not None
        and slots.get("start_text")
    )


async def get_candidate_any(db: Any, candidate_id: str) -> dict[str, Any]:
    candidate = await fetch_candidate(db, candidate_id)
    if candidate is None:
        raise not_found("候选人不存在或已删除")
    return candidate


async def apply_slots_to_candidate(
    conn: asyncpg.Connection,
    clock: Any,
    settings: Any,
    *,
    candidate_id: str,
    slots: dict[str, Any],
) -> dict[str, Any]:
    """把对话槽位写回候选人档案（H5 先同意后建档的流程）。"""
    now = clock.now()
    row = await conn.fetchrow("SELECT * FROM candidates WHERE id = $1 FOR UPDATE", candidate_id)
    if row is None:
        raise not_found("候选人不存在或已删除")
    updates: dict[str, Any] = {}
    for key in ("name_token", "phone_token", "birth_ym", "area_text", "job_type", "has_ebike", "start_text"):
        if slots.get(key) not in (None, ""):
            updates[key] = slots[key]
    if "birth_ym" in updates:
        minor = is_minor(updates["birth_ym"], now)
        updates["is_minor"] = minor
        if minor:
            updates["retention_until"] = now + timedelta(hours=settings.retention_minor_hours)

    merged = dict(row)
    merged.update(updates)
    if slot_values_complete(merged):
        updates["status"] = "complete" if row["status"] in ("new", "collecting") else row["status"]
        updates["profile_complete"] = True
    elif row["status"] == "new":
        updates["status"] = "collecting"
    if not updates:
        return dict(row)
    updates["updated_at"] = now
    set_clause = ", ".join(f"{column} = ${index + 2}" for index, column in enumerate(updates))
    updated = await conn.fetchrow(
        f"UPDATE candidates SET {set_clause} WHERE id = $1 RETURNING *",
        candidate_id,
        *updates.values(),
    )
    return dict(updated)


async def update_self_service(
    db: Any,
    vault: Vault,
    clock: Any,
    *,
    candidate_id: str,
    updates: dict[str, Any],
    actor: str = "candidate:self",
) -> dict[str, Any]:
    unknown = set(updates) - set(SELF_SERVICE_FIELDS)
    if unknown:
        raise ApiError(422, "invalid_field", f"不允许自助修改的字段: {', '.join(sorted(unknown))}")
    candidate = await get_candidate_any(db, candidate_id)
    return await update_candidate_fields(
        db, vault, clock, candidate=candidate, updates=updates, actor=actor
    )


async def export_candidate(
    db: Any,
    vault: Vault,
    *,
    candidate_id: str,
    include_real: bool = False,
    can_view_real: bool = False,
) -> dict[str, Any]:
    candidate = await get_candidate_any(db, candidate_id)
    public = (await reveal_candidates(db, vault, [candidate]))[0]
    payload: dict[str, Any] = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "candidate": {
            "id": public["id"],
            "name": public["name"],
            "phone": public["phone"],
            "birth_ym": public["birth_ym"],
            "area_text": public["area_text"],
            "job_type": public["job_type"],
            "has_ebike": public["has_ebike"],
            "start_text": public["start_text"],
            "experience_text": public["experience_text"],
            "health_cert": public["health_cert"],
            "source_channel": public["source_channel"],
            "status": public["status"],
        },
        "consent": {"version": candidate["consent_version"], "at": public["consent_at"]},
        "retention_until": public["retention_until"],
        "note": "姓名与手机号在本副本中默认以掩码展示；需要完整值请经人工客服核验身份后获取。",
    }
    if include_real and can_view_real:
        name = await vault.detokenize_value(db, candidate["name_token"])
        phone = await vault.detokenize_value(db, candidate["phone_token"])
        payload["candidate"]["name"] = name
        payload["candidate"]["phone"] = phone
        payload["note"] = "已按员工端权限返回完整姓名与手机号（本次导出已写审计）。"
    return payload


async def revoke_candidate(
    db: Any,
    clock: Any,
    *,
    candidate_id: str,
    actor: str = "candidate:self",
    reason: str | None = None,
) -> dict[str, Any]:
    now = clock.now()
    async with db.transaction() as conn:
        candidate = await conn.fetchrow(
            "SELECT * FROM candidates WHERE id = $1 FOR UPDATE", candidate_id
        )
        if candidate is None:
            raise not_found("候选人不存在或已删除")
        active = await conn.fetch(
            "SELECT * FROM bookings WHERE candidate_id = $1 AND status = 'booked'", candidate_id
        )
        for booking in active:
            await conn.execute(
                "UPDATE stations SET open_quota = open_quota + 1 WHERE id = $1",
                booking["station_id"],
            )
        await audit.append_audit(
            conn,
            actor=actor,
            action="candidate.revoke",
            resource=f"candidate:{candidate_id}",
            payload={"reason": reason, "restored_bookings": len(active)},
        )
        await conn.execute("DELETE FROM candidates WHERE id = $1", candidate_id)
        return {
            "deleted": True,
            "candidate_id": str(candidate_id),
            "deleted_at": now.isoformat(),
        }

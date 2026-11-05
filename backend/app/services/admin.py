"""管理端（admin 前端契约）聚合视图与操作：列表/详情/动作/日程/指标/名额/解盲日志。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from app.errors import bad_request, conflict, forbidden, not_found
from app.events import outbox
from app.security.masking import mask_name, mask_phone
from app.security.tokens import EmployeeContext
from app.security.vault import Vault
from app.services import audit, bookings, candidates, kpi, stations

INTENT_BY_STATUS = {
    "new": 1,
    "collecting": 2,
    "complete": 3,
    "booked": 4,
    "interviewed": 4,
    "hired": 5,
    "handoff": 4,
    "rejected": 1,
}
JOB_TYPE_LABEL = {"fulltime": "全职", "parttime": "兼职", "undecided": "未定"}
HEALTH_LABEL = {"none": "无", "holding": "有", "processing": "办理中", "unknown": "待确认"}
CHANNEL_LABEL = {
    "douyin": "抖音短视频",
    "wechat": "微信好友",
    "moments": "朋友圈广告",
    "offline_poster": "线下海报",
    "referral": "老骑手推荐",
    "import": "批量导入",
    "agent": "AI 对话",
    "manual": "人工录入",
    "direct": "直接访问",
}


def _scope(employee: EmployeeContext) -> tuple[str, list[Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    if employee.city != "*":
        params.append(employee.city)
        conditions.append(f"city = ${len(params)}")
    if employee.role == "station_operator" and employee.station_ids:
        params.append(list(employee.station_ids))
        conditions.append(f"station_id = ANY(${len(params)}::uuid[])")
    return (" AND ".join(conditions) if conditions else "TRUE"), params


ADMIN_PATCH_FIELDS = set(candidates.SELF_SERVICE_FIELDS) | {"station_id"}
FIELD_ALIASES = {"name_masked": "name", "phone_masked": "phone"}


def _normalize_fields(fields: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in (fields or {}).items():
        normalized[FIELD_ALIASES.get(key, key)] = value
    return normalized


def _health_for_admin(value: str | None) -> str | None:
    if value is None:
        return None
    return candidates.HEALTH_CERT_DISPLAY.get(value, value)


def _intent_level(candidate: dict[str, Any]) -> int:
    if candidate["profile_complete"]:
        return max(INTENT_BY_STATUS.get(candidate["status"], 3), 4)
    return INTENT_BY_STATUS.get(candidate["status"], 2)


async def _station_names(db: Any) -> dict[str, str]:
    rows = await db.fetch("SELECT id, name FROM stations")
    return {str(row["id"]): row["name"] for row in rows}


async def admin_list_candidates(
    db: Any,
    vault: Vault,
    employee: EmployeeContext,
    *,
    q: str | None = None,
    status: str | None = None,
    source_channel: str | None = None,
    station_id: str | None = None,
    intent_level: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    where, params = _scope(employee)
    rows = await db.fetch(
        f"SELECT * FROM candidates WHERE {where} ORDER BY updated_at DESC", *params
    )
    rows = [dict(row) for row in rows]
    public_by_id = {
        item["id"]: item for item in await candidates.reveal_candidates(db, vault, rows)
    }
    station_names = await _station_names(db)
    query = (q or "").strip().lower()

    filtered: list[dict[str, Any]] = []
    for row in rows:
        item = dict(public_by_id[str(row["id"])])
        item["station_name"] = station_names.get(item["station_id"] or "", "")
        item["intent_level"] = _intent_level(row)
        item["health_cert"] = _health_for_admin(item["health_cert"])
        if query:
            raw_name = await vault.detokenize_value(db, row["name_token"])
            raw_phone = await vault.detokenize_value(db, row["phone_token"])
            haystack = (
                f"{item['name_masked']}{item['phone_masked']}{item['station_name']}"
                f"{raw_name}{raw_phone}"
            ).lower()
            if query not in haystack:
                continue
        if status and item["status"] != status:
            continue
        if source_channel and item["source_channel"] != source_channel:
            continue
        if station_id and item["station_id"] != station_id:
            continue
        if intent_level and str(item["intent_level"]) != str(intent_level):
            continue
        filtered.append(item)

    total = len(filtered)
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    start = (page - 1) * page_size
    return {
        "items": filtered[start : start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def admin_candidate_detail(
    db: Any,
    vault: Vault,
    employee: EmployeeContext,
    candidate_id: str,
    clock: Any,
) -> dict[str, Any]:
    row = await candidates.get_candidate_for_employee(db, employee, candidate_id)
    public = (await candidates.reveal_candidates(db, vault, [row]))[0]
    station_row = (
        await db.fetchrow("SELECT * FROM stations WHERE id = $1", row["station_id"])
        if row["station_id"]
        else None
    )
    station_name = station_row["name"] if station_row else ""
    interview_rows = await admin_interviews(
        db, vault, employee=employee, candidate_id=candidate_id
    )

    detail = dict(public)
    detail.update(
        {
            "station_name": station_name,
            "intent_level": _intent_level(row),
            "health_cert": _health_for_admin(detail["health_cert"]),
            "qualification": _build_qualification(row),
            "conversation_summary": _summary(row),
            "conversation_key_points": _key_points(row),
            "transcript": await _transcript(db, candidate_id),
            "audit_log": await _audit_log(db, candidate_id),
            "interview_slots": await stations.build_station_slots(db, station_row, clock)
            if station_row
            else [],
            "interviews": interview_rows["interviews"],
        }
    )
    return detail


def _format_audit(row: Any) -> dict[str, Any]:
    try:
        payload = json.loads(row["payload"] or "{}")
    except Exception:  # pragma: no cover
        payload = {}
    return {
        "id": row["id"],
        "at": row["created_at"].isoformat(),
        "operator": row["actor"],
        "field": payload.get("field") or payload.get("action") or row["action"],
        "from": payload.get("from", "-"),
        "to": payload.get("to", "-"),
        "reason": payload.get("reason", ""),
    }


async def _audit_log(db: Any, candidate_id: str) -> list[dict[str, Any]]:
    rows = await db.fetch(
        "SELECT * FROM audit_log WHERE resource = $1 ORDER BY id DESC LIMIT 50",
        f"candidate:{candidate_id}",
    )
    return [_format_audit(row) for row in rows]


async def _transcript(db: Any, candidate_id: str) -> list[dict[str, Any]]:
    rows = await db.fetch(
        """
        SELECT m.role, m.text_redacted, m.created_at
        FROM agent_messages m
        JOIN agent_sessions s ON s.id = m.session_id
        WHERE s.candidate_id = $1
        ORDER BY m.id
        LIMIT 40
        """,
        candidate_id,
    )
    return [
        {
            "role": row["role"],
            "text": row["text_redacted"],
            "at": row["created_at"].isoformat(),
        }
        for row in rows
    ]


def _summary(row: dict[str, Any]) -> str:
    return "；".join(
        [
            f"工作类型：{JOB_TYPE_LABEL.get(row['job_type'], '未定')}",
            f"区域：{row['area_text'] or '未填'}",
            f"电动车：{'有' if row['has_ebike'] else '没有' if row['has_ebike'] is not None else '未填'}",
            f"可到岗：{row['start_text'] or '未填'}",
        ]
    ) + "。"


def _key_points(row: dict[str, Any]) -> list[str]:
    points = [f"状态：{row['status']}"]
    if row["health_cert"]:
        points.append(f"健康证：{HEALTH_LABEL.get(row['health_cert'], row['health_cert'])}")
    if row["experience_text"]:
        points.append(f"经验：{row['experience_text']}")
    return points


def _build_qualification(row: dict[str, Any]) -> dict[str, Any]:
    score = 60
    rules: list[str] = []
    if row["has_ebike"]:
        score += 10
        rules.append("自有电动车 +10")
    else:
        rules.append("无电动车：需确认租车方案")
    if row["health_cert"] == "holding":
        score += 10
        rules.append("持健康证 +10")
    elif row["health_cert"] in ("none", "unknown"):
        rules.append("健康证待办理")
    if row["job_type"] == "fulltime":
        score += 10
        rules.append("全职意向 +10")
    if row["profile_complete"]:
        score += 10
        rules.append("资料完整 +10")
    level = 5 if score >= 90 else 4 if score >= 80 else 3 if score >= 70 else 2
    return {
        "level": level,
        "score": min(score, 100),
        "rules": rules,
        "suggestion": "建议优先确认面试" if level >= 4 else "建议人工跟进确认意向",
    }


async def admin_interviews(
    db: Any,
    vault: Vault,
    *,
    employee: EmployeeContext,
    from_: str | None = None,
    to: str | None = None,
    candidate_id: str | None = None,
) -> dict[str, Any]:
    conditions: list[str] = []
    params: list[Any] = []
    if employee.city != "*":
        params.append(employee.city)
        conditions.append(f"c.city = ${len(params)}")
    if employee.role == "station_operator" and employee.station_ids:
        params.append(list(employee.station_ids))
        conditions.append(f"b.station_id = ANY(${len(params)}::uuid[])")
    if candidate_id:
        params.append(candidate_id)
        conditions.append(f"b.candidate_id = ${len(params)}::uuid")
    if from_:
        params.append(from_)
        conditions.append(f"b.slot_start >= ${len(params)}::timestamptz")
    if to:
        params.append(to)
        conditions.append(f"b.slot_start <= ${len(params)}::timestamptz")
    where = " AND ".join(conditions) if conditions else "TRUE"
    rows = await db.fetch(
        f"""
        SELECT b.*, s.name AS station_name,
               c.name_token, c.phone_token
        FROM bookings b
        JOIN candidates c ON c.id = b.candidate_id
        JOIN stations s ON s.id = b.station_id
        WHERE {where}
        ORDER BY b.slot_start
        LIMIT 300
        """,
        *params,
    )
    tokens: list[str] = []
    for row in rows:
        if row["name_token"]:
            tokens.append(row["name_token"])
        if row["phone_token"]:
            tokens.append(row["phone_token"])
    ciphertexts = await vault.fetch_ciphertexts(db, tokens)
    items: list[dict[str, Any]] = []
    for row in rows:
        name_raw = vault.decrypt_ciphertext(ciphertexts.get(row["name_token"] or "")) or ""
        phone_raw = vault.decrypt_ciphertext(ciphertexts.get(row["phone_token"] or "")) or ""
        items.append(
            {
                "id": str(row["id"]),
                "booking_id": str(row["id"]),
                "candidate_id": str(row["candidate_id"]),
                "candidate_name": mask_name(name_raw) if name_raw else "**",
                "name_masked": mask_name(name_raw) if name_raw else "**",
                "candidate_phone_masked": mask_phone(phone_raw) if phone_raw else "***",
                "station_id": str(row["station_id"]),
                "station_name": row["station_name"],
                "slot_start": row["slot_start"].isoformat(),
                "status": row["status"],
                "note": "面试已到访"
                if row["status"] == "done"
                else "未到访，待回访"
                if row["status"] == "no_show"
                else "待面试",
            }
        )
    return {"interviews": items, "items": items, "total": len(items)}


async def admin_metrics(db: Any) -> dict[str, Any]:
    view = await kpi.get_kpi_summary(db)
    leads = int(view["leads_in"])
    profile_complete = int(round(view["profile_complete_rate"] * leads)) if leads else 0
    booking_total = await db.fetchval("SELECT count(*) FROM bookings")
    done_total = await db.fetchval("SELECT count(*) FROM bookings WHERE status = 'done'")
    hired = int(view["hired_count"])
    channels = await db.fetch(
        "SELECT source_channel, count(*) AS n FROM candidates GROUP BY source_channel ORDER BY n DESC"
    )
    trend_seed = [leads, profile_complete, int(booking_total), int(done_total), hired]
    kpis = [
        _kpi("new_leads", "今日新增线索", leads, "人", trend_seed[0]),
        _kpi("valid_profiles", "有效建档数", profile_complete, "人", trend_seed[1]),
        _kpi("complete_rate", "建档完成率", round(view["profile_complete_rate"] * 100, 1), "%", trend_seed[1]),
        _kpi("bookings", "本周预约面试", int(booking_total), "场", trend_seed[2]),
        _kpi("visit_rate", "预约到访率", round(view["booking_show_rate"] * 100, 1), "%", trend_seed[3]),
        _kpi("hired", "本月入职转化", hired, "人", trend_seed[4]),
        _kpi("avg_reply", "AI 平均首响", round(view["ai_first_response_avg_ms"] / 1000, 1), "秒", 1),
    ]
    funnel = [
        {"label": "线索留资", "value": leads},
        {"label": "有效建档", "value": profile_complete},
        {"label": "预约面试", "value": int(booking_total)},
        {"label": "到站面试", "value": int(done_total)},
        {"label": "入职", "value": hired},
    ]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kpis": kpis,
        "funnel": funnel,
        "channels": [
            {"name": CHANNEL_LABEL.get(row["source_channel"], row["source_channel"]), "value": int(row["n"])}
            for row in channels
        ],
        "kpi_metrics": view,
        "source": "kpi_summary",
    }


def _kpi(key: str, label: str, value: float | int, unit: str, trend_base: int) -> dict[str, Any]:
    base = max(1, int(trend_base))
    trend = [max(0, round(base * ratio)) for ratio in (0.55, 0.68, 0.62, 0.78, 0.86, 0.92, 1.0)]
    return {
        "key": key,
        "label": label,
        "value": value,
        "unit": unit,
        "delta": 0.0,
        "trend": trend,
    }


async def update_station_quota(
    db: Any, clock: Any, station_id: str, open_quota: int, actor: str
) -> dict[str, Any]:
    if not isinstance(open_quota, int) or open_quota < 0 or open_quota > 99:
        raise bad_request("invalid_quota", "名额需为 0-99 的整数")
    async with db.transaction() as conn:
        row = await conn.fetchrow("SELECT * FROM stations WHERE id = $1 FOR UPDATE", station_id)
        if row is None:
            raise not_found("站点不存在")
        await conn.execute(
            "UPDATE stations SET open_quota = $2 WHERE id = $1", station_id, open_quota
        )
        await audit.append_audit(
            conn,
            actor=actor,
            action="station.quota.update",
            resource=f"station:{station_id}",
            payload={"from": row["open_quota"], "to": open_quota, "reason": "管理端调整名额"},
        )
    updated = await db.fetchrow("SELECT * FROM stations WHERE id = $1", station_id)
    return await stations.station_payload(db, dict(updated), clock)


async def admin_patch_candidate(
    db: Any,
    vault: Vault,
    clock: Any,
    employee: EmployeeContext,
    candidate_id: str,
    *,
    fields: dict[str, Any],
    reason: str | None,
) -> dict[str, Any]:
    if not reason or len(reason.strip()) < 2:
        raise bad_request("reason_required", "修改候选人信息必须填写修改原因（至少 2 个字）")
    fields = _normalize_fields(fields)
    if not fields:
        raise bad_request("no_changes", "没有需要保存的修改")
    unknown = set(fields) - ADMIN_PATCH_FIELDS
    if unknown:
        raise bad_request("invalid_field", f"不允许修改的字段: {', '.join(sorted(unknown))}")
    candidate = await candidates.get_candidate_for_employee(db, employee, candidate_id)
    await candidates.update_candidate_fields(
        db, vault, clock, candidate=candidate, updates=fields, actor=employee.username,
        reason=reason,
    )
    return await admin_candidate_detail(db, vault, employee, candidate_id, clock)


async def admin_candidate_action(
    db: Any,
    vault: Vault,
    clock: Any,
    employee: EmployeeContext,
    candidate_id: str,
    *,
    action: str,
    reason: str | None,
    slot_start: datetime | None = None,
    fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if action not in ("confirm_interview", "handoff", "reject", "update_fields"):
        raise bad_request("invalid_action", "不支持的操作")
    if not reason or len(reason.strip()) < 2:
        raise bad_request("reason_required", "该操作必须填写理由后才能提交")
    if action == "update_fields":
        return await admin_patch_candidate(
            db, vault, clock, employee, candidate_id, fields=fields or {}, reason=reason
        )
    candidate = await candidates.get_candidate_for_employee(db, employee, candidate_id)
    now = clock.now()
    labels = {"confirm_interview": "确认面试", "handoff": "转人工跟进", "reject": "标记不合适"}
    async with db.transaction() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM candidates WHERE id = $1 FOR UPDATE", candidate_id
        )
        if row is None:
            raise not_found("候选人不存在")
        target_status = "handoff" if action == "handoff" else "rejected" if action == "reject" else "booked"
        if action == "confirm_interview":
            if not slot_start:
                raise bad_request("slot_required", "确认面试需要选择面试时段")
            if row["status"] != "complete":
                await conn.execute(
                    "UPDATE candidates SET status = 'complete', updated_at = $2 WHERE id = $1",
                    candidate_id,
                    now,
                )
                await audit.append_audit(
                    conn,
                    actor=employee.username,
                    action="candidate.status.update",
                    resource=f"candidate:{candidate_id}",
                    payload={
                        "from": row["status"],
                        "to": "complete",
                        "reason": f"{reason}（确认面试前补齐）",
                        "field": "状态",
                    },
                )
            station_id = row["station_id"]
            if station_id is None:
                station = await conn.fetchrow(
                    "SELECT id FROM stations WHERE city = $1 ORDER BY distance_km LIMIT 1",
                    row["city"],
                )
                station_id = station["id"] if station else None
            if station_id is None:
                raise conflict("station_required", "候选人尚未分配站点，无法确认面试")
            refreshed = await conn.fetchrow("SELECT * FROM candidates WHERE id = $1", candidate_id)
            booking = await bookings.create_booking(
                db,
                clock,
                candidate=dict(refreshed),
                station_id=str(station_id),
                slot_start=slot_start,
                actor=employee.username,
                conn=conn,
            )
            await audit.append_audit(
                conn,
                actor=employee.username,
                action="candidate.action.confirm_interview",
                resource=f"candidate:{candidate_id}",
                payload={
                    "field": "操作",
                    "from": "-",
                    "to": labels[action],
                    "reason": reason,
                    "booking_id": booking["id"],
                },
            )
        else:
            await conn.execute(
                "UPDATE candidates SET status = $2, updated_at = $3 WHERE id = $1",
                candidate_id,
                target_status,
                now,
            )
            if target_status == "rejected":
                await conn.execute(
                    "UPDATE candidates SET retention_until = $2 WHERE id = $1",
                    candidate_id,
                    now - timedelta(seconds=1),
                )
            event_type = "handoff.requested" if target_status == "handoff" else "candidate.updated"
            await outbox.emit_event(
                conn,
                event_type=event_type,
                aggregate_type="candidate",
                aggregate_id=candidate_id,
                payload={"candidate_id": str(candidate_id), "from_status": row["status"], "to_status": target_status},
                now=now,
            )
            await audit.append_audit(
                conn,
                actor=employee.username,
                action=f"candidate.action.{action}",
                resource=f"candidate:{candidate_id}",
                payload={
                    "field": "操作",
                    "from": row["status"],
                    "to": target_status,
                    "reason": reason,
                },
            )
    return await admin_candidate_detail(db, vault, employee, candidate_id, clock)


async def detokenize_logs(db: Any, limit: int = 50) -> dict[str, Any]:
    rows = await db.fetch(
        "SELECT * FROM audit_log WHERE action = 'vault.detokenize' ORDER BY id DESC LIMIT $1",
        max(1, min(limit, 200)),
    )
    logs = []
    for row in rows:
        try:
            payload = json.loads(row["payload"] or "{}")
        except Exception:  # pragma: no cover
            payload = {}
        logs.append(
            {
                "id": row["id"],
                "at": row["created_at"].isoformat(),
                "operator": row["actor"],
                "field": "手机号" if payload.get("pii_type") == "phone" else "姓名/证件",
                "reason": payload.get("reason", ""),
                "token": row["resource"].replace("token:", ""),
            }
        )
    return {"logs": logs, "total": len(logs)}

"""对话引擎：7 槽位收集、口语抽取、未成年终止、政策引用、LLM 超时降级。

同时兼容两种入口：
- 契约 v1 原生：`POST /agent/sessions` 匿名开始，收齐 7 项后自动建档；
- H5 演示流程：先 `POST /consent` 建档，再 `POST /agent/sessions {candidate_id}`
  绑定该候选人，对话逐项补齐字段（不重复建档）。

响应契约：{reply, quick_replies[], progress{done,total,fields[]}, actions[]}；
`actions` 取值 show_stations | booking_confirmed | handoff | end_minor。
扩展字段（供 H5 渲染，缺失时前端有兜底）：message_id、candidate_id、greeting、
policy_card、source_label、stations。
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import timedelta
from typing import Any

from app.agent import extract
from app.agent.llm import LLMClient, LLMUnavailable
from app.errors import ApiError, conflict, not_found
from app.security.anonymize import MaskResult, mask_text
from app.security.vault import Vault
from app.services import audit, bookings, candidates, policies
from app.services import stations as station_service
from app.events import outbox

VALID_ACTIONS = ("show_stations", "booking_confirmed", "handoff", "end_minor")
TOTAL = extract.SLOT_TOTAL


def _filled(slots: dict[str, Any], slot: str) -> bool:
    if slot == "name":
        return bool(slots.get("name_token"))
    if slot == "phone":
        return bool(slots.get("phone_token"))
    value = slots.get(slot)
    return value not in (None, "", [])


def build_progress(context: dict[str, Any]) -> dict[str, Any]:
    slots = context.get("slots", {})
    fields = [
        {"key": slot, "label": extract.SLOT_LABELS[slot], "collected": _filled(slots, slot)}
        for slot in extract.SLOTS
    ]
    return {
        "done": sum(1 for field in fields if field["collected"]),
        "total": TOTAL,
        "fields": fields,
        "mode": context.get("mode", "llm"),
    }


def _question(slot: str, context: dict[str, Any], *, degraded: bool) -> tuple[str, list[str]]:
    index = sum(1 for item in extract.SLOTS if _filled(context.get("slots", {}), item))
    if degraded:
        return extract.form_question_for(slot, index), []
    return extract.question_for(slot, index)


def _next_slot(context: dict[str, Any]) -> str | None:
    for slot in extract.SLOTS:
        if not _filled(context.get("slots", {}), slot):
            return slot
    return None


def _slots_from_row(row: dict[str, Any]) -> dict[str, Any]:
    slots: dict[str, Any] = {}
    for slot, column in (
        ("name", "name_token"),
        ("phone", "phone_token"),
        ("birth_ym", "birth_ym"),
        ("area_text", "area_text"),
        ("job_type", "job_type"),
        ("has_ebike", "has_ebike"),
        ("start_text", "start_text"),
    ):
        if column == "name_token":
            if row.get(column):
                slots[column] = row[column]
            continue
        if column == "phone_token":
            if row.get(column):
                slots[column] = row[column]
            continue
        if row.get(column) not in (None, ""):
            slots[column] = row[column]
    return slots


async def _station_cards(db: Any, clock: Any, limit: int = 3) -> list[dict[str, Any]]:
    rows = await db.fetch(
        "SELECT * FROM stations WHERE open_quota > 0 ORDER BY distance_km, name LIMIT $1", limit
    )
    return [await station_service.station_payload(db, dict(row), clock) for row in rows]


async def create_session(
    db: Any,
    clock: Any,
    llm: LLMClient,
    *,
    candidate_id: str | None = None,
) -> dict[str, Any]:
    now = clock.now()
    async with db.transaction() as conn:
        if candidate_id:
            candidate = await conn.fetchrow("SELECT * FROM candidates WHERE id = $1", candidate_id)
            if candidate is None:
                raise not_found("候选人不存在或已删除")
            context = {
                "slots": _slots_from_row(dict(candidate)),
                "mode": "llm",
                "candidate_id": str(candidate["id"]),
            }
            stage = "station_pick" if candidate["profile_complete"] else "collecting"
            row = await conn.fetchrow(
                """
                INSERT INTO agent_sessions
                    (candidate_id, stage, context, status, llm_mode, created_at, updated_at)
                VALUES ($1, $2, $3::jsonb, 'active', $4, $5, $5)
                RETURNING *
                """,
                candidate["id"],
                stage,
                json.dumps(context, ensure_ascii=False),
                llm.name,
                now,
            )
        else:
            context = {"slots": {}, "mode": "llm"}
            row = await conn.fetchrow(
                """
                INSERT INTO agent_sessions (stage, context, status, llm_mode, created_at, updated_at)
                VALUES ('collecting', $1::jsonb, 'active', $2, $3, $3)
                RETURNING *
                """,
                json.dumps(context, ensure_ascii=False),
                llm.name,
                now,
            )

        next_slot = _next_slot(context)
        if next_slot:
            hint, quick_replies = extract.question_for(next_slot, 0)
            reply = "你好，我是骑手招聘信息收集助手，会依次了解 7 项信息。" + hint
        else:
            quick_replies = [card["name"] for card in await _station_cards(db, clock)]
            reply = "7 项信息已收集完整，请选择一个就近站点预约到站时间。"
        progress = build_progress(context)
        greeting = {
            "text": reply,
            "quick_replies": quick_replies,
            "progress": progress,
            "actions": [],
        }
        await _store_message(conn, row["id"], "assistant", reply, now, latency_ms=0)
        await audit.append_audit(
            conn,
            actor="agent",
            action="agent.session.create",
            resource=f"agent_session:{row['id']}",
            payload={"llm_mode": llm.name, "candidate_id": str(candidate_id) if candidate_id else None},
        )
        return {
            "session_id": str(row["id"]),
            "candidate_id": str(row["candidate_id"]) if row["candidate_id"] else None,
            "reply": reply,
            "quick_replies": quick_replies,
            "progress": progress,
            "actions": [],
            "greeting": greeting,
        }


async def _store_message(
    conn: Any,
    session_id: Any,
    role: str,
    text: str,
    now: Any,
    *,
    raw_text: str | None = None,
    llm_payload: dict[str, Any] | None = None,
    latency_ms: int | None = None,
    client_message_id: str | None = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO agent_messages
            (session_id, role, text_redacted, raw_text, llm_payload, latency_ms, client_message_id, created_at)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8)
        ON CONFLICT DO NOTHING
        """,
        session_id,
        role,
        text,
        raw_text,
        json.dumps(llm_payload, ensure_ascii=False) if llm_payload is not None else None,
        latency_ms,
        client_message_id,
        now,
    )


async def _extract_slots(
    db: Any,
    vault: Vault,
    settings: Any,
    llm: LLMClient,
    context: dict[str, Any],
    masked: MaskResult,
    *,
    use_llm: bool,
) -> dict[str, Any]:
    """调用 LLM（带超时）抽取槽位；失败则降级为确定性表单抽取。"""
    if use_llm:
        payload = {
            "text": masked.text,
            "placeholders": _group_placeholders(masked),
            "missing_slots": [slot for slot in extract.SLOTS if not _filled(context.get("slots", {}), slot)],
            "stage": context.get("stage"),
            "locale": "zh-CN",
        }
        try:
            result = await asyncio.wait_for(
                llm.extract(payload), timeout=settings.llm_timeout_seconds
            )
            context["mode"] = "llm"
            context["last_llm_payload"] = payload
            slots = dict(result.slots)
        except (asyncio.TimeoutError, LLMUnavailable):
            context["mode"] = "form"
            context["degraded_reason"] = "llm_timeout"
            slots = extract.extract_slots(masked.text)
    else:
        slots = extract.extract_slots(masked.text)
    return slots


def _group_placeholders(masked: MaskResult) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {"name": [], "phone": [], "area_text": []}
    for placeholder in masked.placeholders:
        if placeholder.startswith("〔phone_"):
            grouped["phone"].append(placeholder)
        elif placeholder.startswith("〔name_"):
            grouped["name"].append(placeholder)
        elif placeholder.startswith("〔addr_"):
            grouped["area_text"].append(placeholder)
    return grouped


async def _merge_slots(
    conn: Any,
    vault: Vault,
    context: dict[str, Any],
    masked: MaskResult,
    llm_slots: dict[str, Any],
) -> None:
    slots = context.setdefault("slots", {})
    for match in masked.matches:
        if match.type == "phone":
            slots["phone_token"] = await vault.tokenize(conn, "phone", match.value)
        elif match.type == "name":
            slots["name_token"] = await vault.tokenize(conn, "name", match.value)
        elif match.type == "address":
            slots["area_text"] = match.value

    for slot, value in llm_slots.items():
        if value in (None, ""):
            continue
        if not isinstance(value, (str, bool)):
            continue
        if slot in ("name", "phone", "area_text") and isinstance(value, str):
            if value in masked.placeholders:
                raw_value = masked.placeholders[value]
                pii_type = "phone" if value.startswith("〔phone_") else "name"
                if slot == "area_text":
                    slots["area_text"] = raw_value
                else:
                    key = "phone_token" if pii_type == "phone" else "name_token"
                    slots[key] = await vault.tokenize(conn, pii_type, raw_value)
                continue
            if slot == "area_text":
                slots["area_text"] = value.strip()
            continue
        if slot == "birth_ym":
            parsed = extract.parse_birth_ym(str(value))
            if parsed:
                slots["birth_ym"] = parsed
        elif slot == "job_type" and value in ("fulltime", "parttime", "undecided"):
            slots["job_type"] = value
        elif slot == "has_ebike" and isinstance(value, bool):
            slots["has_ebike"] = value
        elif slot == "start_text":
            slots["start_text"] = str(value)

    # 确定性兜底：LLM 漏抽时用本地规则补齐（保证 mock/真实模型行为一致）
    for key, value in extract.extract_slots(masked.text).items():
        if key not in slots or slots[key] in (None, ""):
            slots[key] = value


async def _handoff(
    conn: Any,
    *,
    session: dict[str, Any],
    context: dict[str, Any],
    now: Any,
    reply: str,
    reason: str,
    actor: str,
) -> str:
    await conn.execute(
        "UPDATE agent_sessions SET status = 'handoff', stage = 'handoff', updated_at = $2 WHERE id = $1",
        session["id"],
        now,
    )
    candidate_id = context.get("candidate_id")
    if candidate_id:
        row = await conn.fetchrow("SELECT * FROM candidates WHERE id = $1 FOR UPDATE", candidate_id)
        if row is not None and "handoff" in candidates.ALLOWED_TRANSITIONS.get(
            row["status"], frozenset()
        ):
            await conn.execute(
                "UPDATE candidates SET status = 'handoff', updated_at = $2 WHERE id = $1",
                row["id"],
                now,
            )
    await outbox.emit_event(
        conn,
        event_type="handoff.requested",
        aggregate_type="candidate" if candidate_id else "agent_session",
        aggregate_id=candidate_id or session["id"],
        payload={
            "session_id": str(session["id"]),
            "candidate_id": str(candidate_id) if candidate_id else None,
            "reason": reason,
        },
        now=now,
    )
    await audit.append_audit(
        conn,
        actor=actor,
        action="agent.handoff",
        resource=f"agent_session:{session['id']}",
        payload={"reason": reason},
    )
    return reply


async def _create_candidate_from_context(
    conn: Any,
    vault: Vault,
    context: dict[str, Any],
    session_id: Any,
    *,
    status: str,
    clock: Any,
    settings: Any,
    actor: str,
) -> Any:
    slots = context.get("slots", {})
    name_token = slots.get("name_token") or await vault.tokenize(conn, "name", f"匿名-{session_id}")
    phone_token = slots.get("phone_token") or await vault.tokenize(conn, "phone", f"匿名-{session_id}")
    row = await conn.fetchrow(
        """
        INSERT INTO candidates
            (name_token, phone_token, birth_ym, area_text, job_type, has_ebike, start_text,
             experience_text, health_cert, source_channel, status, is_minor, profile_complete,
             consent_version, consent_at, retention_until, created_at, updated_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,NULL,'unknown','agent',$8,$9,$10,'v1',$11,$12,$11,$11)
        RETURNING *
        """,
        name_token,
        phone_token,
        slots.get("birth_ym"),
        slots.get("area_text"),
        slots.get("job_type"),
        slots.get("has_ebike"),
        slots.get("start_text"),
        status,
        candidates.is_minor(slots.get("birth_ym"), clock.now()),
        status == "complete",
        clock.now(),
        None
        if status in candidates.TERMINAL_RETENTION_STATUSES
        else candidates.retention_deadline(
            now=clock.now(),
            minor=candidates.is_minor(slots.get("birth_ym"), clock.now()),
            unhired_days=settings.retention_unhired_days,
            minor_hours=settings.retention_minor_hours,
        ),
    )
    await outbox.emit_event(
        conn,
        event_type="candidate.created",
        aggregate_type="candidate",
        aggregate_id=row["id"],
        payload={
            "candidate_id": str(row["id"]),
            "status": row["status"],
            "source_channel": "agent",
            "session_id": str(session_id),
        },
        now=clock.now(),
    )
    await audit.append_audit(
        conn,
        actor=actor,
        action="candidate.create",
        resource=f"candidate:{row['id']}",
        payload={"source_channel": "agent", "session_id": str(session_id)},
    )
    return row


async def handle_message(
    db: Any,
    vault: Vault,
    settings: Any,
    clock: Any,
    llm: LLMClient,
    *,
    session_id: str,
    text: str,
    client_message_id: str | None = None,
) -> dict[str, Any]:
    if not text or not text.strip():
        raise ApiError(422, "empty_message", "消息不能为空")
    from app.errors import parse_uuid

    session_id = str(parse_uuid(session_id, "会话不存在"))
    now = clock.now()
    async with db.transaction() as conn:
        session_row = await conn.fetchrow(
            "SELECT * FROM agent_sessions WHERE id = $1 FOR UPDATE", session_id
        )
        if session_row is None:
            raise not_found("会话不存在")
        session = dict(session_row)
        client_replies = json.loads(session.get("client_replies") or "{}")
        if client_message_id and client_message_id in client_replies:
            cached = dict(client_replies[client_message_id])
            cached["replayed"] = True
            return cached
        if session["status"] != "active":
            raise conflict("session_closed", f"会话已结束（{session['status']}）")
        context = json.loads(session["context"] or "{}")
        slots = context.setdefault("slots", {})
        degraded = context.get("mode") == "form"
        masked = mask_text(text)

        first_user_at = session["first_user_at"] or now
        await _store_message(
            conn,
            session["id"],
            "user",
            masked.text,
            now,
            raw_text=text,
            llm_payload={"masked_text": masked.text, "placeholders": _group_placeholders(masked)},
            client_message_id=client_message_id,
        )

        # 1) 明确要求转人工
        if extract.wants_handoff(text):
            reply = await _handoff(
                conn,
                session=session,
                context=context,
                now=now,
                reply="好的，已为你转接人工客服，请保持手机畅通。",
                reason="user_requested",
                actor="agent",
            )
            return await _finish(
                conn, session, context, now, first_user_at, reply, [], ["handoff"],
                client_message_id=client_message_id, status="handoff", stage="handoff",
            )

        # 2) 抽取槽位（LLM 可插拔，超时降级表单）
        llm_slots = await _extract_slots(
            db, vault, settings, llm, context, masked, use_llm=not degraded
        )
        if context.get("mode") == "form":
            degraded = True
        await _merge_slots(conn, vault, context, masked, llm_slots)

        # 3) 未成年人 -> 礼貌终止
        birth_ym = slots.get("birth_ym")
        if birth_ym and candidates.is_minor(birth_ym, clock.now()):
            if context.get("candidate_id"):
                await candidates.apply_slots_to_candidate(
                    conn,
                    clock,
                    settings,
                    candidate_id=context["candidate_id"],
                    slots=slots,
                )
                await conn.execute(
                    "UPDATE candidates SET status = 'rejected', is_minor = true, updated_at = $2 WHERE id = $1",
                    context["candidate_id"],
                    now,
                )
            else:
                candidate = await _create_candidate_from_context(
                    conn, vault, context, session["id"],
                    status="rejected", clock=clock, settings=settings, actor="agent",
                )
                context["candidate_id"] = str(candidate["id"])
            await conn.execute(
                "UPDATE agent_sessions SET status = 'terminated_minor', stage = 'terminated', updated_at = $2 WHERE id = $1",
                session["id"],
                now,
            )
            reply = (
                "感谢你的关注。根据平台规定，骑手岗位需年满 18 周岁；"
                "由于你尚未满 18 岁，暂时无法安排岗位，欢迎年满 18 岁后再来应聘。"
            )
            await audit.append_audit(
                conn,
                actor="agent",
                action="agent.minor_terminated",
                resource=f"agent_session:{session['id']}",
                payload={"candidate_id": context.get("candidate_id")},
            )
            return await _finish(
                conn, session, context, now, first_user_at, reply, [], ["end_minor"],
                client_message_id=client_message_id, status="terminated_minor", stage="terminated",
            )

        # 4) 已绑定候选人（H5 先同意后建档）：逐项写回档案
        if context.get("candidate_id"):
            before = await conn.fetchrow(
                "SELECT * FROM candidates WHERE id = $1", context["candidate_id"]
            )
            updated = await candidates.apply_slots_to_candidate(
                conn, clock, settings,
                candidate_id=context["candidate_id"], slots=slots,
            )
            candidate_id = context["candidate_id"]
            if (
                _next_slot(context) is None
                and updated["status"] == "complete"
                and session["stage"] != "station_pick"
                and not extract.is_policy_question(text)
            ):
                if before is None or before["status"] != "complete" or not before["profile_complete"]:
                    await outbox.emit_event(
                        conn,
                        event_type="candidate.completed",
                        aggregate_type="candidate",
                        aggregate_id=candidate_id,
                        payload={"candidate_id": str(candidate_id), "session_id": str(session["id"])},
                        now=now,
                    )
                await conn.execute(
                    "UPDATE agent_sessions SET stage = 'station_pick', updated_at = $2 WHERE id = $1",
                    session["id"],
                    now,
                )
                station_cards = await _station_cards(db, clock)
                reply = (
                    "7 项信息已收集完整，报名资料已提交。"
                    "请选择一个就近站点预约到站时间（也可以直接在站点页预约）。"
                )
                return await _finish(
                    conn, session, context, now, first_user_at, reply,
                    [card["name"] for card in station_cards], ["show_stations"],
                    client_message_id=client_message_id,
                    extra={"stations": station_cards},
                )
        # 5) 未绑定候选人且 7 项齐全 -> 自动建档并进入选站
        elif _next_slot(context) is None:
            candidate = await _create_candidate_from_context(
                conn, vault, context, session["id"],
                status="complete", clock=clock, settings=settings, actor="agent",
            )
            context["candidate_id"] = str(candidate["id"])
            await outbox.emit_event(
                conn,
                event_type="candidate.completed",
                aggregate_type="candidate",
                aggregate_id=candidate["id"],
                payload={"candidate_id": str(candidate["id"]), "session_id": str(session["id"])},
                now=now,
            )
            await conn.execute(
                "UPDATE agent_sessions SET stage = 'station_pick', candidate_id = $2, updated_at = $3 WHERE id = $1",
                session["id"],
                candidate["id"],
                now,
            )
            station_cards = await _station_cards(db, clock)
            reply = (
                "7 项信息已收集完整，报名资料已提交。"
                "请选择一个就近站点预约到站时间（回复站点名称即可）。"
            )
            return await _finish(
                conn, session, context, now, first_user_at, reply,
                [card["name"] for card in station_cards], ["show_stations"],
                client_message_id=client_message_id,
                extra={"stations": station_cards},
            )

        # 6) 待选站（契约模式：对话内直接选站预约）
        if context.get("candidate_id") and session["stage"] == "station_pick":
            station = await _match_station(db, text)
            if station is None:
                if extract.is_policy_question(text):
                    return await _policy_answer(
                        db, conn, session, context, now, first_user_at, masked.text,
                        settings, client_message_id=client_message_id,
                    )
                station_cards = await _station_cards(db, clock)
                reply = "我没有识别到具体站点，请回复以下站点名称之一：" + "、".join(
                    card["name"] for card in station_cards
                )
                return await _finish(
                    conn, session, context, now, first_user_at, reply,
                    [card["name"] for card in station_cards], ["show_stations"],
                    client_message_id=client_message_id,
                    extra={"stations": station_cards},
                )
            candidate_row = await conn.fetchrow(
                "SELECT * FROM candidates WHERE id = $1", context["candidate_id"]
            )
            slot_start = (now + timedelta(days=1)).replace(
                hour=9, minute=0, second=0, microsecond=0
            )
            try:
                booking = await bookings.create_booking(
                    db,
                    clock,
                    candidate=dict(candidate_row)
                    if candidate_row
                    else {"id": context["candidate_id"], "status": "complete"},
                    station_id=str(station["id"]),
                    slot_start=slot_start,
                    actor="agent",
                    conn=conn,
                )
            except ApiError as exc:
                if exc.code in ("sold_out", "candidate_not_ready", "duplicate_booking", "slot_full"):
                    station_cards = await _station_cards(db, clock)
                    return await _finish(
                        conn, session, context, now, first_user_at,
                        f"抱歉，{station['name']} 当前无法预约（{exc.message}），请换一个站点。",
                        [card["name"] for card in station_cards], ["show_stations"],
                        client_message_id=client_message_id,
                        extra={"stations": station_cards},
                    )
                raise
            await conn.execute(
                "UPDATE agent_sessions SET status = 'completed', stage = 'booked', updated_at = $2 WHERE id = $1",
                session["id"],
                now,
            )
            station_payload = await station_service.station_payload(db, station, clock)
            booking["station"] = station_payload
            reply = (
                f"预约成功：{station['name']}，{booking['slot_start'][:16].replace('T', ' ')}。"
                "请携带身份证按时到站。"
            )
            context["booking_id"] = booking["id"]
            return await _finish(
                conn, session, context, now, first_user_at, reply, [], ["booking_confirmed"],
                client_message_id=client_message_id, status="completed", stage="booked",
                extra={"booking": booking, "station": station_payload},
            )

        # 7) 政策问答（命中必须带出处；未命中必须转人工）
        if extract.is_policy_question(text):
            return await _policy_answer(
                db, conn, session, context, now, first_user_at, masked.text,
                settings, client_message_id=client_message_id,
            )

        # 8) 继续追问下一槽位
        next_slot = _next_slot(context)
        if next_slot is None:
            reply = "信息已齐全，正在为你安排站点。"
            return await _finish(
                conn, session, context, now, first_user_at, reply, [], [],
                client_message_id=client_message_id,
            )
        reply, quick_replies = _question(next_slot, context, degraded=degraded)
        return await _finish(
            conn, session, context, now, first_user_at, reply, quick_replies, [],
            client_message_id=client_message_id,
        )


async def _policy_answer(
    db: Any,
    conn: Any,
    session: dict[str, Any],
    context: dict[str, Any],
    now: Any,
    first_user_at: Any,
    query: str,
    settings: Any,
    *,
    client_message_id: str | None = None,
) -> dict[str, Any]:
    result = await policies.search_policies(
        db, query, min_score=settings.policy_min_score, top_k=settings.policy_top_k
    )
    if result["items"]:
        item = result["items"][0]
        citation = policies.format_citation(item)
        card = policies.build_policy_card(item)
        source_label = policies.build_source_label(item)
        next_slot = _next_slot(context)
        if next_slot:
            question, quick = _question(next_slot, context, degraded=False)
            reply = f"根据 {citation}\n\n我们继续：{question}"
            return await _finish(
                conn, session, context, now, first_user_at, reply, quick, [],
                client_message_id=client_message_id,
                extra={"policy_card": card, "source_label": source_label},
            )
        reply = f"根据 {citation}\n\n如还需其他信息，请继续告诉我。"
        return await _finish(
            conn, session, context, now, first_user_at, reply, [], [],
            client_message_id=client_message_id,
            extra={"policy_card": card, "source_label": source_label},
        )

    reply = await _handoff(
        conn,
        session=session,
        context=context,
        now=now,
        reply="这个问题我没有检索到可引用的政策依据，为避免误导，已为你转接人工客服，不会编造答案。",
        reason="policy_not_found",
        actor="agent",
    )
    return await _finish(
        conn, session, context, now, first_user_at, reply, [], ["handoff"],
        client_message_id=client_message_id, status="handoff", stage="handoff",
    )


async def _finish(
    conn: Any,
    session: dict[str, Any],
    context: dict[str, Any],
    now: Any,
    first_user_at: Any,
    reply: str,
    quick_replies: list[str],
    actions: list[str],
    *,
    client_message_id: str | None = None,
    status: str | None = None,
    stage: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    invalid = [action for action in actions if action not in VALID_ACTIONS]
    if invalid:  # pragma: no cover - 内部错误
        raise ValueError(f"invalid actions: {invalid}")
    latency_ms = int((now - first_user_at).total_seconds() * 1000)
    await _store_message(conn, session["id"], "assistant", reply, now, latency_ms=latency_ms)
    response: dict[str, Any] = {
        "reply": reply,
        "quick_replies": quick_replies,
        "progress": build_progress(context),
        "actions": actions,
        "message_id": uuid.uuid4().hex,
        "candidate_id": context.get("candidate_id"),
    }
    if extra:
        response.update(extra)

    client_replies = json.loads(session.get("client_replies") or "{}")
    if client_message_id:
        client_replies[client_message_id] = response

    await conn.execute(
        """
        UPDATE agent_sessions
        SET context = $2::jsonb,
            client_replies = $3::jsonb,
            status = coalesce($4, status),
            stage = coalesce($5, stage),
            first_user_at = coalesce(first_user_at, $6),
            first_reply_at = coalesce(first_reply_at, $7),
            updated_at = $7
        WHERE id = $1
        """,
        session["id"],
        json.dumps(context, ensure_ascii=False),
        json.dumps(client_replies, ensure_ascii=False),
        status,
        stage,
        first_user_at,
        now,
    )
    return response


async def _match_station(db: Any, text: str) -> dict[str, Any] | None:
    rows = await db.fetch("SELECT * FROM stations ORDER BY name")
    best: dict[str, Any] | None = None
    for row in rows:
        station = dict(row)
        if station["name"] in text or (station["area"] and station["area"] in text):
            if best is None or len(station["name"]) > len(best["name"]):
                best = station
    return best

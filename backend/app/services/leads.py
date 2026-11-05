"""线索导入：按 phone_token（确定性令牌）去重 + 站点/区域/轮询分派。"""

from __future__ import annotations

from typing import Any, Literal

from app.errors import bad_request
from app.security.tokens import EmployeeContext
from app.security.vault import Vault
from app.services import audit
from app.services import candidates as candidate_service
from app.services import stations as station_service

AssignmentStrategy = Literal["round_robin", "area", "station"]


async def import_leads(
    db: Any,
    vault: Vault,
    settings: Any,
    clock: Any,
    *,
    employee: EmployeeContext,
    items: list[dict[str, Any]],
    strategy: AssignmentStrategy = "round_robin",
    station_id: str | None = None,
    source_channel: str = "import",
) -> dict[str, Any]:
    if not items:
        raise bad_request("empty_import", "导入列表为空")
    if len(items) > 1000:
        raise bad_request("too_many_items", "单次导入不能超过 1000 条")
    if strategy == "station" and not station_id:
        raise bad_request("station_required", "station 分派策略必须提供 station_id")

    available = await station_service.assignable_stations(db, employee)
    if not available:
        raise bad_request("no_station_available", "当前数据域内没有可用站点")
    aliases = {
        str(row["id"]) for row in available
    } | {str(row["name"]) for row in available}

    if strategy == "station" and station_id not in aliases:
        raise bad_request("invalid_station", "站点不存在或不在当前数据域内")

    phone_tokens = [vault.token_for("phone", item["phone"]) for item in items]
    existing_rows = await db.fetch(
        "SELECT phone_token FROM candidates WHERE phone_token = ANY($1::text[])", phone_tokens
    )
    existing = {row["phone_token"] for row in existing_rows}

    seen: set[str] = set()
    deduped = 0
    imported = 0
    assignments: list[dict[str, str]] = []
    created_ids: list[str] = []
    area_cursor = 0

    for index, (item, token) in enumerate(zip(items, phone_tokens)):
        if token in seen or token in existing:
            deduped += 1
            continue
        seen.add(token)
        chosen = await _pick_station(
            available,
            strategy=strategy,
            station_id=station_id,
            area_text=item.get("area_text"),
            index=area_cursor if strategy != "round_robin" else index,
        )
        if strategy != "round_robin":
            area_cursor += 1
        city = chosen["city"]
        if source_channel == "import" and item.get("source_channel"):
            channel = item["source_channel"]
        else:
            channel = source_channel
        try:
            candidate = await candidate_service.create_candidate(
                db,
                vault,
                settings,
                clock,
                name=item["name"],
                phone=item["phone"],
                actor=employee.username,
                birth_ym=item.get("birth_ym"),
                area_text=item.get("area_text"),
                job_type=item.get("job_type"),
                has_ebike=item.get("has_ebike"),
                start_text=item.get("start_text"),
                health_cert=item.get("health_cert"),
                source_channel=channel,
                station_id=str(chosen["id"]),
                city=city,
            )
        except Exception as exc:  # 唯一约束兜底：视为重复
            if exc.__class__.__name__ == "ApiError" and getattr(exc, "code", "") == "duplicate_candidate":
                deduped += 1
                continue
            raise
        imported += 1
        created_ids.append(str(candidate["id"]))
        assignments.append({"candidate_id": str(candidate["id"]), "station_id": str(chosen["id"])})

    async with db.transaction() as conn:
        await audit.append_audit(
            conn,
            actor=employee.username,
            action="leads.import",
            resource="candidates",
            payload={
                "received": len(items),
                "imported": imported,
                "deduped": deduped,
                "strategy": strategy,
                "source_channel": source_channel,
            },
        )

    return {
        "received": len(items),
        "imported": imported,
        "deduped": deduped,
        "strategy": strategy,
        "assignments": assignments,
        "candidate_ids": created_ids,
    }


async def _pick_station(
    available: list[dict[str, Any]],
    *,
    strategy: AssignmentStrategy,
    station_id: str | None,
    area_text: str | None,
    index: int,
) -> dict[str, Any]:
    if strategy == "station":
        for row in available:
            if str(row["id"]) == station_id or str(row["name"]) == station_id:
                return row
        raise bad_request("invalid_station", "站点不存在或不在当前数据域内")
    if strategy == "area" and area_text:
        for row in available:
            area = str(row["area"])
            if area and area in area_text:
                return row
    return available[index % len(available)]

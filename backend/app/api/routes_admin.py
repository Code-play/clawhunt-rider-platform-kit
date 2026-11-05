"""运维端点（仅 admin）：审计链校验、保留期执行、outbox/webhook 投递。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_clock, get_db, get_settings, require_roles
from app.config import Settings
from app.db.database import Database
from app.errors import bad_request, not_found
from app.events import webhooks
from app.models.schemas import OutboxDeliverRequest
from app.security.tokens import EmployeeContext
from app.services import audit, retention

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/audit/verify")
async def verify_audit_chain(
    employee: EmployeeContext = Depends(require_roles("admin")),
    db: Database = Depends(get_db),
) -> dict:
    async with db.connection() as conn:
        return await audit.verify_chain(conn)


@router.get("/audit")
async def list_audit(
    employee: EmployeeContext = Depends(require_roles("admin")),
    db: Database = Depends(get_db),
    limit: int = 20,
) -> dict:
    rows = await db.fetch(
        "SELECT id, actor, action, resource, prev_hash, hash, created_at FROM audit_log ORDER BY id DESC LIMIT $1",
        min(max(limit, 1), 200),
    )
    return {
        "items": [
            {
                "id": row["id"],
                "actor": row["actor"],
                "action": row["action"],
                "resource": row["resource"],
                "prev_hash": row["prev_hash"],
                "hash": row["hash"],
                "created_at": row["created_at"].isoformat(),
            }
            for row in rows
        ]
    }


@router.post("/retention/run")
async def run_retention(
    employee: EmployeeContext = Depends(require_roles("admin")),
    db: Database = Depends(get_db),
    clock: object = Depends(get_clock),
    settings: Settings = Depends(get_settings),
) -> dict:
    return await retention.run_retention(db, clock, settings, actor=employee.username)


@router.get("/outbox")
async def list_outbox(
    employee: EmployeeContext = Depends(require_roles("admin")),
    db: Database = Depends(get_db),
    limit: int = 50,
) -> dict:
    rows = await db.fetch(
        "SELECT * FROM outbox_events ORDER BY created_at DESC LIMIT $1", min(max(limit, 1), 200)
    )
    return {
        "items": [
            {
                "id": str(row["id"]),
                "event_type": row["event_type"],
                "aggregate_type": row["aggregate_type"],
                "aggregate_id": str(row["aggregate_id"]),
                "dedupe_key": row["dedupe_key"],
                "attempts": row["attempts"],
                "next_attempt_at": row["next_attempt_at"].isoformat(),
                "delivered_at": row["delivered_at"].isoformat() if row["delivered_at"] else None,
                "last_error": row["last_error"],
                "created_at": row["created_at"].isoformat(),
            }
            for row in rows
        ]
    }


@router.post("/outbox/{event_id}/deliver")
async def deliver_outbox_event(
    event_id: str,
    body: OutboxDeliverRequest,
    employee: EmployeeContext = Depends(require_roles("admin")),
    db: Database = Depends(get_db),
    clock: object = Depends(get_clock),
    settings: Settings = Depends(get_settings),
) -> dict:
    endpoint = body.endpoint or settings.webhook_endpoint
    if not endpoint:
        raise bad_request("endpoint_required", "未配置 webhook 端点（WEBHOOK_ENDPOINT）")
    event = await db.fetchrow("SELECT id FROM outbox_events WHERE id = $1", event_id)
    if event is None:
        raise not_found("事件不存在")
    result = await webhooks.deliver_event(
        db,
        event_id,
        endpoint=endpoint,
        secret=settings.webhook_secret,
        now=clock.now(),
        backoff_base_seconds=settings.webhook_backoff_base_seconds,
        max_attempts=settings.webhook_max_attempts,
    )
    return result.as_dict()
